#!/usr/bin/env python3
"""
Hybrid PoC harness for the LibreNMS natural-language project.

Goal: test whether a "planning -> deterministic backend" split eliminates the
T46 class of failures (simple device-status questions where the LLM
occasionally misreads an explicit {"hostname": ..., "status": "up"} tool result).

Two paths are compared per test case:

  Path B (hybrid):
      Qwen plans (request_type / intent / device_query)
      -> deterministic entity resolution
      -> deterministic status lookup
      -> deterministic atomic formatter (final answer)

  Path A (direct LLM interpretation, current production baseline):
      Qwen resolves the device (entity step)
      -> Qwen reads the tool-result JSON and writes the final answer

The production system prompt is reproduced read-only in
production_baseline_system.txt (from `ollama show librenms-qwen --modelfile`)
so that Path A faithfully mirrors the current production assistant.

This PoC does NOT touch LibreNMS, does NOT implement real tools, and does NOT
modify the production Modelfile or evaluation suite.
"""

import argparse
from datetime import datetime
import inspect
import json
import os
import re
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

import resolver
import planner_v2
import investigation_grounding

HERE = os.path.dirname(os.path.abspath(__file__))

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "librenms-qwen"

# ----------------------------------------------------------------------------
# Device inventory (deterministic source of truth, loaded from inventory.json)
# ----------------------------------------------------------------------------
INVENTORY = resolver.load_inventory()

# ----------------------------------------------------------------------------
# Production baseline system prompt (reproduced read-only for Path A)
# ----------------------------------------------------------------------------
def load_baseline():
    path = os.path.join(HERE, "production_baseline_system.txt")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return (
            "You are a read-only LibreNMS Level-1 investigation assistant. "
            "You always answer in Turkish."
        )

PRODUCTION_SYSTEM = load_baseline()

# ----------------------------------------------------------------------------
# Qwen planning (Path B) - structured output
# ----------------------------------------------------------------------------
PLANNING_SCHEMA = {
    "type": "object",
    "properties": {
        "request_type": {
            "type": "string",
            "enum": ["atomic_fact", "device_set", "investigation", "unsupported"],
        },
        "intent": {
            "type": "string",
            "enum": ["device_status", "device_set", "investigation", "unknown"],
        },
        "device_query": {"type": ["string", "null"]},
    },
    "required": ["request_type", "intent", "device_query"],
}

PLANNING_SYSTEM = """You are the PLANNER for a network monitoring assistant. You classify the user's request and extract only the raw device reference. You do NOT resolve or disambiguate devices — the deterministic backend resolver does that.

request_type rules:
- "atomic_fact": a simple yes/no question about ONE device's CURRENT status (up/down, working, reachable, available). One deterministic lookup answers it. Even if the reference looks ambiguous or partial, use "atomic_fact" and let the backend decide.
- "device_set": the user refers to a device MODEL, SKU, part number, brand or a group of devices (not one specific hostname), e.g. a model name like "2530 48G", a SKU like "J9772A", or a feature description like "48 port PoE ProCurve".
- "investigation": any request that needs analysis, diagnosis, correlation, comparison, root-cause, or multi-step reasoning (e.g. "is there a problem?", "why?", "anything suspicious?", "but users report...").
- "unsupported": a question about the PAST ("was it up yesterday?", "last week") or outside current device status.

intent rules:
- "device_status" only when request_type is atomic_fact.
- "device_set" only when request_type is device_set.
- "investigation" only when request_type is investigation.
- "unknown" for unsupported.

device_query: the raw device/model reference exactly as the user wrote it (e.g. "Sw46", "sw-46", "sw 46", "sq46", "core switch", "J9772A", "2530 48G"). Do NOT normalize or resolve it. Use null only if there is no device reference at all.

Examples:
User: "sw-46 çalışıyor mu?" -> {"request_type":"atomic_fact","intent":"device_status","device_query":"sw-46"}
User: "sq46 çalışıyor mu?" -> {"request_type":"atomic_fact","intent":"device_status","device_query":"sq46"}
User: "core switch çalışıyor mu?" -> {"request_type":"atomic_fact","intent":"device_status","device_query":"core switch"}
User: "J9772A çalışıyor mu?" -> {"request_type":"device_set","intent":"device_set","device_query":"J9772A"}
User: "2530 48G çalışıyor mu?" -> {"request_type":"device_set","intent":"device_set","device_query":"2530 48G"}
User: "48 port PoE ProCurve çalışıyor mu?" -> {"request_type":"device_set","intent":"device_set","device_query":"48 port PoE ProCurve"}
User: "sw46 ayakta görünüyor ama kullanıcılar bağlantı problemi yaşıyor, dikkat çeken bir şey var mı?" -> {"request_type":"investigation","intent":"investigation","device_query":"sw46"}
User: "sw46 dün çalışıyor muydu?" -> {"request_type":"unsupported","intent":"unknown","device_query":"sw46"}

Output ONLY valid JSON matching the schema."""

# ----------------------------------------------------------------------------
# Path A entity-resolution step - structured output
# ----------------------------------------------------------------------------
ENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "hostname": {"type": ["string", "null"]},
        "ambiguous": {"type": "boolean"},
    },
    "required": ["hostname", "ambiguous"],
}

ENTITY_SYSTEM = """You are a network monitoring assistant. Resolve the device reference in the user's question to a hostname from the inventory below.

Inventory (hostname: status):
sw-46: up
sw-47: down
sw-48: unknown
sw-460: up
core-sw-01: up
core-sw-02: down

Rules:
- Return the exact hostname if exactly one device matches the reference.
- If the reference matches multiple devices, set ambiguous=true and hostname=null.
- If no device matches, set hostname=null and ambiguous=false.
Do not guess; do not invent hostnames.
Output ONLY valid JSON matching the schema."""


# ----------------------------------------------------------------------------
# Deterministic entity resolver (Path B backend) now lives in resolver.py.
# The harness calls resolver.resolve_device / resolver.resolve_device_set /
# resolver.lookup_status / resolver.format_atomic directly.
# ----------------------------------------------------------------------------
# Ollama client
# ----------------------------------------------------------------------------
def ollama_chat(model, messages, schema=None, temperature=0.0, think=False):
    payload = {
        "model": model,
        "stream": False,
        "think": think,
        "options": {
            "temperature": temperature,
            "top_p": 0.95,
            "top_k": 20,
            "presence_penalty": 1.5,
        },
        "messages": messages,
    }
    if schema is not None:
        payload["format"] = schema

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    elapsed_ms = (time.time() - t0) * 1000.0
    content = (body.get("message") or {}).get("content", "") or ""
    return content, body.get("done_reason"), elapsed_ms


def parse_json_obj(content):
    c = (content or "").strip()
    if c.startswith("```"):
        c = re.sub(r"^```[a-zA-Z]*\s*", "", c)
        c = re.sub(r"\s*```$", "", c)
    try:
        return json.loads(c)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", c, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def classify_status(text):
    """Classify the implied device status in a natural-language answer.

    Used only to judge Path A's final answer. Deliberately conservative:
    "bu bilgi mevcut verilerde bulunmuyor" is NOT treated as 'unknown'
    because for a present `status: unknown` field that wording would be a
    rule violation (missing-data claim) rather than a correct report.
    """
    if not text:
        return None
    t = text.lower()
    unknown = ["bilinmiyor", "bilinmemekte", "belirsiz", "unknown", "tespit edilemedi"]
    down = [
        "çalışmıyor", "calismiyor", "down", "kapalı", "erişilemiyor",
        "erisilemiyor", "ayakta değil", "ayakta degil", "devre dışı",
        "devre disi", "düştü", "dustu",
    ]
    up = [
        "çalışıyor", "calisiyor", "ayakta", "up", "erişilebilir", "erisilebilir",
        "aktif", "çalışmakta", "calismakta", "çalışır", "calisir",
    ]
    if any(k in t for k in unknown):
        return "unknown"
    if any(k in t for k in down):
        return "down"
    if any(k in t for k in up):
        return "up"
    return None


# ----------------------------------------------------------------------------
# Path B (hybrid)
# ----------------------------------------------------------------------------
def plan_question(question, model, temperature):
    content, reason, ms = ollama_chat(
        model,
        [
            {"role": "system", "content": PLANNING_SYSTEM},
            {"role": "user", "content": question},
        ],
        schema=PLANNING_SCHEMA,
        temperature=temperature,
    )
    return parse_json_obj(content), reason, ms


def run_path_b(case, model, temperature):
    q = case["question"]
    t0 = time.time()
    plan, reason, plan_ms = plan_question(q, model, temperature)

    rt = (plan or {}).get("request_type")
    intent = (plan or {}).get("intent")
    dq = (plan or {}).get("device_query")

    r = {
        "plan": plan,
        "request_type": rt,
        "intent": intent,
        "device_query": dq,
        "plan_latency_ms": round(plan_ms, 1),
        "resolution": None,
        "reason": None,
        "hostname": None,
        "status": None,
        "answer": None,
        "route": None,
        "candidates": None,
        "models": None,
        "devices": None,
    }

    # "clarification" is no longer a planner authority; if an older planner
    # emits it, fall through to the deterministic resolver anyway.
    if rt in ("atomic_fact", "clarification"):
        res = resolver.resolve_device(dq)
        r["resolution"] = res["outcome"]
        r["reason"] = res["reason"]
        if res["outcome"] == "resolved":
            device = res["device"]
            hostname = device["hostname"]
            status = resolver.lookup_status(hostname)
            r["hostname"] = hostname
            r["status"] = status
            r["answer"] = resolver.format_atomic(hostname, device.get("status", status))
            r["route"] = "atomic"
        elif res["outcome"] == "ambiguous":
            r["candidates"] = [c["hostname"] for c in res["candidates"]]
            r["route"] = "ambiguous"
        else:
            r["route"] = "no_match"
    elif rt == "device_set":
        res = resolver.resolve_device_set(dq)
        r["resolution"] = res["outcome"]
        r["reason"] = res["reason"]
        r["models"] = [m["sku"] for m in (res.get("models") or [])]
        r["devices"] = [d["hostname"] for d in (res.get("devices") or [])]
        r["answer"] = resolver.format_device_set(res)
        r["route"] = "device_set" if res["outcome"] == "resolved" else "no_match"
    elif rt == "investigation":
        r["route"] = "investigation"
    elif rt == "unsupported":
        r["route"] = "unsupported"
    else:
        r["route"] = "unknown"

    r["total_latency_ms"] = round((time.time() - t0) * 1000.0, 1)
    return r


def judge_path_b(case, r):
    exp = case["expected"]
    route = r.get("route")
    if exp["route"] == "atomic":
        hostname_ok = r.get("hostname") == exp["hostname"]
        status_ok = r.get("status") == exp["status"]
        reason_ok = ("reason" not in exp) or (r.get("reason") == exp["reason"])
        ok = route == "atomic" and hostname_ok and status_ok and reason_ok
        return ok, {
            "hostname_ok": hostname_ok, "status_ok": status_ok, "route": route,
            "reason": r.get("reason"), "reason_ok": reason_ok,
        }

    if exp["route"] == "device_set":
        models_ok = (set(r.get("models") or []) == set(exp["models"])) if "models" in exp else True
        devices_ok = (set(r.get("devices") or []) == set(exp["devices"])) if "devices" in exp else True
        # A device-set answer is also acceptable if the planner misrouted to
        # atomic_fact and the resolver returned the equivalent ambiguous set.
        ok = (route == "device_set" and models_ok and devices_ok) or (
            route == "ambiguous" and "devices" in exp
            and set(r.get("candidates") or []) == set(exp["devices"])
        )
        return ok, {
            "route": route, "models": r.get("models"), "devices": r.get("devices"),
            "models_ok": models_ok, "devices_ok": devices_ok,
        }

    if exp["route"] == "investigation":
        return route == "investigation", {"route": route}

    if exp["route"] == "clarification":
        kind = exp.get("clarification_kind")
        if kind == "ambiguous":
            ok = route == "ambiguous"
        elif kind == "no_match":
            ok = route == "no_match"
        else:
            ok = route in ("ambiguous", "no_match")
        return ok, {"route": route, "expected_kind": kind}

    if exp["route"] == "unsupported":
        # Must stay out of the current-status atomic path. "unsupported" is the
        # expected classification; "investigation" is also acceptable because it
        # still avoids using current status.
        ok = route in ("unsupported", "investigation")
        return ok, {"route": route}

    return False, {"route": route}


# ----------------------------------------------------------------------------
# Hybrid orchestrator: single entry point used by external acceptance harnesses
# ----------------------------------------------------------------------------
# The orchestrator is the SUT's decision layer: it runs the REAL Qwen planner,
# the deterministic resolver, route selection, SpyBackend execution and (for
# investigation) the REAL Qwen grounded-synthesis step. A thin adapter in the
# harness only translates the orchestrator's output into the harness trace.
#
# planner_schema:
#   'poc'  - the ORIGINAL planner taxonomy {atomic_fact, device_set,
#            investigation, unsupported}. Used to measure the current system.
#   'gold' - orchestration-contract taxonomy that additionally separates direct
#            retrieval routes {ports, alerts, events} and historical
#            investigation, and keeps current-status questions on the atomic
#            path even for SKU/model references (identity is the resolver's job).
#
# The planner is Qwen; it never resolves identity. The resolver module can be
# injected (resolver_candidate_v4) and must expose resolve_device,
# resolve_device_set, format_atomic, format_clarification, format_device_set.
# ----------------------------------------------------------------------------

PLANNING_SCHEMA_GOLD = {
    "type": "object",
    "properties": {
        "request_type": {
            "type": "string",
            "enum": [
                "atomic_fact",
                "ports",
                "alerts",
                "events",
                "device_set",
                "device_set_status",
                "investigation",
                "historical_investigation",
                "unsupported",
            ],
        },
        "intent": {
            "type": "string",
            "enum": [
                "device_status",
                "device_ports",
                "device_alerts",
                "device_events",
                "device_set",
                "device_set_status",
                "investigation",
                "historical_status",
                "unsupported",
                "unknown",
            ],
        },
        "device_query": {"type": ["string", "null"]},
        "device_filters": planner_v2.DEVICE_FILTER_SCHEMA,
        "event_window": planner_v2.EVENT_WINDOW_SCHEMA,
    },
    "required": ["request_type", "intent", "device_query", "device_filters"],
}

PLANNING_SYSTEM_GOLD = """You are the semantic planner for a read-only network monitoring assistant. Output one JSON object matching the schema. Do not answer the user and do not resolve catalog identity.

Choose exactly one request_type and its matching intent:
- atomic_fact / device_status: current status of ONE device reference, including a bare device-like token.
- device_set_status / device_set_status: current status of a plural group or set of devices.
- device_set / device_set: list/show a device group; no current-status question.
- ports / device_ports: directly retrieve port state.
- alerts / device_alerts: directly retrieve active alerts.
- events / device_events: directly retrieve events or logs.
- investigation / investigation: cause, reason, diagnosis, explanation, effect, or a reported conflict with the simple status bit. Investigation wins over ports/alerts/events.
- historical_investigation / historical_status: any question about the past.
- unsupported / unsupported: only an explicit write or change request such as reboot, restart, reset, configure, change, or delete.

Identity rules:
- The resolver owns unique, ambiguous, and no-match decisions. Never choose clarification or no-match here.
- Copy an explicit hostname, alias, SKU, model phrase, number, or unknown device-like token into device_query. Never drop, truncate, complete, normalize, or split it into filters.
- Intent words such as device, devices, show, status, problem, port, alert, and event are not part of device_query.
- A Turkish plural suffix attached to an identity is grammar: J9775A'lar has device_query J9775A.
- Use device_query=null only for a feature/family group with no explicit identity, or when no reference exists.
- A bare number or unknown SKU is a device reference, never unsupported.

Plurality rules:
- A singular current-status request is atomic_fact even if its reference may match multiple inventory devices. The resolver will clarify.
- A plural/group current-status request is device_set_status.
- A plural/group list request without current status is device_set.
- Plural/group means multiple DEVICES, switches, models, or a device family.
  Grammatical plural or possessive forms of port, alarm, event, or log do not
  mean a device set. If the requested object is ports, alerts, events, or logs,
  choose its direct retrieval route unless the user asks for explanation.

device_filters rules:
- Every output contains exactly brand, family, port_count, and poe.
- For atomic_fact, ports, alerts, events, investigation, historical_investigation, and unsupported, every filter is null without exception.
- For device_set and device_set_status, fill filters only when the user explicitly describes a feature/family group rather than naming a model identity.
- null means unconstrained. poe=false only means explicitly non-PoE.
- Never infer filters from characters inside device_query. A model phrase such as 6400-24G-PoEP remains one identity and all filters stay null.

event_window rules:
- Omit event_window for every non-investigation route.
- For a current investigation with no explicit time expression, use {"mode":"default_24h"}.
- For "son N saat/gün/hafta", use {"mode":"relative","amount":N,"unit":"hour|day|week"}.
- For an explicit date or interval, use {"mode":"absolute","from":"ISO date or datetime","to":"ISO date or datetime"}.
- Never calculate relative timestamps; the deterministic orchestrator anchors them to request time.

Examples:
"6400-24G-PoEP up mı?"
-> {"request_type":"atomic_fact","intent":"device_status","device_query":"6400-24G-PoEP","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"core switch port 8 ne durumda?"
-> {"request_type":"ports","intent":"device_ports","device_query":"core switch","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"X100 portlarını göster"
-> {"request_type":"ports","intent":"device_ports","device_query":"X100","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"X100 üzerinde aktif alarm var mı?"
-> {"request_type":"alerts","intent":"device_alerts","device_query":"X100","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"X100 alarmını göster"
-> {"request_type":"alerts","intent":"device_alerts","device_query":"X100","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"X100 son eventlerini göster"
-> {"request_type":"events","intent":"device_events","device_query":"X100","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"ZZ999 neden problem yaşıyor?"
-> {"request_type":"investigation","intent":"investigation","device_query":"ZZ999","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null},"event_window":{"mode":"default_24h"}}

"ZZ999 son 7 günde neden problem yaşadı?"
-> {"request_type":"historical_investigation","intent":"historical_status","device_query":"ZZ999","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null},"event_window":{"mode":"relative","amount":7,"unit":"day"}}

"ZZ999 20 Ağustos 2026 tarihinde neden problem yaşadı?"
-> {"request_type":"historical_investigation","intent":"historical_status","device_query":"ZZ999","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null},"event_window":{"mode":"absolute","from":"2026-08-20","to":"2026-08-20"}}

"J4850A cihazı açık mı?"
-> {"request_type":"atomic_fact","intent":"device_status","device_query":"J4850A","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"J4850A cihazları açık mı?"
-> {"request_type":"device_set_status","intent":"device_set_status","device_query":"J4850A","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"J9775A'lar çalışıyor mu?"
-> {"request_type":"device_set_status","intent":"device_set_status","device_query":"J9775A","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"J9775A cihazlarını göster"
-> {"request_type":"device_set","intent":"device_set","device_query":"J9775A","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

"48 port PoE'siz cihazlar açık mı?"
-> {"request_type":"device_set_status","intent":"device_set_status","device_query":null,"device_filters":{"brand":null,"family":null,"port_count":48,"poe":false}}

"2530 ailesindeki cihazların durumu ne?"
-> {"request_type":"device_set_status","intent":"device_set_status","device_query":null,"device_filters":{"brand":null,"family":"2530","port_count":null,"poe":null}}

"42"
-> {"request_type":"atomic_fact","intent":"device_status","device_query":"42","device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}

Before output, verify mechanically:
1. request_type and intent are the matching pair above.
2. Explicit identity present means device_query is not null.
3. Non-set route means all four filters are null.
4. Output only the JSON object."""

_ORCH_ROUTE = {
    "atomic_fact": "atomic",
    "ports": "ports",
    "alerts": "alerts",
    "events": "events",
    "device_set": "device_set",
    "device_set_status": "device_set_status",
    "investigation": "investigation",
    "historical_investigation": "historical_investigation",
    "unsupported": "unsupported",
}


def _format_ports_text(hostname, ports):
    if not ports:
        return f"{hostname} için port verisi bulunmuyor."
    lines = []
    for p in ports:
        lines.append(
            f"Port {p.get('ifName', p.get('ifIndex'))}: "
            f"admin={p.get('ifAdminStatus')} oper={p.get('ifOperStatus')}"
            f"{(' (' + p['ifAlias'] + ')') if p.get('ifAlias') else ''}"
        )
    return f"{hostname} portları:\n" + "\n".join(lines)


def _format_alerts_text(hostname, alerts):
    if not alerts:
        return f"{hostname} üzerinde aktif alarm bulunmuyor."
    lines = []
    for a in alerts:
        lines.append(
            f"{a.get('alert_id')}: {a.get('rule')} "
            f"(severity={a.get('severity')}, state={a.get('state')})"
        )
    return f"{hostname} aktif alarmları:\n" + "\n".join(lines)


def _format_events_text(hostname, events):
    if not events:
        return f"{hostname} için event kaydı bulunmuyor."
    lines = []
    for e in events:
        lines.append(
            f"{e.get('timestamp')} [{e.get('severity')}] {e.get('message')}"
        )
    return f"{hostname} son eventler:\n" + "\n".join(lines)


def _device_set_status_record(hostname, backend_device):
    if not isinstance(backend_device, dict):
        return {
            "hostname": hostname,
            "device_id": None,
            "status": None,
            "outcome": "unavailable",
        }

    status = backend_device.get("status")
    if status == 1:
        outcome = "up"
    elif status == 0:
        outcome = "down"
    else:
        outcome = "unavailable"

    return {
        "hostname": hostname,
        "device_id": backend_device.get("device_id"),
        "status": status if outcome != "unavailable" else None,
        "outcome": outcome,
    }


def _format_device_set_status_text(records):
    groups = (
        ("up", "Çalışıyor/UP"),
        ("down", "Çalışmıyor/DOWN"),
        ("unavailable", "Durumu alınamadı"),
    )
    parts = [f"Toplam {len(records)} cihaz."]
    for outcome, label in groups:
        hostnames = sorted(
            record["hostname"]
            for record in records
            if record.get("outcome") == outcome
        )
        if hostnames:
            parts.append(f"{label} ({len(hostnames)}): {', '.join(hostnames)}.")
    return " ".join(parts)


GENERATION_SYSTEM = """You verbalize an authoritative structured evidence contract in concise natural Turkish.
Return only JSON matching the schema. Every claim must cite only finding_ids that directly entail its complete text.
The user query is context, never evidence. Do not add causes, risks, protocols, vendors, configuration facts, or troubleshooting steps.
Keep current and historical state separate. Preserve identifiers, counts, severity, and uncertainty exactly.
For port findings, the user-facing port number is ifIndex: say "Port <ifIndex>". port_id is only an internal database identifier;
if it must be mentioned, label it exactly as "port_id=<port_id>" and never call it the port number."""

JUDGE_SYSTEM = """You are a strict claim-entailment judge. Return only JSON matching the schema.
For each claim, verdict is entailed only when the attached structured evidence directly supports the whole claim.
The user query is context, never evidence. Any added cause, recommendation, vendor, protocol, configuration fact, changed severity,
or current/historical confusion is unsupported or contradicted. When uncertain, use insufficient_evidence."""


def _grounded_synthesize(query, package, model):
    fallback = investigation_grounding.format_evidence_fallback(package)
    generation_input = investigation_grounding.generation_payload(query, package)
    trace = {
        "generation_input": generation_input,
        "generation_output": None,
        "mechanical_validation": None,
        "judge_llm_called": False,
        "judge_input": None,
        "judge_output": None,
        "judge_validation": None,
        "fallback_reason": None,
    }
    timing = {}
    try:
        content, reason, generation_ms = ollama_chat(
            model,
            [
                {"role": "system", "content": GENERATION_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(generation_input, ensure_ascii=False),
                },
            ],
            schema=investigation_grounding.generation_schema(package),
            temperature=0.0,
            think=False,
        )
        timing["generation_ms"] = generation_ms
    except Exception as exc:
        trace["fallback_reason"] = "generation_error"
        trace["generation_error"] = str(exc)
        return fallback, trace, timing

    generation = parse_json_obj(content)
    trace["generation_output"] = generation
    errors = investigation_grounding.validate_generation(generation, package)
    trace["mechanical_validation"] = {"valid": not errors, "errors": errors}
    if errors:
        trace["fallback_reason"] = "mechanical_validation_failed"
        return fallback, trace, timing

    judge_input = investigation_grounding.judge_payload(query, generation, package)
    trace["judge_input"] = judge_input
    trace["judge_llm_called"] = True
    try:
        judge_content, judge_reason, judge_ms = ollama_chat(
            model,
            [
                {"role": "system", "content": JUDGE_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(judge_input, ensure_ascii=False),
                },
            ],
            schema=investigation_grounding.judge_schema(len(generation["claims"])),
            temperature=0.0,
            think=False,
        )
        timing["judge_ms"] = judge_ms
    except Exception as exc:
        trace["fallback_reason"] = "judge_error"
        trace["judge_error"] = str(exc)
        return fallback, trace, timing

    judgement = parse_json_obj(judge_content)
    trace["judge_output"] = judgement
    judge_errors = investigation_grounding.validate_judgement(
        judgement, len(generation["claims"])
    )
    trace["judge_validation"] = {"valid": not judge_errors, "errors": judge_errors}
    if judge_errors:
        trace["fallback_reason"] = "judge_invalid_output"
        return fallback, trace, timing
    if any(
        verdict["verdict"] != "entailed"
        for verdict in judgement["verdicts"]
    ):
        trace["fallback_reason"] = "judge_rejected_claims"
        return fallback, trace, timing
    return " ".join(claim["text"].strip() for claim in generation["claims"]), trace, timing


def orchestrate(query, inventory=None, backend=None, model=DEFAULT_MODEL,
                planner_schema="poc", resolver_module=None,
                synthesis_system=None, request_time=None):
    """Run the real hybrid pipeline for one user query and return a full trace.

    Args:
        query: user question.
        inventory: inventory dict (defaults to the PoC inventory).
        backend: SpyBackend-like object that records actual tool calls.
        model: Ollama model name (default librenms-qwen).
        planner_schema: 'poc' (original taxonomy) or 'gold' (contract taxonomy).
        resolver_module: deterministic resolver module (defaults to the PoC resolver).
        synthesis_system: deprecated compatibility argument; grounded generation
            and judge use their dedicated fixed system prompts.
        request_time: optional timezone-aware timestamp used to resolve relative
            investigation event windows exactly once per request.

    Returns a dict with route in the gold-compatible vocabulary:
        atomic | ports | alerts | events | device_set | device_set_status | investigation |
        historical_investigation | clarification | no_match | unsupported | unknown
    plus planner/synthesis LLM flags kept separate.
    """
    wall0 = time.time()
    llm = {"planner": False, "synthesis": False, "judge": False}
    timing = {}
    if inventory is None:
        inventory = INVENTORY
    if resolver_module is None:
        resolver_module = resolver
    if synthesis_system is None:
        synthesis_system = PRODUCTION_SYSTEM
    if request_time is None:
        request_time = datetime.now(ZoneInfo("Europe/Istanbul"))

    if planner_schema == "gold":
        schema, system = PLANNING_SCHEMA_GOLD, PLANNING_SYSTEM_GOLD
    else:
        schema, system = PLANNING_SCHEMA, PLANNING_SYSTEM

    # 1) planner: Qwen owns all natural-language interpretation. Python only
    # validates the resulting structured plan before any resolver/tool action.
    t0 = time.time()
    content, reason, ms = ollama_chat(
        model,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ],
        schema=schema,
        temperature=0.0,
        think=False,
    )
    llm["planner"] = True
    plan = parse_json_obj(content)
    planner_errors = []
    if planner_schema == "gold":
        valid, planner_errors = planner_v2.validate_plan(plan)
        if not valid:
            plan = None
    timing["planner_ms"] = round(ms, 1)
    planner_output = {
        "planner_schema": planner_schema,
        "plan": plan,
        "raw": {
            "content": content,
            "done_reason": reason,
            "method": "llm",
        },
    }

    if not isinstance(plan, dict):
        return {
            "query": query,
            "planner_output": planner_output,
            "route": "unknown",
            "intent": None,
            "resolver_output": None,
            "tool_calls": list(backend.trace()) if backend is not None else [],
            "tool_results": {},
            "planner_llm_called": llm["planner"],
            "synthesis_llm_called": llm["synthesis"],
            "judge_llm_called": llm["judge"],
            "structured_findings": None,
            "grounding_trace": None,
            "event_window": None,
            "llm_input": None,
            "llm_output": None,
            "final_answer": None,
            "timing_ms": {
                "planner_ms": timing["planner_ms"],
                "total_ms": round((time.time() - wall0) * 1000.0, 1),
            },
            "planner_failure": True,
            "planner_errors": planner_errors,
        }

    rt = plan.get("request_type")
    intent = plan.get("intent")
    dq = plan.get("device_query")
    device_filters = plan.get("device_filters") if planner_schema == "gold" else None
    event_window_spec = plan.get("event_window") if planner_schema == "gold" else None
    route = _ORCH_ROUTE.get(rt, "unknown")

    # 2) deterministic resolution
    t0 = time.time()
    res = None
    if route == "unsupported":
        res = None
    elif route in ("device_set", "device_set_status"):
        if hasattr(resolver_module, "planner_catalog_context"):
            res = resolver_module.resolve_device_set(
                dq, inventory, filters=device_filters
            )
        else:
            # Compatibility only for frozen pre-v5 resolver runs.
            res = resolver_module.resolve_device_set(dq, inventory)
        if res.get("outcome") == "no_match":
            route = "no_match"
    else:
        res = resolver_module.resolve_device(dq, inventory)
        if res.get("outcome") == "ambiguous":
            route = "clarification"
        elif res.get("outcome") == "no_match":
            route = "no_match"
    timing["resolve_ms"] = round((time.time() - t0) * 1000.0, 2)

    # 3) backend execution + final answer
    t0 = time.time()
    evidence = {}
    final_answer = None
    llm_input = None
    llm_output = None
    structured_findings = None
    grounding_trace = None
    resolved_event_window = None
    device = res.get("device") if isinstance(res, dict) else None
    hostname = device.get("hostname") if device else None
    def bk(fn, **kw):
        if backend is None:
            return None
        return getattr(backend, fn)(**kw)

    def bk_events(device_id, window=None):
        if backend is None:
            return None
        method = getattr(backend, "get_events")
        kwargs = {"device_id": device_id}
        if window is not None:
            parameters = list(inspect.signature(method).parameters.values())
            parameter_names = {parameter.name for parameter in parameters}
            supports_window = (
                any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in parameters
                )
                or {"from_time", "to_time"}.issubset(parameter_names)
            )
            if not supports_window:
                return None
            kwargs.update(
                investigation_grounding.event_window_backend_args(window)
            )
        return method(**kwargs)

    if route == "unsupported":
        final_answer = (
            "Bu katman yalnızca read-only (salt-okunur) işlemleri destekliyor; "
            "yazma/reboot/konfigürasyon değişikliği yapılamaz."
        )
    elif route == "clarification":
        final_answer = resolver_module.format_clarification(
            res.get("candidates")
        )
    elif route == "no_match":
        final_answer = "Eşleşen cihaz bulunamadı."
    elif route == "device_set":
        final_answer = resolver_module.format_device_set(res)
    elif route == "device_set_status":
        records = []
        devices = sorted(
            res.get("devices") or [], key=lambda item: item.get("hostname", "")
        )
        for resolved_device in devices:
            resolved_hostname = resolved_device.get("hostname")
            try:
                backend_device = bk("get_device", hostname=resolved_hostname)
            except Exception:
                backend_device = None
            records.append(
                _device_set_status_record(resolved_hostname, backend_device)
            )
        evidence["devices"] = records
        final_answer = _format_device_set_status_text(records)
    elif hostname is None or device is None:
        route = "no_match"
        final_answer = "Eşleşen cihaz bulunamadı."
        res = {"outcome": "no_match", "reason": "no_match", "candidates": []}
    elif route == "atomic":
        ev = bk("get_device", hostname=hostname)
        evidence["device"] = ev
        status = ev.get("status") if isinstance(ev, dict) else None
        final_answer = resolver_module.format_atomic(hostname, status)
    elif route == "ports":
        evidence["device"] = bk("get_device", hostname=hostname)
        backend_did = (evidence["device"] or {}).get("device_id")
        evidence["ports"] = (
            bk("get_ports", device_id=backend_did) if backend_did is not None else []
        )
        final_answer = _format_ports_text(hostname, evidence["ports"])
    elif route == "alerts":
        evidence["device"] = bk("get_device", hostname=hostname)
        backend_did = (evidence["device"] or {}).get("device_id")
        evidence["alerts"] = (
            bk("get_alerts", device_id=backend_did) if backend_did is not None else []
        )
        final_answer = _format_alerts_text(hostname, evidence["alerts"])
    elif route == "events":
        evidence["device"] = bk("get_device", hostname=hostname)
        backend_did = (evidence["device"] or {}).get("device_id")
        evidence["events"] = (
            bk_events(backend_did) if backend_did is not None else []
        )
        final_answer = _format_events_text(hostname, evidence["events"])
    elif route == "historical_investigation":
        resolved_event_window = investigation_grounding.resolve_event_window(
            event_window_spec, request_time
        )
        evidence["device"] = bk("get_device", hostname=hostname)
        backend_did = (evidence["device"] or {}).get("device_id")
        evidence["events"] = (
            bk_events(backend_did, resolved_event_window)
            if backend_did is not None
            else None
        )
        structured_findings = investigation_grounding.build_investigation_evidence(
            evidence, resolved_event_window
        )
        llm["synthesis"] = True
        final_answer, grounding_trace, synth_timing = _grounded_synthesize(
            query, structured_findings, model
        )
        llm["judge"] = grounding_trace["judge_llm_called"]
        llm_input = grounding_trace["generation_input"]
        llm_output = grounding_trace["generation_output"]
        timing.update(synth_timing)
        timing["synthesis_ms"] = round(sum(synth_timing.values()), 1)
    elif route == "investigation":
        resolved_event_window = investigation_grounding.resolve_event_window(
            event_window_spec, request_time
        )
        evidence["device"] = bk("get_device", hostname=hostname)
        backend_did = (evidence["device"] or {}).get("device_id")
        if backend_did is None:
            evidence["ports"] = None
            evidence["alerts"] = None
            evidence["events"] = None
        else:
            evidence["ports"] = bk("get_ports", device_id=backend_did)
            evidence["alerts"] = bk("get_alerts", device_id=backend_did)
            evidence["events"] = bk_events(backend_did, resolved_event_window)
        structured_findings = investigation_grounding.build_investigation_evidence(
            evidence, resolved_event_window
        )
        llm["synthesis"] = True
        final_answer, grounding_trace, synth_timing = _grounded_synthesize(
            query, structured_findings, model
        )
        llm["judge"] = grounding_trace["judge_llm_called"]
        llm_input = grounding_trace["generation_input"]
        llm_output = grounding_trace["generation_output"]
        timing.update(synth_timing)
        timing["synthesis_ms"] = round(sum(synth_timing.values()), 1)
    else:
        final_answer = "İşlem desteklenmiyor."
    timing["execution_ms"] = round((time.time() - t0) * 1000.0, 2)
    timing["total_ms"] = round((time.time() - wall0) * 1000.0, 1)

    return {
        "query": query,
        "planner_output": planner_output,
        "route": route,
        "intent": intent,
        "resolver_output": res,
        "tool_calls": list(backend.trace()) if backend is not None else [],
        "tool_results": evidence,
        "planner_llm_called": llm["planner"],
        "synthesis_llm_called": llm["synthesis"],
        "judge_llm_called": llm["judge"],
        "structured_findings": structured_findings,
        "grounding_trace": grounding_trace,
        "event_window": resolved_event_window,
        "llm_input": llm_input,
        "llm_output": llm_output,
        "final_answer": final_answer,
        "timing_ms": timing,
        "planner_failure": False,
        "planner_errors": planner_errors,
    }


# ----------------------------------------------------------------------------
# Path A (direct LLM interpretation)
# ----------------------------------------------------------------------------
def path_a_entity(question, model, temperature):
    content, reason, ms = ollama_chat(
        model,
        [
            {"role": "system", "content": ENTITY_SYSTEM},
            {"role": "user", "content": question},
        ],
        schema=ENTITY_SCHEMA,
        temperature=temperature,
    )
    obj = parse_json_obj(content)
    return obj, reason, ms


def path_a_final(question, tool_result_obj, model, temperature):
    tool_json = json.dumps(tool_result_obj, ensure_ascii=False, indent=2)
    user = (
        "Aşağıdaki veriler salt-okunur onaylı bir araçtan geldi:\n"
        + tool_json
        + '\n\nKullanıcı sordu: "' + question + '"\n'
    )
    content, reason, ms = ollama_chat(
        model,
        [
            {"role": "system", "content": PRODUCTION_SYSTEM},
            {"role": "user", "content": user},
        ],
        schema=None,
        temperature=temperature,
    )
    return content, reason, ms


def run_path_a(case, model, temperature):
    q = case["question"]
    exp = case["expected"]

    ent, ereason, ems = path_a_entity(q, model, temperature)
    r = {
        "entity": ent,
        "entity_reason": ereason,
        "entity_latency_ms": round(ems, 1),
        "final_answer": None,
        "implied_status": None,
        "final_latency_ms": None,
    }

    rt = exp["route"]
    if rt == "atomic":
        ans, freason, fms = path_a_final(
            q, {"hostname": exp["hostname"], "status": exp["status"]}, model, temperature
        )
        r["final_answer"] = ans
        r["final_reason"] = freason
        r["final_latency_ms"] = round(fms, 1)
        r["implied_status"] = classify_status(ans)
    elif rt == "clarification" and exp.get("clarification_kind") == "no_match":
        ans, freason, fms = path_a_final(
            q, {"found": False, "hostname": None, "status": None}, model, temperature
        )
        r["final_answer"] = ans
        r["final_reason"] = freason
        r["final_latency_ms"] = round(fms, 1)
        r["implied_status"] = classify_status(ans)
    elif rt == "investigation":
        host = exp.get("hostname") or "sw-46"
        ans, freason, fms = path_a_final(
            q, {"hostname": host, "status": "up"}, model, temperature
        )
        r["final_answer"] = ans
        r["final_reason"] = freason
        r["final_latency_ms"] = round(fms, 1)
        r["implied_status"] = classify_status(ans)
    elif rt == "unsupported":
        host = exp.get("hostname") or "sw-46"
        ans, freason, fms = path_a_final(
            q, {"hostname": host, "status": "up"}, model, temperature
        )
        r["final_answer"] = ans
        r["final_reason"] = freason
        r["final_latency_ms"] = round(fms, 1)
        r["implied_status"] = classify_status(ans)

    return r


def judge_path_a(case, r):
    exp = case["expected"]
    rt = exp["route"]
    ent = r.get("entity") or {}
    ent_hostname = ent.get("hostname")
    ent_ambiguous = bool(ent.get("ambiguous"))
    ans = (r.get("final_answer") or "").lower()

    if rt == "atomic":
        hostname_ok = ent_hostname == exp["hostname"]
        implied = r.get("implied_status")
        status_ok = implied == exp["status"]
        ok = hostname_ok and status_ok
        return ok, {
            "hostname_ok": hostname_ok,
            "entity_hostname": ent_hostname,
            "entity_ambiguous": ent_ambiguous,
            "implied_status": implied,
            "status_ok": status_ok,
        }

    if rt == "clarification" and exp.get("clarification_kind") == "ambiguous":
        # must NOT guess a single device
        ok = ent_ambiguous or ent_hostname is None
        return ok, {"entity_hostname": ent_hostname, "entity_ambiguous": ent_ambiguous}

    if rt == "clarification" and exp.get("clarification_kind") == "no_match":
        # must NOT fabricate a hostname; final answer must NOT assert up/down
        entity_ok = ent_hostname is None and not ent_ambiguous
        implied = r.get("implied_status")
        no_fabrication = implied not in ("up", "down")
        ok = entity_ok and no_fabrication
        return ok, {
            "entity_hostname": ent_hostname,
            "entity_ambiguous": ent_ambiguous,
            "implied_status": implied,
        }

    if rt == "investigation":
        # must NOT collapse to a binary "working -> no problem" verdict
        implied = r.get("implied_status")
        no_problem_phrases = ["sorun yok", "problem yok", "sıkıntı yok", "sorunsuz", "problem yoktur"]
        collapsed = implied in ("up", "down") and any(k in ans for k in no_problem_phrases)
        ok = not collapsed
        return ok, {"implied_status": implied, "collapsed_to_status": collapsed}

    if rt == "unsupported":
        # must NOT answer a past-tense question with the current status
        implied = r.get("implied_status")
        history_markers = [
            "dün", "dun", "geçmiş", "gecmis", "tarih", "hafta", "önce", "once",
            "bilmiyor", "bilmiyorum", "bulunmuyor", "mevcut verilerde",
        ]
        used_current_status = implied in ("up", "down") and not any(m in ans for m in history_markers)
        ok = not used_current_status
        return ok, {"implied_status": implied, "used_current_status": used_current_status}

    if rt == "device_set":
        # Path A (direct LLM baseline) has no device-set capability; it is not
        # measured here. It must simply not fabricate a specific hostname.
        ok = ent_hostname is None
        return ok, {"entity_hostname": ent_hostname, "note": "device_set not part of Path A baseline"}

    return False, {}


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------
def load_cases(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def run_case(case, model, temperature):
    pb = run_path_b(case, model, temperature)
    pa = run_path_a(case, model, temperature)
    pb_pass, pb_detail = judge_path_b(case, pb)
    pa_pass, pa_detail = judge_path_a(case, pa)
    pb["pass"] = pb_pass
    pb["judge"] = pb_detail
    pa["pass"] = pa_pass
    pa["judge"] = pa_detail
    return {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "expected": case["expected"],
        "path_b": pb,
        "path_a": pa,
    }


def summarize(cases_results):
    n = len(cases_results)
    pb_pass = sum(1 for c in cases_results if c["path_b"]["pass"])
    pa_pass = sum(1 for c in cases_results if c["path_a"]["pass"])

    atomic = [c for c in cases_results if c["expected"]["route"] == "atomic"]
    atomic_n = len(atomic)
    pb_atomic = sum(1 for c in atomic if c["path_b"]["pass"])
    pa_atomic = sum(1 for c in atomic if c["path_a"]["pass"])

    # status preservation for atomic cases in Path A (the T46 failure dimension)
    pa_status_ok = sum(1 for c in atomic if c["path_a"]["judge"].get("status_ok"))
    pa_entity_ok = sum(1 for c in atomic if c["path_a"]["judge"].get("hostname_ok"))

    return {
        "total_cases": n,
        "path_b_passes": pb_pass,
        "path_a_passes": pa_pass,
        "path_b_rate": pb_pass / n if n else 0.0,
        "path_a_rate": pa_pass / n if n else 0.0,
        "atomic_cases": atomic_n,
        "path_b_atomic_passes": pb_atomic,
        "path_a_atomic_passes": pa_atomic,
        "path_b_atomic_rate": pb_atomic / atomic_n if atomic_n else 0.0,
        "path_a_atomic_rate": pa_atomic / atomic_n if atomic_n else 0.0,
        "path_a_status_preserved": pa_status_ok,
        "path_a_status_preserved_rate": pa_status_ok / atomic_n if atomic_n else 0.0,
        "path_a_entity_resolved": pa_entity_ok,
        "path_a_entity_resolved_rate": pa_entity_ok / atomic_n if atomic_n else 0.0,
        "by_case": [
            {
                "id": c["id"],
                "category": c["category"],
                "path_b_pass": c["path_b"]["pass"],
                "path_a_pass": c["path_a"]["pass"],
            }
            for c in cases_results
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Hybrid PoC T46 harness")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cases", default=os.path.join(HERE, "t46_variants.json"))
    parser.add_argument("--out", default=os.path.join(HERE, "results.json"))
    parser.add_argument("--temps", default="0.0,0.7",
                        help="comma-separated temperatures to sweep")
    parser.add_argument("--reps", type=int, default=None,
                        help="override per-case repetition count")
    parser.add_argument("--think", action="store_true", default=False,
                        help="enable thinking mode (default: off)")
    args = parser.parse_args()

    temps = [float(t) for t in args.temps.split(",") if t.strip() != ""]
    cases = load_cases(args.cases)

    results = {
        "meta": {
            "model": args.model,
            "ollama_url": OLLAMA_URL,
            "think": args.think,
            "temperatures": temps,
            "inventory": INVENTORY,
            "note": (
                "Path B = hybrid (Qwen plans -> deterministic resolver/lookup/formatter). "
                "Path A = direct LLM interpretation using the production system prompt. "
                "Path A 'final_answer' for atomic cases is produced from the correct "
                "tool result; entity resolution is measured separately via Path A 'entity'."
            ),
        },
        "temperatures": {},
    }

    per_temp_summary = {}
    for temp in temps:
        key = repr(temp)
        temp_results = []
        for case in cases:
            reps = args.reps if args.reps is not None else case.get("reps", 3)
            case_runs = []
            for _ in range(reps):
                try:
                    r = run_case(case, args.model, temp)
                except Exception as exc:  # noqa: BLE001 - record and continue
                    r = {
                        "id": case["id"],
                        "category": case["category"],
                        "question": case["question"],
                        "expected": case["expected"],
                        "error": str(exc),
                        "path_b": {"pass": False, "error": str(exc)},
                        "path_a": {"pass": False, "error": str(exc)},
                    }
                case_runs.append(r)
            temp_results.append({"case": case["id"], "reps": len(case_runs), "runs": case_runs})
        # collapse per-case runs into pass-rate view for the summary
        flat = []
        for tr in temp_results:
            for run in tr["runs"]:
                flat.append(run)
        per_temp_summary[key] = summarize(flat)
        results["temperatures"][key] = {"summary": per_temp_summary[key], "cases": temp_results}

    results["summary"] = per_temp_summary

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # console summary
    print(f"\nmodel={args.model} think={args.think} temps={temps}")
    for key, s in per_temp_summary.items():
        print(f"\n--- temperature {key} ---")
        print(f"  Path B (hybrid):        {s['path_b_passes']}/{s['total_cases']} "
              f"({100*s['path_b_rate']:.0f}%)")
        print(f"  Path A (direct):        {s['path_a_passes']}/{s['total_cases']} "
              f"({100*s['path_a_rate']:.0f}%)")
        print(f"  Atomic subset: B={s['path_b_atomic_passes']}/{s['atomic_cases']} "
              f"({100*s['path_b_atomic_rate']:.0f}%)  "
              f"A={s['path_a_atomic_passes']}/{s['atomic_cases']} "
              f"({100*s['path_a_atomic_rate']:.0f}%)")
        print(f"  Path A status preserved: {s['path_a_status_preserved']}/{s['atomic_cases']} "
              f"({100*s['path_a_status_preserved_rate']:.0f}%)")
        print(f"  Path A entity resolved:  {s['path_a_entity_resolved']}/{s['atomic_cases']} "
              f"({100*s['path_a_entity_resolved_rate']:.0f}%)")
        for c in s["by_case"]:
            mark_b = "PASS" if c["path_b_pass"] else "FAIL"
            mark_a = "PASS" if c["path_a_pass"] else "FAIL"
            print(f"    [{c['category']:1}] {c['id']:34}  B={mark_b:4}  A={mark_a:4}")

    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

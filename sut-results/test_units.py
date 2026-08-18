#!/usr/bin/env python3
"""Deterministic regression tests for the SUT wiring (no LLM).

Covers:
  1. route taxonomy mapping (request_type -> gold route names)
  2. gold planner schema enum completeness (acceptance contract)
  3. resolver candidate contract against the gold dummy inventory
  4. orchestrator route selection on synthetic (non-LLM) planner outputs
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(os.path.dirname(HERE), "hybrid-gold-v3")
POC = os.path.join(os.path.dirname(HERE), "librenms-hybrid-poc")
sys.path.insert(0, GOLD)
sys.path.insert(0, POC)

import hybrid_poc


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


r = load_module(os.path.join(GOLD, "resolver_candidate_v4.py"), "resolver_under_test")
inventory = json.load(open(os.path.join(GOLD, "dummy_inventory.json"), encoding="utf-8"))

passed = 0
failed = []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print("PASS", name)
    else:
        failed.append(name)
        print("FAIL", name, detail)


# --- 1. route taxonomy mapping ---
for rt, route in [
    ("atomic_fact", "atomic"),
    ("ports", "ports"),
    ("alerts", "alerts"),
    ("events", "events"),
    ("device_set", "device_set"),
    ("investigation", "investigation"),
    ("historical_investigation", "historical_investigation"),
    ("unsupported", "unsupported"),
]:
    check(f"route_map:{rt}", hybrid_poc._ORCH_ROUTE.get(rt) == route, hybrid_poc._ORCH_ROUTE.get(rt))

# --- 2. gold schema enum completeness ---
req = set(hybrid_poc.PLANNING_SCHEMA_GOLD["properties"]["request_type"]["enum"])
need_req = {"atomic_fact", "ports", "alerts", "events", "device_set",
            "investigation", "historical_investigation", "unsupported"}
check("schema.request_type.enum", req == need_req, req)
intent = set(hybrid_poc.PLANNING_SCHEMA_GOLD["properties"]["intent"]["enum"])
need_int = {"device_status", "device_ports", "device_alerts", "device_events",
            "device_set", "investigation", "historical_status", "unsupported", "unknown"}
check("schema.intent.enum", intent == need_int, intent)
check("schema.device_query", hybrid_poc.PLANNING_SCHEMA_GOLD["properties"]["device_query"]["type"] == ["string", "null"])
check("schema.required_present", {
    "request_type", "intent", "device_query"
} == set(hybrid_poc.PLANNING_SCHEMA_GOLD["required"]))

# --- 3. resolver contract (single-device) ---
def single(ref, exp_outcome, exp_reason=None, exp_hostname=None, exp_cands=None):
    res = r.resolve_device(ref, inventory)
    ok = res.get("outcome") == exp_outcome
    if exp_reason is not None:
        ok = ok and res.get("reason") == exp_reason
    if exp_hostname is not None:
        ok = ok and (res.get("device") or {}).get("hostname") == exp_hostname
    if exp_cands is not None:
        obs = {d.get("hostname") for d in (res.get("candidates") or [])}
        ok = ok and obs == set(exp_cands)
    return ok, res


for ref, out, reason, host, cands in [
    ("J9774A", "resolved", "metadata", "lab-j9774a-01", None),
    ("2530-8G-PoEP", "resolved", "metadata", "lab-j9774a-01", None),
    ("HP ProCurve J9774A 2530-8G-PoEP", "resolved", "metadata", "lab-j9774a-01", None),
    ("lab j9774a 01", "resolved", "normalized", "lab-j9774a-01", None),
    ("lab-j9774s-01", "resolved", "typo", "lab-j9774a-01", None),
    ("lab8g", "resolved", "alias", "lab-j9774a-01", None),
    ("J4850A", "ambiguous", "ambiguous", None, ["lab-j4850a-01", "lab-j4850a-02"]),
    ("ZZ999", "no_match", "no_match", None, None),
    ("J9772A", "ambiguous", "ambiguous", None, ["lab-j9772a-01", "lab-j9772a-02"]),
    ("J9780A", "resolved", "metadata", "lab-j9780a-01", None),
    ("J9776A", "resolved", "metadata", "lab-j9776a-01", None),
    ("J9783A", "resolved", "metadata", "lab-j9783a-01", None),
    ("25", "no_match", "no_match", None, None),
]:
    ok, res = single(ref, out, reason, host, cands)
    check(f"resolver.single:{ref}", ok, json.dumps(res, ensure_ascii=False, default=str)[:220])


# --- 3b. device-set contract ---
def dset(ref, exp_skus):
    res = r.resolve_device_set(ref, inventory)
    if res.get("outcome") != "resolved":
        return False, res
    obs = {m.get("sku") for m in (res.get("models") or [])}
    return obs == set(exp_skus), res


for ref, skus in [
    ("J9772A", ["J9772A"]),
    ("2530 48G", ["J9772A", "J9775A"]),
    ("48 port PoE ProCurve", ["J9772A", "JL357A"]),
    ("2540-48G-PoE+-4SFP+", ["JL357A"]),
    ("2530-8-PoEP", ["J9780A"]),              # GOLD-036 regression: literal-exact only
    ("2530-8-PoE", ["J9774A", "J9780A"]),     # planner must not truncate; if it does, this is the result
    ("J9783A", ["J9783A"]),
    ("J9775A", ["J9775A"]),
]:
    ok, res = dset(ref, skus)
    check(f"resolver.set:{ref}", ok, json.dumps(res, ensure_ascii=False, default=str)[:220])

# --- 4. formatters ---
check("format_atomic.up", r.format_atomic("lab-j9774a-01", 1) == "lab-j9774a-01 şu anda çalışıyor.", r.format_atomic("lab-j9774a-01", 1))
check("format_atomic.down", r.format_atomic("lab-j9780a-01", 0) == "lab-j9780a-01 şu anda çalışmıyor.", r.format_atomic("lab-j9780a-01", 0))
cl = r.format_clarification([{"hostname": "a"}, {"hostname": "b"}])
check("format_clarification", "Adaylar: a, b" in cl, cl)
ds = r.format_device_set({"outcome": "resolved", "models": [], "devices": [{"hostname": "h1", "status": 1}]})
check("format_device_set", "h1" in ds, ds)

print(f"\n{passed} passed, {len(failed)} failed")
if failed:
    print("FAILED:", failed)
    sys.exit(1)

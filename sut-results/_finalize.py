#!/usr/bin/env python3
"""Finalize: complete summaries + merged external judge export + RUN_REPORT.md."""
import json
import io
import time

ROOT = "sut-results"

def load(p):
    return json.load(open(p, encoding="utf-8"))

gold = load(f"{ROOT}/sut_gold_results.json")
gen = load(f"{ROOT}/sut_generated_results.json")
legacy = load(f"{ROOT}/sut_legacy_results.json")

def dims(payload):
    return {k: {"pass": v["pass"], "total": v["total"]} for k, v in sorted(payload["summary"]["dimensions"].items())}

def analyze(payload, suite):
    results = payload["results"]
    total = len(results)
    passed = sum(1 for r in results if r["deterministic_pass"])
    atomic = [r for r in results if r["expected"].get("route") == "atomic"]
    inv = [r for r in results if r["expected"].get("route") in ("investigation", "historical_investigation")]
    clar = [r for r in results if r["expected"].get("route") == "clarification"]
    nomatch = [r for r in results if r["expected"].get("route") == "no_match"]
    exec_cases = [r for r in results if r["expected"].get("route") in
                  ("atomic", "ports", "alerts", "events", "investigation", "historical_investigation")]
    atomic_avoid = sum(1 for r in atomic if not bool((r.get("observed") or {}).get("synthesis_llm_called")))
    atomic_planner = sum(1 for r in atomic if bool((r.get("observed") or {}).get("planner_llm_called")))
    inv_called = sum(1 for r in inv if bool((r.get("observed") or {}).get("synthesis_llm_called")))
    wrong = sum(1 for r in clar
                if (r.get("observed") or {}).get("route") != "clarification"
                and (r.get("observed") or {}).get("resolver_output", {}).get("outcome") == "resolved")
    fab = sum(1 for r in nomatch
              if (r.get("observed") or {}).get("resolver_output", {}).get("outcome") == "resolved")
    call_ok = arg_ok = 0
    call_fail = []
    for r in exec_cases:
        obs = r.get("observed") or {}
        actual = [c.get("tool") for c in obs.get("tool_calls", [])]
        req = r["expected"].get("execution", {}).get("required_calls", [])
        forb = r["expected"].get("execution", {}).get("forbidden_calls", [])
        if (set(req) <= set(actual)) and not (set(forb) & set(actual)):
            call_ok += 1
        else:
            call_fail.append((r["id"], actual))
        resolved = (obs.get("resolver_output") or {}).get("device") or {}
        aok = True
        if actual and actual[0] == "get_device":
            args = obs.get("tool_calls", [])[0].get("args", {})
            aok = aok and (args.get("hostname") == resolved.get("hostname")
                           or args.get("device_id") == resolved.get("device_id"))
        did = resolved.get("device_id")
        if did is not None:
            for c in obs.get("tool_calls", [])[1:]:
                if c.get("tool") in ("get_ports", "get_alerts", "get_events"):
                    aok = aok and c.get("args", {}).get("device_id") == did
        if aok:
            arg_ok += 1
    ext = sum(1 for r in results if r.get("external_judge_required"))
    return {
        "suite": suite,
        "mode": payload["summary"]["mode"],
        "adapter": payload["summary"]["adapter"],
        "planner_schema": (results[0].get("observed") or {}).get("planner_output", {}).get("planner_schema") if results else None,
        "deterministic_pass": passed,
        "deterministic_total": total,
        "dimensions": dims(payload),
        "atomic_cases": len(atomic),
        "atomic_avoided_synthesis_llm": atomic_avoid,
        "atomic_llm_avoidance_rate": round(100.0 * atomic_avoid / len(atomic), 2) if atomic else None,
        "atomic_planner_llm_used": atomic_planner,
        "investigation_cases": len(inv),
        "investigation_synthesis_llm_called": inv_called,
        "investigation_llm_invocation_rate": round(100.0 * inv_called / len(inv), 2) if inv else None,
        "clarification_cases": len(clar),
        "ambiguous_wrong_device_selection_count": wrong,
        "no_match_cases": len(nomatch),
        "no_match_fabricated_device_count": fab,
        "execution_cases": len(exec_cases),
        "exact_backend_tool_call_accuracy": call_ok,
        "exact_backend_tool_call_accuracy_rate": round(100.0 * call_ok / len(exec_cases), 2) if exec_cases else None,
        "exact_tool_call_failures": call_fail,
        "backend_tool_argument_accuracy": arg_ok,
        "backend_tool_argument_accuracy_rate": round(100.0 * arg_ok / len(exec_cases), 2) if exec_cases else None,
        "external_judge_pending": ext,
        "planner_failures": sum(1 for r in results if (r.get("observed") or {}).get("planner_failure")),
        "llm_usage": {
            "planner_llm_called_total": sum(1 for r in results if bool((r.get("observed") or {}).get("planner_llm_called"))),
            "synthesis_llm_called_total": sum(1 for r in results if bool((r.get("observed") or {}).get("synthesis_llm_called"))),
        },
    }

gold_sum = analyze(gold, "hybrid-gold-v3 (Gold 40)")
gen_sum = analyze(gen, "hybrid-generated-v3 (Generated 16)")

# ---------- legacy summary ----------
ls = legacy["summary"]
legacy_sum = {
    "suite": "librenms-prompt-eval legacy 56-suite (frozen)",
    "runner": "eval_runner.py (unchanged)",
    "model": ls.get("model"),
    "think": ls.get("think"),
    "system_sha": ls.get("system_sha"),
    "deterministic_pass": ls.get("passed"),
    "deterministic_total": ls.get("total"),
    "deterministic_rate": ls.get("pass_rate"),
    "judge_used": False,
    "judge_note": "Secondary semantic judge step skipped on purpose: local Qwen must not judge itself (" 
                  "no-local-judge policy). Deterministic grading is identical to the frozen runner.",
    "previous_recorded_final": {"total": 56, "passed": 55, "system_sha": "d320cbd8e984"},
    "failing_ids": [r["id"] for r in legacy["results"] if not r["deterministic_pass"]],
}

# ---------- merge external judge exports ----------
gold_ext = [json.loads(l) for l in io.open(f"{ROOT}/external_judge_cases.jsonl", encoding="utf-8") if l.strip()]
gen_ext = [json.loads(l) for l in io.open(f"{ROOT}/external_judge_cases_generated.jsonl", encoding="utf-8") if l.strip()]
# gold file currently written by run_gold; keep a per-suite copy as *_gold.jsonl
io.open(f"{ROOT}/external_judge_cases_gold.jsonl", "w", encoding="utf-8").writelines(
    json.dumps(x, ensure_ascii=False) + "\n" for x in gold_ext)
merged = gold_ext + gen_ext
io.open(f"{ROOT}/external_judge_cases.jsonl", "w", encoding="utf-8").writelines(
    json.dumps(x, ensure_ascii=False) + "\n" for x in merged)

# ---------- write summaries ----------
io.open(f"{ROOT}/sut_gold_summary.json", "w", encoding="utf-8").write(
    json.dumps(gold_sum, ensure_ascii=False, indent=2))
io.open(f"{ROOT}/sut_generated_summary.json", "w", encoding="utf-8").write(
    json.dumps(gen_sum, ensure_ascii=False, indent=2))
io.open(f"{ROOT}/sut_legacy_summary.json", "w", encoding="utf-8").write(
    json.dumps(legacy_sum, ensure_ascii=False, indent=2))

print(json.dumps({"gold": gold_sum, "generated": gen_sum, "legacy": legacy_sum,
                  "external_judge_records": len(merged)}, ensure_ascii=False, indent=2)[:4000])

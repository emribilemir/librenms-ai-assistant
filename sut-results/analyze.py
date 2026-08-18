#!/usr/bin/env python3
"""Compute the section-16 metrics from a run_gold-style results payload."""
import json, sys

def hostname(d):
    return (d or {}).get("hostname")

def main(path):
    payload = json.load(open(path, encoding="utf-8"))
    results = payload["results"]
    cases = [r for r in results]

    total = len(cases)
    passed = sum(1 for r in cases if r["deterministic_pass"])

    # dimension coverage
    dims = {}
    for r in cases:
        for d in r.get("covers", []):
            dims.setdefault(d, {"total": 0, "pass": 0})
            dims[d]["total"] += 1
            if r["deterministic_pass"]:
                dims[d]["pass"] += 1

    # atomic LLM avoidance: atomic-expected cases where synthesis LLM was NOT used
    atomic_cases = [r for r in cases if r["expected"].get("route") == "atomic"]
    atomic_avoid = sum(1 for r in atomic_cases
                       if not bool((r.get("observed") or {}).get("synthesis_llm_called")))
    atomic_avoid_llm = sum(1 for r in atomic_cases
                           if bool((r.get("observed") or {}).get("planner_llm_called")))

    # investigation LLM invocation: investigation/historical expected with synthesis called
    inv_expected = [r for r in cases if r["expected"].get("route") in ("investigation", "historical_investigation")]
    inv_called = sum(1 for r in inv_expected
                     if bool((r.get("observed") or {}).get("synthesis_llm_called")))

    # ambiguous wrong-device selection: expected clarification cases where route != clarification
    clar = [r for r in cases if r["expected"].get("route") == "clarification"]
    wrong_device = sum(1 for r in clar
                       if (r.get("observed") or {}).get("route") != "clarification"
                       and (r.get("observed") or {}).get("resolver_output", {}).get("outcome") in ("resolved",))
    # no-match fabricated device: expected no_match where a device was resolved
    nomatch = [r for r in cases if r["expected"].get("route") == "no_match"]
    fabricated = sum(1 for r in nomatch
                     if (r.get("observed") or {}).get("resolver_output", {}).get("outcome") == "resolved")

    # exact backend tool-call accuracy + argument accuracy (on execution-expected cases)
    exec_routes = {"atomic", "ports", "alerts", "events", "investigation", "historical_investigation"}
    exec_cases = [r for r in cases if r["expected"].get("route") in exec_routes]
    call_ok = arg_ok = 0
    call_fail = []
    arg_fail = []
    for r in exec_cases:
        obs = r.get("observed") or {}
        actual = [c.get("tool") for c in obs.get("tool_calls", [])]
        req = r["expected"].get("execution", {}).get("required_calls", [])
        forb = r["expected"].get("execution", {}).get("forbidden_calls", [])
        exact_ok = (set(req) <= set(actual)) and not (set(forb) & set(actual))
        if exact_ok:
            call_ok += 1
        else:
            call_fail.append((r["id"], actual, req))
        # argument accuracy: first call get_device uses resolved identity; downstream device_id
        resolved = (obs.get("resolver_output") or {}).get("device") or {}
        aok = True
        if actual and actual[0] == "get_device":
            args = obs.get("tool_calls", [])[0].get("args", {})
            aok = aok and (args.get("hostname") == resolved.get("hostname") or args.get("device_id") == resolved.get("device_id"))
        did = resolved.get("device_id")
        if did is not None:
            for c in obs.get("tool_calls", [])[1:]:
                if c.get("tool") in ("get_ports", "get_alerts", "get_events"):
                    aok = aok and c.get("args", {}).get("device_id") == did
        if aok:
            arg_ok += 1
        else:
            arg_fail.append(r["id"])

    ext_pending = sum(1 for r in cases if r.get("external_judge_required"))

    summary = {
        "suite": payload.get("summary", {}).get("suite"),
        "adapter": payload.get("summary", {}).get("adapter"),
        "mode": payload.get("summary", {}).get("mode"),
        "planner_schema": (cases[0].get("observed") or {}).get("planner_output", {}).get("planner_schema") if cases else None,
        "deterministic_pass": passed,
        "deterministic_total": total,
        "dimensions": {k: {"pass": v["pass"], "total": v["total"]} for k, v in sorted(dims.items())},
        "atomic_cases": len(atomic_cases),
        "atomic_synthesis_llm_avoided": atomic_avoid,
        "atomic_planner_llm_used": atomic_avoid_llm,
        "investigation_expected": len(inv_expected),
        "investigation_synthesis_llm_called": inv_called,
        "clarification_expected": len(clar),
        "wrong_device_selection_count": wrong_device,
        "no_match_expected": len(nomatch),
        "fabricated_device_count": fabricated,
        "execution_expected": len(exec_cases),
        "exact_tool_call_accuracy": call_ok,
        "tool_call_failures": call_fail,
        "tool_argument_accuracy": arg_ok,
        "tool_argument_failures": arg_fail,
        "external_judge_pending": ext_pending,
        "planner_failures": sum(1 for r in cases if (r.get("observed") or {}).get("planner_failure")),
        "llm_called_harness_counts": {
            "synthesis_true": sum(1 for r in cases if bool((r.get("observed") or {}).get("synthesis_llm_called"))),
            "planner_true": sum(1 for r in cases if bool((r.get("observed") or {}).get("planner_llm_called"))),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main(sys.argv[1])

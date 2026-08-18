#!/usr/bin/env python3
"""Build sut_gold_failures.md: final-run failures + first-run divergence report."""
import json

def build_first_run_failures(path="sut-results/sut_gold_firstrun_raw.json"):
    D = json.load(open(path, encoding="utf-8"))
    lines = [
        "# First real-SUT run (as-is planner taxonomy, SUT_PLANNER_SCHEMA=poc): preserved divergences",
        "",
        "This is the RAW first run of the real local SUT against gold_cases.json, before any",
        "planner-taxonomy fix. It was NOT used to change gold expectations; the divergences",
        "below are the evidence that drove the general planner-taxonomy fix.",
        "",
        f"First-run deterministic: {sum(r['deterministic_pass'] for r in D['results'])}/{len(D['results'])}",
        "",
    ]
    for r in D["results"]:
        if r["deterministic_pass"]:
            continue
        obs = r.get("observed") or {}
        exp = r.get("expected") or {}
        plan = (obs.get("planner_output") or {}).get("plan")
        reso = obs.get("resolver_output")
        route = obs.get("route")
        tools = [c.get("tool") for c in obs.get("tool_calls", [])]
        synth = bool(obs.get("synthesis_llm_called"))
        fails = [c for c in r.get("deterministic_assertions", []) if not c["pass"]]
        first_div = fails[0]["name"] if fails else "none"
        lines += [
            f"## {r['id']}",
            f"- Query: `{r['query']}`",
            f"- Expected behavior: route={exp.get('route')}, intent={exp.get('intent')}, "
            f"resolution={json.dumps(exp.get('resolution'), ensure_ascii=False)}, "
            f"execution={json.dumps(exp.get('execution'), ensure_ascii=False)}",
            f"- Observed planner output: {json.dumps(plan, ensure_ascii=False)}",
            f"- Observed resolver output: {json.dumps(reso, ensure_ascii=False)[:400]}",
            f"- Observed route: {route}",
            f"- Actual tool calls: {tools}",
            f"- LLM called (synthesis): {synth} (planner LLM: {bool(obs.get('planner_llm_called'))})",
            f"- First point of divergence: {first_div}",
            f"- Final answer: {str(obs.get('final_answer'))[:300]}",
            "- Failed assertions:",
        ]
        for c in fails:
            lines.append(f"  - {c['name']}: expected `{c.get('expected')}`, observed `{c.get('observed')}`")
        lines.append("")
    return "\n".join(lines)

def build_final(path="sut-results/sut_gold_results.json"):
    D = json.load(open(path, encoding="utf-8"))
    s = D["summary"]
    fails = [r for r in D["results"] if not r["deterministic_pass"]]
    lines = [
        "# hybrid-gold-v3 — real SUT Gold results",
        "",
        f"Adapter: {s.get('adapter')}  Mode: {s.get('mode')}",
        f"Deterministic: {s.get('deterministic_pass')}/{s.get('deterministic_total')}",
        "",
    ]
    if fails:
        for r in fails:
            lines.append(f"## {r['id']}")
            lines.append(f"- Query: `{r['query']}`")
            for c in r.get("deterministic_assertions", []):
                if not c["pass"]:
                    lines.append(f"  - {c['name']}: expected `{c.get('expected')}`, observed `{c.get('observed')}`")
    else:
        lines.append("No deterministic failures on the final run (planner_schema=gold).")
        lines.append("First-run divergences with the as-is planner are preserved in the appendix below.")
    return "\n".join(lines)

if __name__ == "__main__":
    import io
    final = build_final()
    first = build_first_run_failures()
    io.open("sut-results/sut_gold_failures.md", "w", encoding="utf-8").write(final + "\n\n---\n\n" + first + "\n")
    gen = json.load(open("sut-results/sut_generated_results.json", encoding="utf-8"))
    fails = [r for r in gen["results"] if not r["deterministic_pass"]]
    glines = [
        "# hybrid-gold-v3 — real SUT generated robustness results",
        "",
        f"Deterministic: {gen['summary']['deterministic_pass']}/{gen['summary']['deterministic_total']}",
        "",
    ]
    if fails:
        for r in fails:
            glines.append(f"## {r['id']}")
            glines.append(f"- Query: `{r['query']}`")
            for c in r.get("deterministic_assertions", []):
                if not c["pass"]:
                    glines.append(f"  - {c['name']}: expected `{c.get('expected')}`, observed `{c.get('observed')}`")
    else:
        glines.append("No deterministic failures (planner_schema=gold).")
    io.open("sut-results/sut_generated_failures.md", "w", encoding="utf-8").write("\n".join(glines) + "\n")
    print("failures md files written")

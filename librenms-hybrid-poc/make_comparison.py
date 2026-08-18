#!/usr/bin/env python3
"""Generate comparison_v2.md from results_v2.json."""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def hostnames(result):
    if result.get("device"):
        return [result["device"]["hostname"]]
    return [c["hostname"] for c in (result.get("candidates") or [])]


def main():
    data = json.load(io.open(os.path.join(HERE, "results_v2.json"), encoding="utf-8"))
    out = []
    w = out.append

    meta = data.get("meta", {})
    w("# Hybrid PoC v2 — comparison")
    w("")
    w("Generated from results_v2.json (model=%s, think=%s)." % (meta.get("model"), meta.get("think")))
    w("")

    per_temp = data.get("summary", {})
    w("## Headline results")
    w("")
    w("| temperature | Path B (hybrid) | Path A (direct) |")
    w("|---|---|---|")
    for key, s in sorted(per_temp.items()):
        w("| %s | %d/%d (%.0f%%) | %d/%d (%.0f%%) |" % (
            key, s["path_b_passes"], s["total_cases"], 100 * s["path_b_rate"],
            s["path_a_passes"], s["total_cases"], 100 * s["path_a_rate"]))
    w("")

    # reason distribution at temp 0.0
    w("## Resolution reasons (Path B, temperature 0.0)")
    w("")
    reason_counts = {}
    for key, block in data.get("temperatures", {}).items():
        if key != "0.0":
            continue
        for case_group in block.get("cases", []):
            for run in case_group.get("runs", []):
                pb = run.get("path_b", {})
                reason = pb.get("reason") or pb.get("route")
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
    w("| reason/route | count |")
    w("|---|---|")
    for k in sorted(reason_counts, key=lambda x: -reason_counts[x]):
        w("| %s | %d |" % (k, reason_counts[k]))
    w("")

    # new-case detail at temp 0.0
    w("## New typo/metadata cases (temperature 0.0)")
    w("")
    w("| id | question | expected route | Path B | reason |")
    w("|---|---|---|---|---|")
    for key, block in data.get("temperatures", {}).items():
        if key != "0.0":
            continue
        for case_group in block.get("cases", []):
            case_id = case_group.get("case", "")
            if not case_id.startswith("V2-"):
                continue
            run = case_group["runs"][0]
            exp = run.get("expected", {})
            pb = run.get("path_b", {})
            w("| %s | %s | %s | %s | %s |" % (
                case_id, run.get("question"), exp.get("route"),
                "PASS" if pb.get("pass") else "FAIL", pb.get("reason")))
    w("")

    # per-temperature new-case pass summary
    w("## New-case Path B pass rate")
    w("")
    w("| temperature | new cases passed |")
    w("|---|---|")
    for key, block in data.get("temperatures", {}).items():
        total = 0
        passed = 0
        for case_group in block.get("cases", []):
            if not case_group.get("case", "").startswith("V2-"):
                continue
            for run in case_group.get("runs", []):
                total += 1
                if run.get("path_b", {}).get("pass"):
                    passed += 1
        w("| %s | %d/%d |" % (key, passed, total))
    w("")

    io.open(os.path.join(HERE, "comparison_v2.md"), "w", encoding="utf-8").write("\n".join(out))
    print("wrote comparison_v2.md")


if __name__ == "__main__":
    main()

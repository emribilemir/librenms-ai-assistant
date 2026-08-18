#!/usr/bin/env python3
"""Offline resolver contract test: resolver_candidate_v4 vs every gold expected resolution.

No LLM. Verifies the deterministic layer satisfies the gold resolution contract.
"""
import json, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(os.path.dirname(HERE), "hybrid-gold-v3")
sys.path.insert(0, GOLD)

import importlib.util
spec = importlib.util.spec_from_file_location("resolver_v4", os.path.join(GOLD, "resolver_candidate_v4.py"))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

inventory = json.load(open(os.path.join(GOLD, "dummy_inventory.json"), encoding="utf-8"))
gold = json.load(open(os.path.join(GOLD, "gold_cases.json"), encoding="utf-8"))

# Map planner device_query candidates we expect per case (from case queries).
device_query = None  # adapter decides; here we test resolver on plausible queries

fails = []
n = 0
for case in gold["cases"]:
    exp = case["expected"]
    er = exp.get("resolution")
    if not er:
        continue
    n += 1
    # choose the resolution path per resolver_mode
    if exp.get("resolver_mode") == "set":
        res = r.resolve_device_set(case["query"], inventory)
    else:
        res = r.resolve_device(case["query"], inventory)
    checks = []
    checks.append(("outcome", res.get("outcome") == er.get("outcome"), er.get("outcome"), res.get("outcome")))
    if er.get("reason") is not None:
        checks.append(("reason", res.get("reason") == er["reason"], er["reason"], res.get("reason")))
    if er.get("hostname") is not None:
        obs = (res.get("device") or {}).get("hostname")
        checks.append(("hostname", obs == er["hostname"], er["hostname"], obs))
    if er.get("candidates_include") is not None:
        obs = {d.get("hostname") for d in (res.get("candidates") or [])}
        need = set(er["candidates_include"])
        checks.append(("candidates", need.issubset(obs), sorted(need), sorted(obs)))
    if er.get("model_skus") is not None:
        obs = {m.get("sku") for m in (res.get("models") or [])}
        need = set(er["model_skus"])
        checks.append(("model_skus", obs == need, sorted(need), sorted(obs)))
    bad = [c for c in checks if not c[1]]
    if bad:
        fails.append({"id": case["id"], "query": case["query"], "mode": exp.get("resolver_mode"), "fails": bad})
    print(("PASS" if not bad else "FAIL"), case["id"], res.get("outcome"), res.get("reason"), (res.get("device") or {}).get("hostname"))

print(f"\nResolver contract: {n - len(fails)}/{n} pass (query-as-reference mode)")
for f in fails:
    print(json.dumps(f, ensure_ascii=False))

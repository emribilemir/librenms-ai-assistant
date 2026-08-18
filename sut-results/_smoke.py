#!/usr/bin/env python3
"""Smoke: verify the thin adapter + REAL orchestrator pipeline end-to-end."""
import importlib.util, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(os.path.dirname(HERE), "hybrid-gold-v3")
sys.path.insert(0, GOLD)

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

from dummy_backend import SpyBackend

r = load_module(os.path.join(GOLD, "resolver_candidate_v4.py"), "resolver_under_test")
adapter_mod = load_module(os.path.join(HERE, "sut_adapter.py"), "sut_adapter")
inventory = json.load(open(os.path.join(GOLD, "dummy_inventory.json"), encoding="utf-8"))
backend = SpyBackend(os.path.join(GOLD, "dummy_inventory.json"), os.path.join(GOLD, "dummy_backend_data.json"))
adapter = adapter_mod.SUTAdapter(r, inventory, backend)

queries = [
    "J9774A up mı?",
    "lab-j9774s-01 up mı?",
    "J9774A up gözüküyor ama ben tepki alamıyorum.",
    "J9772A cihazlarını göster",
    "J4850A up mı?",
    "J9774A cihazını reboot et",
]
for q in queries:
    tr = adapter.run_query(q, {"id": "smoke", "query": q})
    print(json.dumps({
        "query": q,
        "route": tr["route"],
        "intent": tr["intent"],
        "planner": (tr.get("planner_output") or {}).get("plan"),
        "resolver_outcome": (tr.get("resolver_output") or {}).get("outcome"),
        "tools": [c["tool"] for c in tr["tool_calls"]],
        "llm_called": tr["llm_called"],
        "planner_llm": tr["planner_llm_called"],
        "answer": (tr["final_answer"] or "")[:120],
        "planner_failure": tr.get("planner_failure"),
    }, ensure_ascii=False))
    sys.stdout.flush()

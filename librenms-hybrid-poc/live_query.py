#!/usr/bin/env python3
"""Run the gold hybrid pipeline against the real read-only LibreNMS API."""

import importlib.util
import json
import sys
from pathlib import Path

import hybrid_poc
from librenms_backend import LibreNMSBackend

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GOLD = ROOT / "librenms-hybrid-poc" / "hybrid-gold-v3"
INVENTORY_PATH = GOLD / "dummy_inventory.json"
RESOLVER_PATH = GOLD / "resolver_candidate_v5.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver_v5 = _load_module("resolver_v5_live", RESOLVER_PATH)
with INVENTORY_PATH.open(encoding="utf-8") as stream:
    INVENTORY = json.load(stream)


def run_live_query(query, *, backend=None, model=hybrid_poc.DEFAULT_MODEL):
    if backend is None:
        backend = LibreNMSBackend()
    if hasattr(backend, "reset_trace"):
        backend.reset_trace()
    return hybrid_poc.orchestrate(
        query,
        inventory=INVENTORY,
        backend=backend,
        model=model,
        planner_schema="gold",
        resolver_module=resolver_v5,
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print('Usage: python3 live_query.py "lab-j9775a-01 açık mı?"', file=sys.stderr)
        return 2
    trace = run_live_query(" ".join(argv))
    print(json.dumps(trace, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

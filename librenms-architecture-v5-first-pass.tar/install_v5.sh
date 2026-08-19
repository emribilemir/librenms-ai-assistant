#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$PWD}"
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

V4="$ROOT/hybrid-gold-v3/resolver_candidate_v4.py"
POC="$ROOT/librenms-hybrid-poc/hybrid_poc.py"
EXPECTED_V4="f925a75fe86d2b3a99040b4b608c93effc782cac9f60848d339c5a2fb62ba6f4"
EXPECTED_POC="49cbd734346cb178c06dd3d616c65a9a29e2f7d707b004828998b04f293f60b4"

sha256_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

[[ -f "$V4" ]] || { echo "missing: $V4" >&2; exit 2; }
[[ -f "$POC" ]] || { echo "missing: $POC" >&2; exit 2; }

ACTUAL_V4="$(sha256_file "$V4")"
ACTUAL_POC="$(sha256_file "$POC")"
[[ "$ACTUAL_V4" == "$EXPECTED_V4" ]] || {
  echo "REFUSE: resolver_candidate_v4.py hash mismatch" >&2
  echo "expected $EXPECTED_V4" >&2
  echo "actual   $ACTUAL_V4" >&2
  exit 3
}
[[ "$ACTUAL_POC" == "$EXPECTED_POC" ]] || {
  echo "REFUSE: hybrid_poc.py baseline hash mismatch" >&2
  echo "expected $EXPECTED_POC" >&2
  echo "actual   $ACTUAL_POC" >&2
  echo "Do not force-apply. Rebase the patch deliberately against the current file." >&2
  exit 4
}

install -m 0644 "$BUNDLE_DIR/hybrid-gold-v3/catalog_ingest.py" \
  "$ROOT/hybrid-gold-v3/catalog_ingest.py"
install -m 0644 "$BUNDLE_DIR/hybrid-gold-v3/resolver_candidate_v5.py" \
  "$ROOT/hybrid-gold-v3/resolver_candidate_v5.py"
install -m 0644 "$BUNDLE_DIR/librenms-hybrid-poc/planner_v2.py" \
  "$ROOT/librenms-hybrid-poc/planner_v2.py"

python3 - "$POC" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"REFUSE: patch anchor {label!r} count={count}, expected 1")
    text = text.replace(old, new, 1)

replace_once(
    "import resolver\n",
    "import resolver\nimport planner_v2\n",
    "planner import",
)

replace_once(
    '        "device_query": {"type": ["string", "null"]},\n'
    '    },\n'
    '    "required": ["request_type", "intent", "device_query"],\n'
    '}\n\n'
    'def _gold_planning_base():',
    '        "device_query": {"type": ["string", "null"]},\n'
    '        "device_filters": planner_v2.DEVICE_FILTER_SCHEMA,\n'
    '    },\n'
    '    "required": ["request_type", "intent", "device_query", "device_filters"],\n'
    '}\n\n'
    'def _gold_planning_base():',
    "gold schema",
)

replace_once(
    'PLANNING_SYSTEM_GOLD = _gold_planning_base() + GOLD_PLANNING_RULES\n',
    '''PLANNING_SYSTEM_GOLD = _gold_planning_base() + GOLD_PLANNING_RULES + """

Structured device filter contract:
- EVERY output must include device_filters with exactly these semantic fields:
  brand, family, port_count, poe.
- null means the user did not constrain that property. null is NOT false.
- poe=false means the user explicitly requested non-PoE devices.
- For non-device_set routes, all device_filters fields must be null.
- For device_set, put property constraints in device_filters. device_query is
  only an explicit hostname/SKU/model reference and may be null for a
  feature-only search.
- Do not copy the whole natural-language query into device_query just so the
  resolver can parse it again.

Examples:
User: "48 port PoE ProCurve switchleri göster"
-> {"request_type":"device_set","intent":"device_set","device_query":null,
    "device_filters":{"brand":"ProCurve","family":null,"port_count":48,"poe":true}}
User: "poesiz 48 port 2530ları göster"
-> {"request_type":"device_set","intent":"device_set","device_query":null,
    "device_filters":{"brand":null,"family":"2530","port_count":48,"poe":false}}
User: "J9774A up mı?"
-> {"request_type":"atomic_fact","intent":"device_status","device_query":"J9774A",
    "device_filters":{"brand":null,"family":null,"port_count":null,"poe":null}}
"""
''',
    "gold planner contract",
)

old_planner = '''    # 1) planner: REAL Qwen structured output
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
    timing["planner_ms"] = round(ms, 1)
    plan = parse_json_obj(content)
    planner_output = {
        "planner_schema": planner_schema,
        "plan": plan,
        "raw": {"content": content, "done_reason": reason},
    }
'''
new_planner = '''    # 1) planner: deterministic-first for catalog/device-set constraints.
    # All other requests fall back to the REAL Qwen structured planner.
    t0 = time.time()
    deterministic_plan = None
    if planner_schema == "gold":
        deterministic_plan = planner_v2.try_deterministic_device_set_plan(
            query, resolver_module, inventory
        )

    if deterministic_plan is not None:
        plan = planner_v2.normalize_plan_filters(deterministic_plan)
        content = json.dumps(plan, ensure_ascii=False)
        reason = "deterministic"
        ms = 0.0
    else:
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
        if planner_schema == "gold" and isinstance(plan, dict):
            plan = planner_v2.normalize_plan_filters(plan)
    timing["planner_ms"] = round(ms, 1)
    planner_output = {
        "planner_schema": planner_schema,
        "plan": plan,
        "raw": {
            "content": content,
            "done_reason": reason,
            "method": "deterministic" if deterministic_plan is not None else "llm",
        },
    }
'''
replace_once(old_planner, new_planner, "orchestrator planner")

replace_once(
    '''    rt = plan.get("request_type")
    intent = plan.get("intent")
    dq = plan.get("device_query")
    route = _ORCH_ROUTE.get(rt, "unknown")
    if not dq and route != "unsupported":
        dq = query
''',
    '''    rt = plan.get("request_type")
    intent = plan.get("intent")
    dq = plan.get("device_query")
    device_filters = plan.get("device_filters") if planner_schema == "gold" else None
    route = _ORCH_ROUTE.get(rt, "unknown")
    # A feature-only device_set is intentionally allowed to have no identity
    # reference. Do not feed its raw natural-language query back to the resolver.
    if not dq and route not in ("unsupported", "device_set"):
        dq = query
''',
    "device query ownership",
)

replace_once(
    '''    elif route == "device_set":
        res = resolver_module.resolve_device_set(dq, inventory)
        if res.get("outcome") == "no_match":
            route = "no_match"
''',
    '''    elif route == "device_set":
        if hasattr(resolver_module, "planner_catalog_context"):
            res = resolver_module.resolve_device_set(
                dq, inventory, filters=device_filters
            )
        else:
            # Compatibility only for frozen pre-v5 resolver runs.
            res = resolver_module.resolve_device_set(dq, inventory)
        if res.get("outcome") == "no_match":
            route = "no_match"
''',
    "structured device-set resolver call",
)

path.write_text(text, encoding="utf-8")
PY

python3 -m py_compile \
  "$ROOT/hybrid-gold-v3/catalog_ingest.py" \
  "$ROOT/hybrid-gold-v3/resolver_candidate_v5.py" \
  "$ROOT/librenms-hybrid-poc/planner_v2.py" \
  "$ROOT/librenms-hybrid-poc/hybrid_poc.py"

AFTER_V4="$(sha256_file "$V4")"
[[ "$AFTER_V4" == "$EXPECTED_V4" ]] || {
  echo "REFUSE: frozen v4 changed during install" >&2
  exit 5
}

echo "Applied architecture v5 first pass."
echo "Frozen resolver v4 SHA preserved: $AFTER_V4"
echo "Next: inspect git diff, run existing suites unchanged, then commit the product change."

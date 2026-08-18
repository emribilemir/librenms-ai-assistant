# LibreNMS hybrid-gold-v3

`hybrid-gold-v3` is the corrected architecture acceptance suite for the LibreNMS natural-language hybrid PoC.

## Source truth

The uploaded Excel contains only `Brand` and `Model` columns. It has 50 rows and 8 unique HP ProCurve model identities. It does **not** contain real hostnames, device IDs, status, ports, alerts, or events.

Therefore:

- Real source-backed identifiers in tests: `J4850A`, `J9772A`, `J9774A`, `J9775A`, `J9776A`, `J9780A`, `J9783A`, `JL357A` and their model names.
- Synthetic operational fields are explicitly marked as fixtures.
- Synthetic hostnames use `lab-<sku>-NN`, for example `lab-j9774a-01`. They must never be described as production/real device names.

The previous v2 used synthetic fixture names that looked too much like production hostnames. v3 removes that naming style entirely to avoid provenance confusion.

## What is tested

```text
user query
  -> planner / intent
  -> deterministic resolver
  -> route selection
  -> SpyBackend tool calls
  -> optional Qwen investigation
  -> answer
```

The harness asserts resolution, route, actual backend calls, arguments, and whether the LLM was invoked. Open-ended investigation semantics are exported for external judging. Local Qwen never judges itself.

## Central proof pair

Direct fact:

`J9774A up mı?`

Expected: resolve exact SKU -> `get_device` -> deterministic answer -> no LLM.

Investigation escalation:

`J9774A up gözüküyor ama ben tepki alamıyorum.`

Expected: resolve same device -> `get_device + get_ports + get_alerts + get_events` -> Qwen grounded investigation.

The backend fixture deliberately reports device status `up` while port 8 is admin-up/oper-down with an active alert and matching state-change events.

## Files

- `source_catalog.json`: source-backed model vocabulary derived from the Excel
- `dummy_inventory.json`: explicit synthetic lab instances mapped to real SKU/model identities
- `dummy_backend_data.json`: synthetic operational fixtures
- `backend_capabilities.json`: read-only backend capability contract
- `orchestration_policy.json`: expected route-to-tool policy
- `gold_cases.json`: 40 hand-authored architecture acceptance cases
- `generated_cases.json`: 16 wording robustness variants
- `dummy_backend.py`: SpyBackend that records actual calls and args
- `run_gold.py`: deterministic harness
- `reference_adapter.py`: harness self-test adapter only
- `sut_adapter_template.py`: adapter contract for the real local PoC
- `resolver_candidate_v3.py`: current resolver candidate

## Judging

Deterministic properties are graded in code. Investigation answer quality is written to `external_judge_cases.jsonl` for DeepSeek or ChatGPT. The local model under test is never a judge.

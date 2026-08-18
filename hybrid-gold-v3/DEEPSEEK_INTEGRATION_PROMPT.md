# DeepSeek task: connect hybrid-gold-v3 to the real local SUT

Use the provided `hybrid-gold-v3` package as the acceptance specification. Do not redesign the 40 Gold cases.

Important provenance rule: the uploaded Excel contains model metadata only. Real source-backed identifiers are the eight HP ProCurve SKU/model identities. Any `lab-<sku>-NN` hostname, device_id, status, port, alert, or event is an explicitly synthetic fixture. Never describe these as real production hostnames.

## Goal

Implement a thin `sut_adapter.py` around the current local PoC so `run_gold.py` can observe:

- planner output
- resolver output
- route / intent
- actual SpyBackend tool calls and arguments
- whether Qwen was invoked
- Qwen input/output when investigation is required
- final answer

Do not infer tool calls from final text. Execute through the supplied SpyBackend so the trace proves what was actually called.

## Critical proof pair

1. `J9774A up mı?`
   - resolve model identity deterministically
   - `get_device`
   - no Qwen

2. `J9774A up gözüküyor ama ben tepki alamıyorum.`
   - same resolved identity
   - `get_device`, `get_ports`, `get_alerts`, `get_events`
   - Qwen investigation

The fixture intentionally creates an operational contradiction: overall status is up, but port 8 is admin-up/oper-down and evidence contains an alert plus matching events.

## Judge policy

Qwen is part of the SUT. It must not grade its own output. Deterministic assertions are handled by the harness. Semantic investigation cases must be exported to `external_judge_cases.jsonl` for DeepSeek or ChatGPT external judging.

## Run order

1. Run syntax/unit checks.
2. Run 40 Gold cases unchanged.
3. Preserve the first raw run and failures.
4. If implementation bugs are found, preserve pre-fix traces before the smallest general fix.
5. Run 16 generated robustness cases separately.
6. Run the frozen legacy 56-suite unchanged.
7. Export external judge JSONL.

Report Gold, Generated, Legacy, and external-judge-pending metrics separately. Do not collapse them into one score.

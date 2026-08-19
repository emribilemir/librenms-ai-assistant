# LibreNMS Hidden Holdout v1 Run Report

## Status

Completed as a frozen model run. All 42 queries were sent exactly as provided through the real pipeline. No accuracy score or PASS/FAIL judgment is reported.

## Run outcome

The first attempt was blocked by sandbox access to Ollama and is preserved as `holdout_v1_initial_permission_failure_*`. After the user-authorized local Ollama check confirmed `librenms-qwen:latest`, the same frozen SUT was run with Ollama access. The valid run completed all 42 cases with no exceptions.

## Identified SUT files and SHA-256

See [pre/key-file-sha256.txt](../holdout-evidence/pre/key-file-sha256.txt). The identified runtime is `librenms-hybrid-poc/hybrid_poc.py`, invoked through `sut-results/sut_adapter.py`, with `librenms-hybrid-poc/resolver.py` and `hybrid-gold-v3/dummy_backend.py`.

## Required evaluation fields

- Frozen commit SHA: `99cb6670176897ebf04f5ecb8fdd457caa49aec7`
- Freeze tag SHA: `99cb6670176897ebf04f5ecb8fdd457caa49aec7`
- PRE working tree clean: implementation diff/index clean; unrelated untracked `.DS_Store` remains
- Model: `librenms-qwen` default in the adapter
- Think setting: `false` in the orchestration planner and synthesis calls
- Hidden queries executed: 42
- Planner failure count: 0
- Synthesis invocation count: 8
- Queries that executed backend tools: HID-006, HID-007, HID-022, HID-023, HID-025, HID-026, HID-027, HID-028, HID-029, HID-042
- Backend call totals: `get_device` 10, `get_ports` 8, `get_alerts` 8, `get_events` 8
- Route counts: `atomic` 2, `device_set` 23, `investigation` 8, `no_match` 4, `unsupported` 5
- Clarification count: 0; no-match count: 4; unsupported count: 5
- Missing observability fields: none in the valid run; complete planner, resolver, tool, synthesis, final-answer, and timing fields are preserved
- SpyBackend used: yes; actual runtime tool calls and returned evidence are preserved in each trace
- SUT changed after holdout exposure: no; only result, log, backup, report, and Git evidence artifacts were written
- PRE and POST HEAD match: yes (`99cb6670176897ebf04f5ecb8fdd457caa49aec7`)
- PRE and POST implementation hashes match: yes

## Artifacts

- [holdout_v1_console.log](holdout_v1_console.log)
- [holdout_v1_raw_results.json](holdout_v1_raw_results.json)
- [initial sandbox-failure raw backup](holdout_v1_initial_permission_failure_raw.json)
- [initial sandbox-failure console backup](holdout_v1_initial_permission_failure_console.log)
- [pre Git evidence](../holdout-evidence/pre/)
- [post Git evidence](../holdout-evidence/post/)

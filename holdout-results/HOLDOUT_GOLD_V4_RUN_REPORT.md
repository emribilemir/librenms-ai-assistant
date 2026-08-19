# LibreNMS Hidden Holdout v1 — Gold + Resolver v4 Run

## Integrity

All previous runs are preserved unchanged:

- Initial sandbox-failure run: `holdout_v1_initial_permission_failure_*`
- Gold-schema run using the wrong resolver: `holdout_v1_raw_results_wrong_resolver_poc.json` and `holdout_v1_console_wrong_resolver_poc.log`
- Earlier Gold-schema/poc-resolver artifacts remain separately available under their original names and in the prior reports.

The Gold v4 run used the exact same 42 hidden query strings, frozen commit, planner schema, model, backend, and prompts. Only the runtime resolver module was selected as requested. No source, prompt, resolver file, fixture, test file, or hidden query was modified. No local answer-key judging or accuracy score was performed.

## Accepted resolver verification

Pre-holdout Gold artifacts identify the accepted resolver as `resolver_candidate_v4.py`:

- `hybrid-gold-v3/gold_results_v3.json`: resolver `resolver_candidate_v4.py`, deterministic 40/40
- `hybrid-gold-v3/gold_summary_v3.json`: resolver `resolver_candidate_v4.py`, deterministic 40/40
- `sut-results/sut_gold_results.json`: resolver `resolver_candidate_v4.py`
- `sut-results/RUN_REPORT.md`: documents `hybrid-gold-v3/resolver_candidate_v4.py` as the resolver under test

Exact resolver:

`hybrid-gold-v3/resolver_candidate_v4.py`

SHA-256:

`f925a75fe86d2b3a99040b4b608c93effc782cac9f60848d339c5a2fb62ba6f4`

## Frozen runtime

- Commit and freeze tag: `99cb6670176897ebf04f5ecb8fdd457caa49aec7`
- `SUT_PLANNER_SCHEMA=gold`
- `SUT_MODEL=librenms-qwen`
- Resolver: `hybrid-gold-v3/resolver_candidate_v4.py`
- Planner think: `false`
- Synthesis think: `false`
- Ollama: `http://localhost:11434`
- Query count: 42

See [PRE runtime config](../holdout-evidence/pre-gold-v4/runtime-config.txt) and [POST runtime config](../holdout-evidence/post-gold-v4/runtime-config.txt).

## Run observations

- Planner failures: 0
- Synthesis invocations: 11
- Cases reaching SpyBackend: 28
- Exceptions: 0
- Routes: atomic 10; alerts 2; clarification 2; device_set 4; events 2; historical_investigation 3; investigation 8; no_match 4; ports 3; unsupported 4
- Backend calls: `get_device` 28; `get_ports` 11; `get_alerts` 10; `get_events` 13

## Git evidence

- PRE-v4 and POST-v4 HEAD match: yes
- PRE-v4 and POST-v4 implementation/resolver hashes match: yes
- SUT behavior changed: no

Artifacts:

- [Gold + resolver-v4 raw results](holdout_v1_raw_results_gold_resolver_v4.json)
- [Gold + resolver-v4 console log](holdout_v1_console_gold_resolver_v4.log)
- [Preserved prior Gold/wrong-resolver raw results](holdout_v1_raw_results_wrong_resolver_poc.json)
- [Preserved prior Gold/wrong-resolver console log](holdout_v1_console_wrong_resolver_poc.log)
- [PRE-Gold-v4 evidence](../holdout-evidence/pre-gold-v4/)
- [POST-Gold-v4 evidence](../holdout-evidence/post-gold-v4/)

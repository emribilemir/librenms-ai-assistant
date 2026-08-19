# LibreNMS Hidden Holdout v1 — Gold Planner Configuration Run

## Scope and integrity

The original valid run was preserved unchanged as the wrong-configuration `poc` run:

- Raw SHA-256: `828d399ff62292cb46442b8a92673ca73f3795142a944f82442fa316c634400c`
- Console SHA-256: `90ecd18701888316d625ab37eec049eb7a9640921bb93a17ce464ed07d4a001d`
- Configuration recorded in that raw file: `planner_schema=poc`, `model=librenms-qwen`

The corrected run used the exact same 42 query strings, the same frozen commit, and the same SUT/backend files, with only the runtime environment changed to `SUT_PLANNER_SCHEMA=gold`. No source, prompt, resolver, fixture, or test file was modified. No local answer-key judging or accuracy score was performed.

## Frozen implementation verification

- Commit: `99cb6670176897ebf04f5ecb8fdd457caa49aec7`
- Freeze tag: `holdout-v1-freeze` at `99cb6670176897ebf04f5ecb8fdd457caa49aec7`
- Adapter default verified in `sut-results/sut_adapter.py`: `os.environ.get("SUT_PLANNER_SCHEMA", "poc")`
- Gold branch verified in `librenms-hybrid-poc/hybrid_poc.py`: `planner_schema == "gold"` selects `PLANNING_SCHEMA_GOLD` and `PLANNING_SYSTEM_GOLD`

## Corrected run configuration

See [PRE runtime config](../holdout-evidence/pre-gold/runtime-config.txt) and [POST runtime config](../holdout-evidence/post-gold/runtime-config.txt).

- `SUT_PLANNER_SCHEMA=gold`
- `SUT_MODEL=librenms-qwen`
- planner `think=false`
- synthesis `think=false`
- Ollama endpoint: `http://localhost:11434`
- Query count: 42

## Corrected run observations

- Planner failures: 0
- Synthesis invocations: 11
- Cases reaching SpyBackend: 27
- Exceptions: 0
- Routes: atomic 9; alerts 2; clarification 3; device_set 4; events 2; historical_investigation 3; investigation 8; no_match 4; ports 3; unsupported 4
- Backend calls: `get_device` 27; `get_ports` 11; `get_alerts` 10; `get_events` 13

## Git evidence

- PRE-Gold and POST-Gold HEAD match: yes
- PRE-Gold and POST-Gold key implementation hashes match: yes
- SUT behavior changed: no

Artifacts:

- [Corrected raw results](holdout_v1_raw_results_gold.json)
- [Corrected console log](holdout_v1_console_gold.log)
- [Preserved wrong-config raw run](holdout_v1_raw_results_wrong_config_poc.json)
- [Preserved wrong-config console log](holdout_v1_console_wrong_config_poc.log)
- [PRE-Gold evidence](../holdout-evidence/pre-gold/)
- [POST-Gold evidence](../holdout-evidence/post-gold/)

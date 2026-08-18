# LibreNMS Hidden Holdout v1 Run Report

## Status

Not executed. The required preconditions were unavailable, so no hidden query was opened and no evaluation result was produced.

## Blockers

- `holdout_queries_v1.json` was not found in the supplied attachment directory or workspace.
- `/Users/emirbilici/Desktop/jrWorkworkwork/programming/isbaklibrenms` is not a Git repository, nor are the visible SUT directories. Therefore commit SHA, Git status/diffs, freeze tag, and PRE/POST Git comparisons cannot be captured honestly.

## Identified SUT files and SHA-256

See [pre/key-file-sha256.txt](../holdout-evidence/pre/key-file-sha256.txt). The identified runtime is `librenms-hybrid-poc/hybrid_poc.py`, invoked through `sut-results/sut_adapter.py`, with `librenms-hybrid-poc/resolver.py` and `hybrid-gold-v3/dummy_backend.py`.

## Required evaluation fields

- Frozen commit SHA: unavailable
- Freeze tag SHA: unavailable
- PRE working tree clean: unverifiable
- Model: `librenms-qwen` default in the adapter
- Think setting: `false` in the orchestration planner and synthesis calls
- Hidden queries executed: 0
- Planner failures: not applicable
- Synthesis invocations: not applicable
- Backend-tool cases: none
- Clarification / no-match / unsupported counts: not applicable
- Missing observability fields: none assessed; no run occurred
- SpyBackend used: identified, but not invoked
- SUT changed after holdout exposure: no holdout exposure occurred; no SUT files were changed
- PRE and POST HEAD match: not applicable
- PRE and POST implementation hashes match: not applicable

## Artifacts

- [holdout_v1_console.log](holdout_v1_console.log)
- [pre Git evidence](../holdout-evidence/pre/)
- No raw result file was created because there were no supplied queries to execute.
- No post-run evidence was created because no first raw run occurred.

# Repository agent instructions

## Live browser acceptance

- Run all live LibreNMS/UTM UI acceptance in the Codex in-app browser.
- Do not substitute Safari, Chrome, or headless Playwright for live UTM browser acceptance.
- Desktop acceptance is the supported target unless the task explicitly says otherwise.

## VM access

- Before every VM operation, read `docs/CODEX_VM_ACCESS.md`.
- Use only `ssh librenms-vm '<command>'` and do not repair or rediscover SSH access.

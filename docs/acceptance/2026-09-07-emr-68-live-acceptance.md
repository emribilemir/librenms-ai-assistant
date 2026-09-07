# EMR-68 UTM LibreNMS AI Assistant live acceptance

Last verified: 2026-09-07 (Europe/Istanbul)

Environment: authenticated LibreNMS 26.8.1 lab in UTM, exercised only through the Codex in-app browser at `/plugin/AiAssistant`. Desktop acceptance viewport was 1007 × 987. The Mac-hosted FastAPI service and UTM SNMPSIM/LibreNMS data path were live; browser responses were not mocked.

## Release and deployment

| Check | Result |
| --- | --- |
| Git source | PASS — `origin/main` at `1cdb0c4` after PRs [#20](https://github.com/emribilemir/isbaklibrenms/pull/20), [#21](https://github.com/emribilemir/isbaklibrenms/pull/21), and [#22](https://github.com/emribilemir/isbaklibrenms/pull/22). |
| Frontend asset version | PASS — the authenticated page loaded both CSS and JS with `?v=20260907-emr68c`. |
| Plugin deployment | PASS — only `/opt/librenms/app/Plugins/AiAssistant/` and `/opt/librenms/html/plugins/ai-assistant/` were replaced; LibreNMS core `git status --short` remained empty. |
| Recoverable backup | `/opt/librenms/.ai-assistant-backups/20260907-emr68c-1cdb0c4` |
| PHP preflight | PASS — `Menu.php`, `Page.php`, and `Settings.php` all passed `php -l` before replacement. |
| Backend runtime | PASS — launchd service `com.emirbilici.librenms-ai-assistant` was running as PID `80367`; deployed and source `chat_service/app.py` SHA-256 both equal `d870b02df5d19f1464548ef0530f8bde87a32b790e9b4ff4f44455b93474b57e`. |

Final deployed SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| `Page.php` | `a7140f1643c82dd3edc34c2375e5a1bac11872235d93dd401c926645c5b9db80` |
| `page.blade.php` | `f45da5fedfd1c21f6575574ad178d132682879a62bd64268c0a6d496d647cfa4` |
| `ai-assistant.js` | `a3c11a67271e2a875f7c18346746587267421e6c3076d21fbf26ad0f38be76f1` |
| `ai-assistant.css` | `448c09246df7ac92072cddef5dd88967ef8acc16aa1f8ef8b15eb958efd3f45e` |

## Automated regression

| Suite | Result |
| --- | --- |
| Backend pytest | PASS — 180 tests and 27 subtests; one existing Starlette `anyio` deprecation warning. |
| Frontend Jest | PASS — 9 suites / 93 tests. |
| Plugin contract | PASS — 9 tests. |
| Standalone Playwright | PASS — 27/27 tests, including saved threads, sanitized inspection, safe navigation, structured port/alarm results, queue FIFO/removal/isolation, stop, reload, responsive layout, and accessibility. |
| Device picker replacement stress | PASS — 10/10 repeated runs. |
| Vite production build | PASS — JS 754.71 kB (230.24 kB gzip), CSS 33.09 kB (7.38 kB gzip). The existing >500 kB chunk warning is non-failing. |

The live tour exposed two composer synchronization edge cases that the prior automated pass did not make deterministic. PR #21 prevents runtime refreshes from restoring stale device-picker text. PR #22 clears submitted controlled text after button/Enter submission and captures native paste/replacement edits before an unrelated refresh. The latter regression was added red-first, then the full suite and a 10-run picker stress pass were completed before deployment.

## Authenticated in-app browser tour

| Area | Live result |
| --- | --- |
| Demo default and opt-out | PASS — Demo Mode started off after backend restart. With it off, Demo Controls, investigation verification, and JSON/Python demo metadata were absent. The normal compact process-timing disclosure remains available by design. |
| Suggested prompts | PASS — the empty state simultaneously offered model information, admin-up/oper-down ports, last-24-hours history, and investigation prompts from live up devices. |
| Device picker | PASS — 11 devices with live status dots, hostname search (`lab-j9772` → 2 rows), keyboard editing, no auto-submit on selection, and `lab-j9772a-01` under “Son kullanılanlar” after reopening. The picker matched the SNMPSIM invariant: 8 up and 3 intentional baseline-down devices. |
| `port-down` | PASS — SNMP mutation, LibreNMS poll, and Port 2 `admin=up / oper=down` were confirmed. |
| `port-up` | PASS — Port 2 `admin=up / oper=up` was confirmed. |
| `location-change` | PASS — LibreNMS showed `EMR-55 Demo Lab`. |
| `device-down-up` | PASS — the target went down and returned up, with the transition persisted in event history. |
| `port-down-up-event` | PASS — the Port 2 transition event was recorded and appeared in the real LibreNMS event log. |
| Investigation incident | PASS — prepared Port 2 down plus event and active warning alarm, then submitted the UI's suggested question: `lab-j9772a-01 cihazında şu an ne sorun var, son 24 saatte neler olmuş?`. |
| Investigation answer | PASS — reported the device up, Port 2 admin up / oper down, active critical alarm `#88`, active warning alarm `#133`, historical down→up and up→down transitions, and explicitly kept root cause unknown. |
| Investigation verification | PASS — target, `investigation` route, device/port/alarm/event reads, current device state, expected port finding, active alarm, historical transition, expected event evidence, and restricted synthesis all showed checkmarks. |
| Process inspector | PASS — “İşlem ayrıntıları” exposed completed stages and timings. `Özet` and `JSON` showed only bounded planner, resolution, route, tool-argument, finding, synthesis, and navigation-target metadata. No token, shared secret, authorization value, prompt, or raw backend payload was present. |
| Structured port answer | PASS — `lab-j9772a-01 port 2 ne durumda?` rendered a semantic table with Port 2, Down, Admin Up, `Test-Down`, and the verified inline port link. |
| Composer submission | PASS — `lab-j9772a-01 ne durumda?` cleared immediately on send under `emr68c`; the live answer said the device is running and retained an empty enabled composer. |
| FIFO queue | PASS — while a live investigation was running, a second status question showed `1 sırada`; after the first completed, the second ran exactly once and the queue disappeared. |
| History and reload | PASS — after a full page reload the latest status thread appeared first; selecting it restored both answer and device deep link. |
| Desktop geometry | PASS — after a long thread, composer top/bottom were `842/894`, main bottom `986`, root bottom `987`, viewport height `987`; the composer was visible and no unexplained lower band remained. |
| Lab reset | PASS — “Laboratuvar sıfırlandı” confirmed that the selected target returned to its known baseline. |

## Read-only LibreNMS deep links

All links were opened from assistant answers in new Codex in-app browser tabs and resolved to authenticated UTM LibreNMS pages:

- device: `/device/1` → `lab-j9772a-01 | LibreNMS`, including model, location, status summary, and recent events;
- port: `/device/1/port/port=2` → real GigabitEthernet2 / `Test-Down` detail and graphs;
- alerts: `/device/1/alerts` → two active rows for `Port status up/down` and `LAB - Port admin up oper down` during the incident;
- events: `/device/1/logs/eventlog` → real Port 2 up/down and device down/up transitions with timestamps.

## SNMPSIM restart and baseline invariant

`origin/main:simulation/run.py` and the local checkout both hash to `b4069eaab3f39cfba228cb5f2c70844fddfd7cdff8f75714da55d54666b98524`. Its responder start path rebuilds the command exclusively from `/opt/snmpsim-lab/devices-up.txt`.

The real responder was stopped and started during acceptance (`PID 955` → `7554`), after which all eight members of `devices-up.txt` answered direct SNMP GETs. The three intentional baseline-down devices remained down in LibreNMS and the picker. The final lab reset performed another real responder restart; final PID was `1418`, and all eight up members again answered direct GETs:

- `lab-j9772a-01`
- `lab-j9772a-02`
- `lab-j9775a-02`
- `lab-jl357a-01`
- `lab-j4850a-01`
- `lab-j9774a-01`
- `lab-j9776a-01`
- `lab-j9783a-01`

The excluded baseline-down devices were `lab-j9775a-01`, `lab-j4850a-02`, and `lab-j9780a-01`. Final target records were location `Test Lab`, Port 2 admin OID value `1` (up), and oper OID value `2` (down). Deployed lab control hashes were:

- `/opt/snmpsim-lab/run-up-only.sh`: `ad73d50e7bc7b6182106396baa6d9562739b69b4b1bdc6f4e3845087bca62ec6`
- `/opt/snmpsim-lab/devices-up.txt`: `9e09d0a1924fdfca4d304cd7496ee2866035bfec47d3085089feef583156fac3`

## Rollback boundary

No LibreNMS core, Nginx, SSH, or VM network configuration was changed. Rollback is limited to restoring the plugin and asset directories from `/opt/librenms/.ai-assistant-backups/20260907-emr68c-1cdb0c4` using the existing deployment runbook.

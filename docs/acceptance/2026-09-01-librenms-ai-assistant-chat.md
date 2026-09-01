# LibreNMS AI Assistant chat acceptance — offline evidence

Date: 2026-09-01
Environment: ephemeral loopback-only standalone fixture (`127.0.0.1`), local SQLite database in `/private/tmp`, local Vite shell, and local Chrome. The fixture starts the Task 1 FastAPI factory in development-auth mode, drives its real REST and SSE routes, and uses a deterministic server-side pipeline adapter. No browser-level API/SSE mocks are used.

## Results

| Check | Command | Result |
| --- | --- | --- |
| RED acceptance baseline | `cd chat-ui && npx playwright test e2e/standalone.spec.js --project=chromium` before the Playwright configuration existed | Failed as expected: `Project(s) "chromium" not found`; preserved at `e2e-artifacts/red/playwright-red.txt`. |
| Standalone browser acceptance | `cd chat-ui && npx playwright test e2e/standalone.spec.js --project=chromium` | PASS — 6 tests in 6.0 s. |
| Python regression | `.venv/bin/python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v` | PASS — 118 tests in 2.266 s. |
| Frontend unit test and build | `cd chat-ui && npm test -- --runInBand && npm run build` | PASS — 6 suites / 37 tests; production build completed. |
| Plugin contracts | `.venv/bin/python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v` | PASS — 9 tests. |
| Unauthorized UTM guard | `cd chat-ui && npx playwright test --project=utm` | SKIPPED — 8 authored tests. No fixture was started and no target URL or authorization was supplied. |

The standalone tests cover saved thread create/select/delete confirmation, no-match progress, retryable failure and retry, fallback labeling and metric disclosure, cancellation before later stage/answer, keyboard focus, polite live region, and the responsive drawer. They use role and label locators with assertion-driven synchronization. The fallback run verifies persisted component timings of 7 + 11 + 13 + 17 = `total_ms` 48; `total_ms` is not itself included in that sum. The retryable path visibly reaches `librenms running`, then is released through a test-only local server barrier before its terminal backend error, so no browser timer is used to manufacture the ordering.

## Browser evidence

The ignored local Playwright report is at `e2e-artifacts/playwright/report/`. The final-run screenshots are:

- `e2e-artifacts/playwright/test-results/standalone-labels-a-valida-5cd30--complete-metric-disclosure-chromium/fallback-metrics.png`
- `e2e-artifacts/playwright/test-results/standalone-cancelling-a-re-332df-er-stages-and-answer-output-chromium/cancelled-run.png`

These are local evidence artifacts, intentionally excluded from the repository.

## UTM and rollback boundary

UTM acceptance was intentionally **not attempted**: no explicit target authorization, host, credentials, or deployment approval was provided. Consequently this work did not access or change UTM, `/opt/librenms`, Nginx, or an external runtime. The UTM project has no fallback base URL or local fixture for a UTM-only invocation. It remains inert unless the operator supplies `AI_UTM_AUTHORIZED=1`, `AI_UTM_BASE_URL`, readable `AI_UTM_PRIMARY_STORAGE_STATE` and `AI_UTM_SECONDARY_STORAGE_STATE` files, plus the explicitly curated query/expected-text variables required by each scenario.

The authored-but-unexecuted UTM suite covers signed plugin-route identity, responsive keyboard access, create/select/history/delete confirmation, no-match streaming, a live-region stage-change/focus parity case, fallback label and metrics, backend-down/retry, cancellation, and cross-user thread ownership. Its fallback scenario reads the authenticated persisted thread detail and asserts that every present metric is finite/nonnegative, `total_ms` covers the non-backend component sum, and `backend_ms` (when present) is bounded by total rather than blindly added because it measures backend adapter time. The retry scenario observes planner completed → resolver completed → librenms running → error before retry; the authorized live target and curated retry query must themselves be configured to expose that sequence. This suite does not control live timing. It uses only supplied signed-in browser states; it embeds no target, credential, token, deployment action, or default host.

There is therefore no UTM installation, Nginx validation/reload, or rollback execution to claim. Those steps remain pending explicit authorization and must follow the rollback procedure in `integrations/librenms/AiAssistant/docs/deployment.md`: disable the plugin, reverse the proxy include, validate/reload Nginx only after validation succeeds, and stop the Mac API. This document records offline verification only.

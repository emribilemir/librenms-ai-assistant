# LibreNMS AI Assistant chat acceptance — offline evidence

Date: 2026-09-01
Environment: ephemeral loopback-only standalone fixture (`127.0.0.1`), local SQLite database in `/private/tmp`, local Vite shell, and local Chrome. The fixture starts the Task 1 FastAPI factory in development-auth mode, drives its real REST and SSE routes, and uses a deterministic server-side pipeline adapter. No browser-level API/SSE mocks are used.

## Results

| Check | Command | Result |
| --- | --- | --- |
| RED acceptance baseline | `cd chat-ui && npx playwright test e2e/standalone.spec.js --project=chromium` before the Playwright configuration existed | Failed as expected: `Project(s) "chromium" not found`; preserved at `e2e-artifacts/red/playwright-red.txt`. |
| Standalone browser acceptance | `cd chat-ui && npx playwright test e2e/standalone.spec.js --project=chromium` | PASS — 6 tests in 6.0 s. |
| Python regression | `.venv/bin/python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v` | PASS — 118 tests in 2.266 s. |
| Frontend unit test and build | `cd chat-ui && npm test -- --runInBand && npm run build` | PASS — 5 suites / 36 tests; production build completed. |
| Plugin contracts | `.venv/bin/python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v` | PASS — 9 tests. |
| Unauthorized UTM guard | `cd chat-ui && npx playwright test e2e/utm.spec.js --project=utm` | SKIPPED — 1 test. No target URL or `AI_UTM_AUTHORIZED=1` was supplied. |

The standalone tests cover saved thread create/select/delete confirmation, no-match progress, retryable failure and retry, fallback labeling and metric disclosure, cancellation before later stage/answer, keyboard focus, polite live region, and the responsive drawer. They use role and label locators with assertion-driven synchronization.

## Browser evidence

The ignored local Playwright report is at `e2e-artifacts/playwright/report/`. The final-run screenshots are:

- `e2e-artifacts/playwright/test-results/standalone-labels-a-valida-5cd30--complete-metric-disclosure-chromium/fallback-metrics.png`
- `e2e-artifacts/playwright/test-results/standalone-cancelling-a-re-332df-er-stages-and-answer-output-chromium/cancelled-run.png`

These are local evidence artifacts, intentionally excluded from the repository.

## UTM and rollback boundary

UTM acceptance was intentionally **not attempted**: no explicit target authorization, host, credentials, or deployment approval was provided. Consequently this work did not access or change UTM, `/opt/librenms`, Nginx, or an external runtime. The UTM test has no default remote host and remains skipped unless both `AI_UTM_AUTHORIZED=1` and `AI_UTM_BASE_URL` are supplied by the operator.

There is therefore no UTM installation, Nginx validation/reload, or rollback execution to claim. Those steps remain pending explicit authorization and must follow the rollback procedure in `integrations/librenms/AiAssistant/docs/deployment.md`: disable the plugin, reverse the proxy include, validate/reload Nginx only after validation succeeds, and stop the Mac API. This document records offline verification only.

# LibreNMS AI Assistant chat acceptance — offline evidence

Last verified: 2026-09-03
Environment: ephemeral loopback-only standalone fixture (`127.0.0.1`), local SQLite database in `/private/tmp`, local Vite shell, and local Chrome. The fixture starts the Task 1 FastAPI factory in development-auth mode, drives its real REST and SSE routes, and uses a deterministic server-side pipeline adapter. No browser-level API/SSE mocks are used.

## Results

| Check | Command | Result |
| --- | --- | --- |
| RED acceptance baseline | `cd chat-ui && npx playwright test e2e/standalone.spec.js --project=chromium` before the Playwright configuration existed | Failed as expected: `Project(s) "chromium" not found`; preserved at `e2e-artifacts/red/playwright-red.txt`. |
| Standalone browser acceptance | `cd chat-ui && npx playwright test e2e/standalone.spec.js --project=chromium` | PASS — 10 tests in 12.1 s. |
| Python regression | `.venv/bin/python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v` | PASS — 124 tests in 1.775 s. |
| Frontend unit test and build | `cd chat-ui && npm test -- --runInBand && npm run build` | PASS — 7 suites / 49 tests; Vite 8 production build completed. |
| Plugin contracts | `.venv/bin/python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v` | PASS — 9 tests. |
| Authorized UTM deployment smoke | Asset SHA-256, `/plugin/AiAssistant`, `/ai-api/v1/threads`, and signed `/ai-api/v1/suggestions` checks | PASS — deployed bundle matches the local build; plugin redirects anonymous requests to login; proxy returns the expected 401 auth boundary; signed live suggestions return current LibreNMS devices. |
| Authenticated UTM browser suite | `cd chat-ui && npx playwright test e2e/utm.spec.js --project=utm` | NOT RUN — 9 authored scenarios require supplied signed-in primary and secondary browser storage states. |

The standalone tests cover the assistant-ui thread-list adapter, saved thread create/select/delete confirmation, collapsible history rail, no-match progress, retryable failure and retry, fallback labeling and metric disclosure, cancellation before later stage/answer, keyboard focus, polite live region, responsive drawer, progressive validated answer chunks, and real conversation scrolling. They use role and label locators with assertion-driven synchronization. The fallback run verifies persisted component timings of 7 + 11 + 13 + 17 = `total_ms` 48; `total_ms` is not itself included in that sum. The retryable path visibly reaches `librenms running`, then is released through a test-only local server barrier before its terminal backend error, so no browser timer is used to manufacture the ordering.

## Browser evidence

The ignored local Playwright report is at `e2e-artifacts/playwright/report/`. The final-run screenshots are:

- `e2e-artifacts/playwright/test-results/standalone-labels-a-valida-5cd30--complete-metric-disclosure-chromium/fallback-metrics.png`
- `e2e-artifacts/playwright/test-results/standalone-cancelling-a-re-332df-er-stages-and-answer-output-chromium/cancelled-run.png`

These are local evidence artifacts, intentionally excluded from the repository.

## UTM and rollback boundary

The approved lab deployment updated only `/opt/librenms/app/Plugins/AiAssistant/` and `/opt/librenms/html/plugins/ai-assistant/`. A recoverable VM backup was created under `/opt/librenms/.ai-assistant-backups/`; the post-deployment `/opt/librenms` core `git status --short` was empty. Nginx configuration was not changed during this refinement. Anonymous route checks and a short-lived signed read-only suggestion request passed through the existing Nginx → Mac FastAPI path.

The authored-but-unexecuted UTM suite covers signed plugin-route identity, responsive keyboard access, create/select/history/delete confirmation, no-match streaming, a live-region stage-change/focus parity case, fallback label and metrics, backend-down/retry, cancellation, and cross-user thread ownership. Its fallback scenario reads the authenticated persisted thread detail and asserts that every present metric is finite/nonnegative, `total_ms` covers the non-backend component sum, and `backend_ms` (when present) is bounded by total rather than blindly added because it measures backend adapter time. The retry scenario observes planner completed → resolver completed → librenms running → error before retry; the authorized live target and curated retry query must themselves be configured to expose that sequence. This suite does not control live timing. It uses only supplied signed-in browser states; it embeds no target, credential, token, deployment action, or default host.

Authenticated UI acceptance remains pending because no reusable signed-in browser storage states were available; the in-app browser correctly stopped at the LibreNMS login page. Rollback remains the procedure in `integrations/librenms/AiAssistant/docs/deployment.md`: disable the plugin, restore the timestamped plugin/assets backup, and stop the Mac API. The existing proxy include should be reversed only when rolling back the full integration.

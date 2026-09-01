# Task 4 report — offline/standalone verification

## RED → GREEN evidence

- RED: before the acceptance harness was configured, `cd chat-ui && npx playwright test e2e/standalone.spec.js --project=chromium` exited 1 with `Project(s) "chromium" not found. The raw output is retained locally at `e2e-artifacts/red/playwright-red.txt`.
- GREEN: the deterministic loopback fixture now starts the real Task 1 FastAPI app, SQLite persistence, development-auth boundary, Vite `/ai-api` proxy, and browser SSE parser. `npx playwright test e2e/standalone.spec.js --project=chromium` passed 6/6 in 6.0 s.
- The red/green work also caught and corrected two integration defects: the Vite development proxy did not remove `/ai-api` before reaching the Task 1 `/v1` routes, and the assistant-ui external-store bridge did not transform the frontend's raw messages to its required runtime shape. A terminal REST refresh was also erasing a retryable SSE error's safe message before the user could retry.

## Offline gate

- `.venv/bin/python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v`: PASS, 118 tests in 2.266 s.
- `cd chat-ui && npm test -- --runInBand && npm run build`: PASS, 5 suites / 36 tests, build completed.
- `.venv/bin/python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v`: PASS, 9 tests.
- `cd chat-ui && npx playwright test e2e/utm.spec.js --project=utm`: 1 skipped, as designed without explicit UTM authorization and a target URL.

## Deliverable and limitations

Commit: `test: verify AI assistant chat integration`.

The added `@playwright/test` dependency is exact-pinned at `1.62.1` in both package manifest and lockfile. Reports and screenshots are written below ignored `e2e-artifacts/playwright/`; the final screenshots are named in the acceptance document.

UTM was not attempted and no UTM, `/opt/librenms`, Nginx, or external runtime was accessed or mutated. No live deployment, Nginx validation, signed-user UTM flow, or rollback result is claimed. Those remain pending explicit operator authorization.

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

## Fix round 1 — review findings

- RED: strengthened standalone acceptance failed in two expected ways. The retryable backend scenario never exposed `planner completed, resolver completed, librenms running`; the fallback metric disclosure did not contain the required 48 ms total. Raw output is retained at `e2e-artifacts/red/task-4-round1-red.txt`.
- GREEN: `DeterministicPipelineAdapter` now derives `total_ms` from component durations exactly once. The fallback assertion verifies both visible 7/11/13/17/48 ms values and the persisted API run relationship `48 == 7 + 11 + 13 + 17`.
- GREEN: a retryable backend outcome now emits planner and resolver completion, then a real `librenms.started` boundary before its librenms-scoped error. A test-only local control endpoint releases that deterministic pipeline barrier only after the browser observes the live progress; it is not a browser timer mock. The control endpoint was itself RED first (404) and GREEN after implementation; raw evidence is at `e2e-artifacts/red/task-4-round1-gate-red.txt`.
- UTM: replaced the former route smoke check with seven authored visible acceptance cases. `npx playwright test --project=utm` skipped all seven without starting a fixture or contacting a target because authorization, target, signed-in storage states, and curated scenario inputs were absent.

### Fix round 1 offline gate

- `.venv/bin/python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v`: PASS, 118 tests in 1.774 s (temporary loopback contract server only).
- `cd chat-ui && npx playwright test e2e/standalone.spec.js --project=chromium`: PASS, 6/6 in 6.0 s.
- `cd chat-ui && npm test -- --runInBand && npm run build`: PASS, 5 suites / 36 tests and production build.
- `.venv/bin/python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v`: PASS, 9 tests.
- `cd chat-ui && npx playwright test --project=utm`: 7 skipped; no UTM target was contacted.

## Fix round 2 — UTM authored parity

- RED: added the local static/meta contract `src/utmAcceptanceParity.test.js`; it failed because the authorized suite lacked an explicit live-progress scenario input, `aria-live` assertion, persisted-run metric helper, coherent metric assertion, and ordered planner/resolver/librenms retry assertions. Raw output: `e2e-artifacts/red/task-4-round2-red.txt`.
- GREEN: the authorized UTM suite now includes an eighth, explicitly curated live-progress scenario that verifies focus before submitting, `aria-live="polite"`, and observed planner then resolver live-text updates. Its fallback scenario requires `AI_UTM_FALLBACK_THREAD_TITLE`, reads the authenticated `/threads/{id}` detail response, and verifies finite/nonnegative metrics with total/component coherence without assuming backend timing is additive.
- GREEN: the retry scenario now requires `AI_UTM_RETRY_STAGE_GATE` in addition to its query/result inputs and asserts planner completed → resolver completed → librenms running → terminal error, then the successful retry result. This makes a live run opt-in and deterministic only when an authorized operator supplies a controlled scenario.
- Inert check: `cd chat-ui && npx playwright test --project=utm` skipped 8/8 with no fixture server and no UTM target contact.

### Fix round 2 relevant offline gate

- `cd chat-ui && npm test -- --runInBand`: PASS, 6 suites / 37 tests (including the static UTM authoring contract).
- `cd chat-ui && npx playwright test e2e/standalone.spec.js --project=chromium`: PASS, 6/6 in 6.0 s.
- `cd chat-ui && npm run build`: PASS.

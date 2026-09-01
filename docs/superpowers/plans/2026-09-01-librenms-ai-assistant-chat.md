# LibreNMS AI Assistant Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a secure, read-only, user-scoped LibreNMS AI Assistant chat page that wraps the existing hybrid Python pipeline without changing its public CLI or existing test behaviour.

**Architecture:** A FastAPI service under `librenms-hybrid-poc/chat_service/` owns signed-user authentication, SQLite history, run lifecycle, and fetch-compatible SSE while a narrow adapter observes the existing pipeline's real stage boundaries. A Vite/React frontend owns its reducer and `ExternalStoreRuntime`, is served by a version-controlled LibreNMS plugin, and calls only relative `/ai-api/v1` endpoints through the UTM Nginx proxy.

**Tech Stack:** Python with FastAPI `0.141.1`, Uvicorn `0.52.4`, SQLite; Vite `8`, React/ReactDOM `19.2.8`, `@assistant-ui/react` `0.15.17`; CSS Modules; Playwright; Nginx; LibreNMS local plugin.

**Spec:** `docs/superpowers/specs/2026-09-01-librenms-ai-assistant-chat-design.md`

## Global Constraints

- Treat the design document as the binding authority; read it before each task.
- Preserve the existing Python hybrid pipeline, public CLI behaviour, and all 90 existing Python tests.
- The service belongs only under `librenms-hybrid-poc/chat_service/`; it is a thin adapter around existing pipeline behaviour.
- Use monotonic time. `resolver_ms` is current resolver duration and `backend_ms` contains only real LibreNMS adapter call time.
- Buffer investigation synthesis; mechanically validate and judge it before emitting an answer delta. Rejected text is never persisted, logged, or sent.
- Persist only user messages, accepted assistant messages, run state, and summary metrics in SQLite with WAL, foreign keys, busy timeout, and schema versioning.
- Use only exact frontend dependency pins with a committed lockfile, CSS Modules, a custom reducer/store, and `ExternalStoreRuntime`; do not add AI SDK, Next.js, assistant-ui wire protocol, Tailwind, or a global reset.
- Production browser paths are relative `/ai-api/v1`; development uses only the Vite `/ai-api` proxy. A production bundle contains no development token.
- Do not modify LibreNMS core source, package metadata, or Vite files. Keep local plugin source under `integrations/librenms/AiAssistant/`.
- v1 excludes thread rename/search, attachments, branching, edit, and regeneration of completed messages.
- Do not install or modify UTM, LibreNMS, or Nginx until explicit authorization is received. Offline and standalone checks remain safe before that point.

## Planned File Structure

| Path | Responsibility |
| --- | --- |
| `librenms-hybrid-poc/chat_service/app.py` | FastAPI routes, request models, auth dependency, SSE response. |
| `librenms-hybrid-poc/chat_service/auth.py` | `v1` token verification and development-only identity gate. |
| `librenms-hybrid-poc/chat_service/store.py` | SQLite migrations, ownership filtering, title generation, message/run persistence. |
| `librenms-hybrid-poc/chat_service/runs.py` | Active-run registry, event ordering, cancellation, metrics, safe terminal outcomes. |
| `librenms-hybrid-poc/chat_service/pipeline_adapter.py` | Existing hybrid pipeline observer/cancellation seam and safe synthesis buffering. |
| `librenms-hybrid-poc/chat_service/logging.py` | Content-free structured logging. |
| `librenms-hybrid-poc/tests/test_chat_service_*.py` | Service, auth, persistence, SSE, safety, and cancellation tests. |
| `chat-ui/` | Exact-pinned Vite frontend, CSS Module components, reducer/store, and frontend tests. |
| `integrations/librenms/AiAssistant/` | Local LibreNMS plugin source, deployment manifest, and Nginx documentation. |
| `chat-ui/e2e/` | Standalone and authorized UTM Playwright acceptance tests. |

## Shared Interfaces

Every task uses these stable contracts:

- `POST /v1/threads` creates an empty current-user thread; `GET /v1/threads` lists current-user thread summaries; `GET` and `DELETE /v1/threads/{id}` enforce current-user ownership.
- `POST /v1/threads/{id}/runs` accepts `{client_message_id, content}` where `content` is non-empty after trimming and at most 8,000 characters; it returns `text/event-stream`.
- The authenticated identity has `sub` and `name`; the signer/verifier requires `iss=librenms`, `aud=ai-assistant`, and `exp=iat+3600`.
- Stream events are `run.started`, paired real-stage `planner`, `resolver`, `librenms`, and optional `synthesis` events, zero or more `answer.delta`, and a terminal `completed`; a terminal operational failure additionally emits `error` with `{stage, code, retryable, message}`.
- The browser cancels the run-creation fetch; server disconnect detection is the cancellation signal. No later stage or answer delta may occur after cancellation.
- `completed.metrics` contains `planner_ms`, `resolver_ms`, `backend_ms`, `synthesis_ms`, `time_to_first_token_ms`, `time_to_first_visible_chunk_ms`, and `total_ms`; `completed.used_fallback` is boolean.

---

### Task 1: Pipeline Instrumentation, Python Transport, Persistence, and Authentication

**Files:**

- Create: `librenms-hybrid-poc/chat_service/__init__.py`, `app.py`, `auth.py`, `store.py`, `runs.py`, `pipeline_adapter.py`, `logging.py`, `requirements-chat-service.txt`.
- Create: `librenms-hybrid-poc/tests/test_chat_service_auth.py`, `test_chat_service_store.py`, `test_chat_service_sse.py`, `test_chat_service_cancel.py`, `test_chat_service_safety.py`.
- Modify: the existing hybrid pipeline modules only to add optional observer and cancellation-predicate parameters at real stage boundaries, preserving every existing caller's defaults and public CLI output.

**Interfaces:**

- Consumes: signed `Authorization: Bearer` identity, the existing hybrid orchestrator result, and a request disconnect predicate.
- Produces: ownership-scoped REST/SSE service; `PipelineAdapter.run(content, observer, is_cancelled)`; safe, ordered events; persisted current-user history and summary runs.

- [ ] **Step 1: Write the RED tests before creating service code.**

Create focused test modules that assert valid/invalid/expired/tampered tokens; foreign-user `404`; title whitespace normalization and 60-character truncation; SQLite foreign-key/WAL/busy-timeout/schema-version setup; same-thread `409` and simultaneous different-thread runs; exact event order plus 15-second heartbeat; metrics attribution; cancellation before every later stage; no raw content in JSON logs; and no rejected investigation token in stream or storage.

- [ ] **Step 2: Verify the initial RED state.**

Run: `cd librenms-hybrid-poc && python3 -m unittest -v tests.test_chat_service_auth tests.test_chat_service_store tests.test_chat_service_sse tests.test_chat_service_cancel tests.test_chat_service_safety`

Expected: FAIL because `chat_service` and its tested route, store, adapter, and verifier interfaces do not exist yet.

- [ ] **Step 3: Implement the smallest transport and pipeline seam that satisfies the tests.**

Add exact FastAPI `0.141.1` and Uvicorn `0.52.4` pins. Implement the `v1.<base64url-json>.<base64url-hmac-sha256>` verifier with the required claims and 32-byte secret, enabled development identity only behind `AI_DEV_AUTH=1`, and no token in response/configuration. Add SQLite migration, restricted persistence, active-run registry, thread ownership, deterministic title, routes, heartbeat, and restricted JSON logging. Add observer/cancellation hooks with no-op defaults to the existing pipeline, and map real planner/resolver/LibreNMS/synthesis durations precisely. Buffer all investigation generation until mechanical validation and judging finish; emit only accepted text or deterministic fallback.

- [ ] **Step 4: Verify GREEN at the service boundary.**

Run: `cd librenms-hybrid-poc && python3 -m unittest -v tests.test_chat_service_auth tests.test_chat_service_store tests.test_chat_service_sse tests.test_chat_service_cancel tests.test_chat_service_safety`

Expected: PASS; the test output demonstrates strict ownership, ordered events, no rejected-text leakage, constrained logs, and cancellation preventing later stages.

- [ ] **Step 5: Protect compatibility with the existing pipeline suite.**

Run: `python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v`

Expected: PASS with the original 90 tests still green plus the new service tests. If a historical test changes, restore backwards-compatible optional defaults rather than altering its public assertion.

- [ ] **Step 6: Commit the independently testable backend deliverable.**

Run: `git add librenms-hybrid-poc && git commit -m "feat: add AI assistant chat service"`

Expected: one commit containing only the service, focused tests, compatible pipeline instrumentation, and dependency pins.

### Task 2: React Reusable Frontend with assistant-ui ExternalStoreRuntime

**Files:**

- Create: `chat-ui/package.json`, exact-version lockfile, `vite.config.*`, `src/main.*`, `src/App.*`, `src/api.*`, `src/store.*`, `src/runtime.*`.
- Create: `chat-ui/src/components/ThreadDrawer.*`, `ThreadList.*`, `ChatTranscript.*`, `Composer.*`, `RunProgress.*`, `RunMetrics.*`, `DeleteThreadDialog.*` and matching `*.module.css` files.
- Create: `chat-ui/src/**/*.test.*` and `chat-ui/src/test/setup.*`.

**Interfaces:**

- Consumes: Task 1 REST endpoints, the SSE contract, plugin-supplied signed identity, and `/ai-api` dev proxy.
- Produces: `AssistantChatStore` reducer state, custom `ExternalStoreRuntime`, fetch/SSE client, accessible full page, and static build output reusable by the plugin task.

- [ ] **Step 1: Write RED reducer, transport, and accessibility tests first.**

Cover creating/selecting/listing threads, delete confirmation focus and cancellation, optimistic `client_message_id` correlation, exact stream event reduction, live real-stage progress, error/retry state, fetch abort cancellation, expandable metrics, responsive drawer keyboard access, focus visibility, accessible names, and live-region updates. Include a test proving that a browser request uses `/ai-api/v1` and never a Mac host or embedded development identity.

- [ ] **Step 2: Verify the frontend RED state.**

Run: `cd chat-ui && npm test -- --runInBand`

Expected: FAIL because the reducer, runtime, components, and API client are absent.

- [ ] **Step 3: Implement the minimal reusable shell and ExternalStoreRuntime integration.**

Create a Vite `8` application with exact React/ReactDOM `19.2.8` and `@assistant-ui/react` `0.15.17` pins and committed lockfile. Keep message/run state in an application-owned reducer/store and bind that store to a custom `ExternalStoreRuntime`; do not use AI SDK, Next.js, or assistant-ui wire transport. Implement a fetch-based SSE reader that translates the Task 1 events, progressive rendering only after server validation, retry after retryable terminal errors, and `AbortController` cancellation. Build the full thread drawer, transcript, composer, progress, metrics, and confirmation experience with CSS Modules only and WCAG 2.2 AA semantics.

- [ ] **Step 4: Verify GREEN and production build output.**

Run: `cd chat-ui && npm test -- --runInBand && npm run build`

Expected: PASS and a static `dist/` bundle that contains only relative `/ai-api/v1` production requests, no Tailwind/global reset, no AI SDK/Next.js/assistant-ui wire protocol, and no development token.

- [ ] **Step 5: Smoke the standalone Vite shell through its proxy.**

Run: `cd chat-ui && npm run dev -- --host 127.0.0.1 --port 5173`

Expected: the manually started shell is reachable at `http://127.0.0.1:5173`, and an authenticated development-only test run can call `/ai-api/v1` through the configured `/ai-api` proxy rather than a hard-coded backend origin.

- [ ] **Step 6: Commit the independently testable frontend deliverable.**

Run: `git add chat-ui && git commit -m "feat: add AI assistant chat frontend"`

Expected: one commit containing the reusable frontend, exact lockfile, and reducer/UI/a11y tests.

### Task 3: LibreNMS Local Plugin, Asset Packaging, and Deployment Documentation

**Files:**

- Create: `integrations/librenms/AiAssistant/` plugin manifest, menu/page controller/view, settings definition, asset deployment script or manifest, and `README.md`.
- Create: `integrations/librenms/AiAssistant/nginx/ai-assistant.conf` and `integrations/librenms/AiAssistant/docs/deployment.md`.
- Create: `integrations/librenms/AiAssistant/tests/` plugin/static-config checks suitable for the repository's available test runner.

**Interfaces:**

- Consumes: `chat-ui/dist/`, a shared 32-byte plugin setting/environment secret, authenticated LibreNMS global-read user data, and the Task 1 `/v1` API contract.
- Produces: deployable plugin source for `/opt/librenms/app/Plugins/AiAssistant/`, assets for `/opt/librenms/html/plugins/ai-assistant/`, menu and `/plugin/AiAssistant`, signed browser identity, and Nginx proxy configuration.

- [ ] **Step 1: Write RED static/plugin contract checks.**

Write checks that require global-read gating, the `AiAssistant` menu/page route, a non-secret page root/configuration, `v1` token claims and HMAC use, no PHP AI logic, the exact source/asset deployment destinations, relative `/ai-api/v1` configuration, and Nginx HTTP/1.1, disabled buffering/cache, 360-second read timeout, and `192.168.64.1:8765` upstream.

- [ ] **Step 2: Verify the plugin RED state.**

Run: `python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v`

Expected: FAIL because the plugin package, deployment manifest, and Nginx include do not exist.

- [ ] **Step 3: Implement only the local integration and deployment materials.**

Create version-controlled plugin source that renders the frontend root/configuration and signs the authorized user's `sub` and `name` with the required HMAC token claims. Restrict access to global-read and keep PHP free of planner, resolver, Qwen, and LibreNMS adapter logic. Define asset copying to `/opt/librenms/html/plugins/ai-assistant/` and source deployment to `/opt/librenms/app/Plugins/AiAssistant/`. Document Mac service environment/secret configuration, binding to `192.168.64.1:8765`, proxy include installation, ordered Nginx validation/reload, plugin enablement, and reversible rollback.

- [ ] **Step 4: Verify GREEN without changing a UTM guest.**

Run: `python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v`

Expected: PASS; repository checks prove source boundaries, signed-identity contract, static asset destination, and required Nginx directives without installing any guest files.

- [ ] **Step 5: Verify the built asset packaging input.**

Run: `cd chat-ui && npm run build && test -f dist/index.html`

Expected: PASS; the plugin deployment mechanism has a concrete static bundle to package, while LibreNMS core package and Vite files remain unchanged.

- [ ] **Step 6: Commit the independently testable integration deliverable.**

Run: `git add integrations/librenms/AiAssistant && git commit -m "feat: add LibreNMS AI assistant plugin"`

Expected: one commit containing only local plugin, asset packaging, Nginx, deployment documentation, and integration checks.

### Task 4: Cross-Layer Verification, Playwright, Authorized UTM Installation, and Acceptance Evidence

**Files:**

- Create: `chat-ui/e2e/standalone.spec.*`, `chat-ui/e2e/utm.spec.*`, Playwright configuration, and fixture helpers.
- Create: `docs/acceptance/2026-09-01-librenms-ai-assistant-chat.md` containing command output references, screenshots, test reports, environment identifiers, and rollback verification.
- Modify: only deployment documentation from Task 3 when a verified command or deployment prerequisite needs a factual correction.

**Interfaces:**

- Consumes: green Task 1 service, green Task 2 static frontend, green Task 3 plugin/package documentation, and explicit user authorization before any UTM mutation.
- Produces: standalone and UTM Playwright acceptance evidence proving the design contract and the documented rollout/rollback result.

- [ ] **Step 1: Write RED Playwright acceptance tests.**

Write standalone tests for thread creation, selection, delete confirmation, real stage events, a successful ambiguous/no-match result, retryable failure, fallback-labelled investigation response, cancel preventing a later stage/answer delta, metrics disclosure, and keyboard/focus/live-region behaviour. Write UTM tests with the same visible acceptance cases plus signed-user isolation and the `/plugin/AiAssistant` route. Mark UTM tests as requiring an explicitly supplied authorized target rather than a default local run.

- [ ] **Step 2: Verify the Playwright RED state.**

Run: `cd chat-ui && npx playwright test e2e/standalone.spec.* --project=chromium`

Expected: FAIL before the fixture/server wiring and acceptance selectors are complete; preserve the failure report as implementation feedback, not acceptance evidence.

- [ ] **Step 3: Wire deterministic standalone fixtures and complete the acceptance harness.**

Make the standalone harness start the Task 1 API in development-auth mode only for local test fixtures and start the Vite shell through `/ai-api`. Exercise actual SSE parsing and deterministic controlled pipeline outcomes, not timer-only frontend mocks. Add the UTM target configuration so it is inert until the operator supplies the authorized host, credentials, and deployment approval.

- [ ] **Step 4: Verify GREEN in the standalone environment.**

Run: `cd chat-ui && npx playwright test e2e/standalone.spec.* --project=chromium`

Expected: PASS with reports/screenshots showing the specified thread, progress, safety, cancellation, metrics, and WCAG interaction evidence.

- [ ] **Step 5: Run the full offline regression gate.**

Run: `python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v && cd chat-ui && npm test -- --runInBand && npm run build && npx playwright test e2e/standalone.spec.* --project=chromium`

Expected: PASS. This is the required gate before requesting authorization to modify or access the UTM guest.

- [ ] **Step 6: Obtain explicit authorization, then install and verify on UTM.**

Run only after authorization: deploy plugin source to `/opt/librenms/app/Plugins/AiAssistant/`, deploy built assets to `/opt/librenms/html/plugins/ai-assistant/`, install the Nginx include, run `nginx -t`, reload Nginx only when it passes, enable the plugin for a global-read user, and run `cd chat-ui && npx playwright test e2e/utm.spec.* --project=chromium` against the authorized target.

Expected: `nginx -t` exits successfully, event streaming survives the proxy, and UTM Playwright passes signed identity, ownership, plugin-page, streaming, safety, and accessibility acceptance.

- [ ] **Step 7: Capture acceptance and rollback evidence.**

Record exact passing command results, test report/screenshot locations, UTM target identifier, installed plugin/asset paths, Nginx validation result, and a verified rollback sequence in `docs/acceptance/2026-09-01-librenms-ai-assistant-chat.md`. The rollback evidence confirms plugin disablement, proxy include reversal, successful `nginx -t`/reload, and stopped Mac API.

- [ ] **Step 8: Commit the cross-layer verification deliverable.**

Run: `git add chat-ui/e2e docs/acceptance integrations/librenms/AiAssistant/docs && git commit -m "test: verify AI assistant chat integration"`

Expected: one commit containing Playwright tests and factual acceptance evidence. Do not create acceptance claims for UTM until the authorized run has passed.

## Final Verification and Handoff

- [ ] Re-read the design document and map every safety, contract, deployment, and scope requirement to a green Task 1–4 test or captured acceptance item.
- [ ] Run `git diff --check` and `git status --short`; confirm no LibreNMS core files, unrelated files, secret files, or generated development tokens are staged.
- [ ] Confirm the production bundle calls only relative `/ai-api/v1`, and inspect source/logging tests to confirm no user content, raw LibreNMS data, prompt, grounding payload, token, or rejected answer can persist or log.
- [ ] Hand off only after offline gates pass and, when separately authorized, UTM evidence is captured. If authorization is not granted, hand off the green offline/standalone result and state that production installation was intentionally not attempted.

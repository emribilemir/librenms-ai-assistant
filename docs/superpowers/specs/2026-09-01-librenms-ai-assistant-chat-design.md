# LibreNMS AI Assistant Chat Design

## Purpose and v1 Boundary

This design adds a user-scoped, read-only AI chat surface to the existing LibreNMS hybrid proof of concept without changing its public command-line interface or its existing Python test behaviour. The feature is intentionally a thin transport, persistence, authentication, and presentation layer around the current hybrid planner, resolver, LibreNMS adapter, deterministic response, and grounded investigation synthesis pipeline.

The v1 safety boundary is strict:

- The chat service invokes only the existing read-only LibreNMS capabilities: device, ports, alerts, and events.
- The planner does not select a device or claim operational truth; the resolver and the real LibreNMS adapter retain those responsibilities.
- Investigation generation is never streamed directly from Qwen. It is buffered, mechanically validated, judged, and only then exposed as answer chunks. Rejected text is never sent to a browser, persisted, or logged.
- Ambiguous and no-match resolver outcomes are successful user-visible results, not backend failures. They do not trigger a guessed device lookup.
- v1 has no rename, search, attachments, branching, message editing, or regenerate action for completed messages.

No LibreNMS core package, core Vite configuration, or core application source is modified. The LibreNMS integration is a local plugin and static asset deployment.

## Architecture

```text
LibreNMS browser page
  -> relative /ai-api/v1 requests and fetch-based SSE reader
  -> VM Nginx /ai-api/ reverse proxy (no buffering or cache)
  -> Mac 192.168.64.1:8765 FastAPI/Uvicorn service
  -> existing hybrid pipeline and real LibreNMS adapter

SQLite stores user-owned threads, messages, run state, and summary metrics.
```

The service is added below `librenms-hybrid-poc/chat_service/` and uses FastAPI `0.141.1` with Uvicorn `0.52.4`. The existing hybrid pipeline remains importable and callable as it is today. A small integration adapter supplies an optional event observer and cancellation predicate at real planner, resolver, LibreNMS, and synthesis boundaries; it does not replace orchestration semantics or add a parallel planner/resolver implementation.

All elapsed durations use `time.perf_counter()` (or `time.perf_counter_ns()` converted to milliseconds). `resolver_ms` is the current resolver execution duration exposed by the pipeline. `backend_ms` accumulates only actual LibreNMS adapter calls; it excludes resolver work, formatting, storage, serialization, validation, and SSE delivery. `planner_ms`, `synthesis_ms`, `time_to_first_token_ms`, `time_to_first_visible_chunk_ms`, and `total_ms` are measured from their corresponding real boundaries.

## Python Service Components

`chat_service/app.py` owns FastAPI routes, authentication dependency wiring, request validation, and SSE response creation. `chat_service/store.py` owns the SQLite connection configuration, migrations, ownership-scoped repository operations, and no-content persistence policy. `chat_service/auth.py` verifies the signed LibreNMS identity. `chat_service/runs.py` owns one active run per thread, event sequencing, cancellation coordination, and pipeline-to-event translation. `chat_service/pipeline_adapter.py` is the only service module that imports the hybrid pipeline and maps its real stages to the observer contract. `chat_service/logging.py` produces the restricted JSON log records.

The optional pipeline integration contract is conceptually:

- An observer receives a stage name and `started` or `completed` boundary notification.
- A cancellation predicate is checked before a stage starts and before any next stage begins.
- A stage can report monotonic duration and metadata that contains no user content.

For a non-investigation route, answer text is produced only after the existing pipeline result is final. For an investigation route, the adapter buffers the full synthesis output. If the generation implementation can signal its first token, the adapter measures `time_to_first_token_ms` at that signal; otherwise that metric is `null`. It completes mechanical grounding validation and the existing judge before emitting any `answer.delta`. On rejection or a judge failure, the adapter uses the existing deterministic evidence fallback, sets `used_fallback` to `true`, and emits only that fallback. The first emitted validated answer byte sets `time_to_first_visible_chunk_ms`; it is `null` when no answer chunk is emitted.

Cancellation is driven by the request stream lifecycle. The browser cancels the fetch that created the SSE response; the service's predicate observes the disconnect and marks the run cancelled. The predicate is also checked between every stage, so cancellation prevents later stages rather than attempting to interrupt an in-progress opaque model or adapter call. The completed event reports the cancellation outcome; no later stage event or answer delta may follow it.

## Persistence and Data Handling

SQLite is local to the Mac service and opens each connection with WAL journal mode, foreign keys enabled, and a busy timeout. Migrations are idempotent and tracked through a single-row `schema_version` table. The database contains only the following logical records:

| Table | Required fields | Rules |
| --- | --- | --- |
| `schema_version` | `version`, `applied_at` | Records the latest completed migration. |
| `threads` | `id`, `user_sub`, `title`, `created_at`, `updated_at` | Every access filters by `user_sub`; `title` is created deterministically after the first question. |
| `messages` | `id`, `thread_id`, `role`, `content`, `created_at` | `role` is `user` or `assistant`; foreign key cascades with its thread. |
| `runs` | `id`, `thread_id`, `client_message_id`, `status`, `started_at`, `completed_at`, `used_fallback`, metric columns, `error_stage`, `error_code` | A partial unique index permits at most one active run per thread. |

Only chat messages and summary metrics are persisted. The service never persists prompts, raw LibreNMS payloads, resolver candidates, grounding evidence, Qwen tokens, or rejected generated text. It stores the accepted final assistant response only after completion. A cancelled or failed run stores its state, error stage/code where applicable, and safe summary metrics, but creates no assistant message.

The first accepted user message assigns a deterministic title: whitespace-normalize the first question, take its first 60 Unicode characters, and use that value without an LLM or an ellipsis. An empty title cannot occur because run content is validated before insertion.

## Authentication and Authorization

The LibreNMS plugin signs the current authorized user's identity using a shared secret. The service accepts only the following token format:

```text
v1.<base64url-json>.<base64url-hmac-sha256>
```

The JSON payload must contain `sub`, `name`, `iss`, `aud`, `iat`, and `exp`. The verifier requires `iss` equal to `librenms`, `aud` equal to `ai-assistant`, and `exp` exactly `iat + 3600`; it validates the HMAC-SHA-256 signature with the configured shared 32-byte secret. It accepts an `iat` at most 30 seconds later than the service wall clock and rejects an `iat` more than 30 seconds in the future. Expiry has no grace period: a token with `exp` at or before the service wall clock is expired. It rejects malformed base64url, missing claims, invalid types, expired tokens, future-issued tokens outside that 30-second allowance, and invalid signatures. `sub` is the authorization principal and is the sole ownership key; `name` is display metadata only.

The plugin stores the same 32-byte secret in its settings. The Mac service reads it only from its environment. It is neither written to the database nor exposed to client JavaScript. Development identity support is available only when `AI_DEV_AUTH=1` is set on the Mac service; production startup rejects development-auth configuration and the production bundle contains no development token or secret.

Every thread, message history lookup, deletion, and run creation is scoped to the authenticated `sub`. A foreign user receives `404` for a thread identifier they do not own, avoiding cross-user existence disclosure. The plugin is permission-gated by LibreNMS `global-read`; it emits only page root/configuration and the signed identity. PHP contains no AI or pipeline logic.

JSON logs contain only request/run/thread/user identifiers, route, lifecycle stage, monotonic durations, and error codes. They never contain HTTP status, question text, answer text, bearer tokens, raw API payloads, prompts, grounding material, or model tokens.

## HTTP and SSE Contract

All browser production requests use relative paths beginning `/ai-api/v1`; the browser must not construct a host, port, or Mac address. The standalone Vite shell proxies `/ai-api` to the local service during development. Browser requests carry the plugin-issued token as `Authorization: Bearer <token>`.

### REST endpoints

| Method and path | Request | Success | Error behaviour |
| --- | --- | --- | --- |
| `POST /v1/threads` | Empty JSON object | `201` and a new empty thread | `401` for authentication failure. |
| `GET /v1/threads` | None | `200` ordered current-user thread summaries | `401` for authentication failure. |
| `GET /v1/threads/{id}` | None | `200` with current-user thread, messages, and run summaries | `401` or ownership-hidden `404`. |
| `GET /v1/suggestions` | None | `200` with deterministic prompts derived from currently up LibreNMS devices | `401` for authentication failure; `503` with a safe code when LibreNMS inventory is unavailable. |
| `DELETE /v1/threads/{id}` | None | `204` after deleting the current-user thread and its dependent records | `401` or ownership-hidden `404`; an active run is cancelled before deletion completes. |
| `POST /v1/threads/{id}/runs` | `{ "client_message_id": "string", "content": "string" }` | `200`, `Content-Type: text/event-stream` | `400` malformed JSON; `422` empty/whitespace-only or more than 8,000 characters; `401`; ownership-hidden `404`; `409` active run for the same thread or duplicate `client_message_id` for the same owner/thread. |

`client_message_id` is a client-generated, non-empty identifier used to correlate an optimistic user message with the run. A duplicate `client_message_id` for the same owner and thread always returns HTTP `409` before a new stream starts and creates no message or run. It never returns a stored result. A different thread may have an active run at the same time.

There is no resume or replay endpoint in v1. An SSE connection is one request attempt; after a transport interruption, the client refetches thread state and exposes retry when the prior run failed or was cancelled. A completed-message regenerate control is explicitly absent.

### Event stream

Each event uses SSE `event:` and JSON `data:` fields. Data always includes `run_id`. The ordered lifecycle is:

1. `run.started`
2. `planner.started`, then `planner.completed`
3. `resolver.started`, then `resolver.completed`
4. `librenms.started`, then `librenms.completed`
5. For investigation only, `synthesis.started`, then `synthesis.completed`
6. Zero or more `answer.delta`
7. `completed`

Routes that resolve ambiguous, no-match, unsupported, or planner-safe outcomes emit the stages actually entered and a safe final answer; they do not invent skipped backend or synthesis events. A terminal error emits `error` after its last completed stage and then `completed`; no `answer.delta` follows an error. A cancellation emits `completed` with `status` `cancelled` after the final entered stage and no later stage events. The service sends an SSE comment heartbeat at least every 15 seconds while a run remains open.

Event payloads are limited to:

| Event | Data fields |
| --- | --- |
| `run.started` | `run_id`, `thread_id`, `client_message_id` |
| `*.started` | `run_id`, `stage` |
| `*.completed` | `run_id`, `stage`, `duration_ms` |
| `answer.delta` | `run_id`, `message_id`, `delta` |
| `error` | `run_id`, `stage`, `code`, `retryable`, `message` |
| `completed` | `run_id`, `status`, `message_id` when accepted, `used_fallback`, `metrics` |

`error` has the stable shape `{stage, code, retryable, message}`. `message` is a short safe user-facing explanation, never an exception trace or raw upstream response. Codes distinguish validation, authentication, storage, planner, resolver, LibreNMS, synthesis, cancellation, and internal failures. Authentication and request-shape failures are ordinary HTTP errors before a stream starts; operational failures after a run starts use SSE `error`.

The `metrics` object has exactly these fields, each a non-negative integer millisecond value or `null` when inherently unavailable: `planner_ms`, `resolver_ms`, `backend_ms`, `synthesis_ms`, `time_to_first_token_ms`, `time_to_first_visible_chunk_ms`, and `total_ms`. `used_fallback` is a boolean.

## Frontend and Accessibility

The reusable frontend lives under `chat-ui/` and is built with Vite `8`, React `19.2.8`, ReactDOM `19.2.8`, and `@assistant-ui/react` `0.15.17`, all exact-pinned with a committed lockfile. It uses a custom `ExternalStoreRuntime` backed by an application-owned reducer and store. It does not use AI SDK, Next.js, or assistant-ui's wire protocol.

The selected visual direction is **Native Assistant**. The existing LibreNMS top navigation and dark visual language remain recognizable, while the plugin content is a purpose-built AI workspace rather than a generic dashboard panel. The desktop layout has a persistent conversation sidebar and a focused chat surface; the sidebar becomes a focus-managed drawer on narrow screens. Typography, borders, neutral surfaces, and LibreNMS red are inherited visually without importing LibreNMS CSS into the reusable component or adding global styles.

assistant-ui is the interaction layer, not a hidden provider wrapper. The visible chat surface uses:

- `ThreadPrimitive` for the viewport, empty state, message flow, and suggestions;
- `MessagePrimitive` and `MessagePartPrimitive` for user and accepted assistant messages;
- `ComposerPrimitive` for input, send, and cancellation;
- `SuggestionPrimitive` for clickable, live-inventory starter prompts;
- `ActionBarPrimitive` for actions bound to an accepted assistant message, including copy;
- `AuiIf` for empty, running, failed, and completed presentation;
- `ExternalStoreRuntime` as the bridge to the existing reducer, persisted thread state, and custom HTTP/SSE client.

The registry's generated Tailwind/shadcn thread is not copied wholesale because it would introduce global Tailwind dependencies and conflict with the LibreNMS host page. The application composes the official primitives directly and styles them with scoped CSS Modules. No `assistant-ui init` command is run because this is an existing Vite application with a custom backend and an established component/runtime boundary.

On an empty thread the frontend fetches authenticated suggestions from `/ai-api/v1/suggestions`. The service reads the live LibreNMS device collection, filters to devices whose current status is up, sorts them deterministically, and selects a bounded subset without an LLM. It generates only prompt families already supported by the hybrid pipeline: current device status, down ports, active alerts, and recent events. Every prompt contains a real current hostname. The response shape is an array of `{title, label, prompt}` objects suitable for assistant-ui runtime-driven suggestions. Selecting a suggestion through `SuggestionPrimitive.Trigger send` immediately creates the user message and run.

Suggestion failure does not block chat. If LibreNMS inventory is unavailable, the empty state displays a clear unavailable notice and leaves the composer enabled; it does not show fake, cached, fixture, or invented devices. Suggestions are presentation assistance only and are neither persisted nor logged.

A retryable failed run has no accepted assistant message, so its retry control is a thread-level action rather than a message `ActionBarPrimitive`. Retrying submits the latest user question as a new run and does not masquerade as completed-message regeneration.

Pipeline feedback is specific to the submitted question. The UI derives stage labels exclusively from the run's SSE events: planner classification, resolver device resolution, LibreNMS data retrieval, and synthesis only for routes that actually enter synthesis. It never displays a skipped stage as active and never uses timers to advance progress. Internal model reasoning or chain-of-thought is not exposed.

For investigations, generated synthesis remains buffered and invisible until mechanical validation and judging finish. After acceptance, the service emits the approved response as `answer.delta` chunks so the final answer visibly flows through the assistant message surface. A deterministic fallback follows the same visible chunk path and is marked in message metadata. `time_to_first_token_ms` measures the model's first internal token; `time_to_first_visible_chunk_ms` measures the first approved chunk exposed to the browser.

The complete page has:

- a thread list with create, select, and delete-after-confirmation controls;
- current-thread message history and optimistic message correlation;
- real pipeline progress driven by the SSE stage events, not simulated timers;
- a composer with send, cancel while running, and retry after a retryable terminal result;
- expandable final-run metrics;
- a compact system-vitals summary backed only by the current run's real metrics;
- live, clickable device suggestions in the empty thread state;
- a responsive thread drawer that preserves keyboard operation on narrow screens.

Styling uses CSS Modules only. It adds no global reset and no Tailwind. Keyboard focus is visible, order is logical, controls have accessible names and states, the delete confirmation is focus-managed, the current progress and errors are announced through an appropriate live region, and colour is not the only source of status information. The implementation targets WCAG 2.2 AA, including keyboard operation, focus visibility, target sizing, and responsive reflow.

## LibreNMS Plugin and Deployment

Version-controlled plugin source lives in `integrations/librenms/AiAssistant/` and is deployed to `/opt/librenms/app/Plugins/AiAssistant/`. Built frontend assets are deployed to `/opt/librenms/html/plugins/ai-assistant/`. The plugin provides the LibreNMS menu entry and `/plugin/AiAssistant` page, supplies the page root and non-secret runtime configuration, and supplies the signed current-user identity. It has no AI implementation logic.

The Mac API binds `192.168.64.1:8765`. The UTM guest's Nginx proxies `/ai-api/` to that address using HTTP/1.1, proxy buffering off, proxy caching off, and a 360-second read timeout. The proxy preserves the event stream and does not cache event or API responses.

Deployment is ordered as follows:

1. Run offline Python and frontend tests.
2. Start the Mac API with its configured database path and production identity verifier.
3. Run the standalone Vite smoke check through `/ai-api`.
4. Build and deploy plugin source and static assets to their fixed LibreNMS paths.
5. Install the Nginx include, run `nginx -t`, and reload Nginx only after the configuration test succeeds.
6. Enable the plugin under a `global-read` user and perform the UTM end-to-end acceptance flow.

Rollback is reversible: disable the plugin, remove or revert the Nginx proxy include, reload Nginx after `nginx -t`, and stop the Mac API. Existing LibreNMS core files remain untouched throughout.

## Test and Acceptance Strategy

All 90 existing Python tests must remain green. New Python tests cover authentication claims/signatures/expiry, ownership, title generation, SQLite migration/foreign keys/WAL/busy timeout, active-run conflict, event ordering/heartbeat, cancellation boundaries, metric attribution, no rejected synthesis leakage, fallback results, restricted logging, live-device filtering, deterministic suggestion generation, and safe suggestion failure. They run without a live Qwen service or a live LibreNMS server by using controlled pipeline and adapter seams.

Frontend tests cover the reducer/store, `ExternalStoreRuntime` integration, visible assistant-ui primitives, runtime-driven suggestions, suggestion send, fetch/SSE parsing, stage-to-message behavior, approved chunk assembly, thread/delete/cancel/retry states, responsive drawer semantics, and keyboard/focus/live-region accessibility. Playwright covers the standalone Vite shell with the dev proxy and the authorized real UTM installation. The UTM browser acceptance must prove signed user scoping, live device suggestions, thread lifecycle, real question-specific stage progress, visible approved answer chunking, exact run metrics, ambiguity/no-match success, safe investigation fallback, cancellation preventing later stages, backend-unavailable handling, and no accessible secret or user content in logs/bundled configuration.

## Acceptance Criteria

The feature is accepted only when the existing Python suite remains green, the new service and frontend tests pass, exact dependency pins and lockfile are committed, assistant-ui primitives are visibly responsible for the chat interactions, live suggestions contain only actual up devices, the plugin/assets deploy outside LibreNMS core source, Nginx successfully validates and streams SSE, and authorized UTM Playwright evidence demonstrates the contract above. Production installation requires explicit authorization before any UTM mutation.

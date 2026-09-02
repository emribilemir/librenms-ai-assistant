# Native Assistant UI and Live Suggestions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the LibreNMS plugin page into the approved Native Assistant experience using visible assistant-ui primitives, real pipeline progress/metrics, validated answer chunking, and starter prompts derived from currently up LibreNMS devices.

**Architecture:** Keep the existing FastAPI/SQLite/HTTP-SSE service and application reducer as the source of truth. Add one authenticated read-only suggestions endpoint backed by the existing LibreNMS adapter, expose suggestions through `ExternalStoreRuntime`, and compose the official assistant-ui primitives directly with CSS Modules so no Next.js, AI SDK, Assistant Transport, Tailwind reset, or second orchestration layer is introduced.

**Tech Stack:** Python 3.14, FastAPI 0.141.1, Uvicorn 0.52.4, SQLite, Vite 8.0.0, React/ReactDOM 19.2.8, `@assistant-ui/react` 0.15.17, Jest 30.2.0, Playwright 1.62.1, LibreNMS 26.8.1 local plugin.

**Spec:** `docs/superpowers/specs/2026-09-01-librenms-ai-assistant-chat-design.md`

## Global Constraints

- Preserve the current hybrid `orchestrate()` API, CLI behavior, Python regression suite, and read-only LibreNMS scope.
- Use `ExternalStoreRuntime`; do not add Next.js, Vercel AI SDK, Assistant Cloud, Assistant Transport, AG-UI, A2A, Google ADK, or a second backend.
- Keep `@assistant-ui/react` at exactly `0.15.17`, React/ReactDOM at exactly `19.2.8`, and Vite at exactly `8.0.0`.
- Use assistant-ui primitives for visible chat interactions and CSS Modules for all plugin UI styling; do not add Tailwind, preflight, global reset, or global utility CSS.
- Derive progress only from real SSE events. Do not add fake stages, timers, or simulated token delays.
- Never expose generated investigation text before validation/judging. Chunk only the accepted final answer or deterministic fallback.
- Never persist or log suggestion responses, raw LibreNMS payloads, prompts, bearer tokens, grounding traces, or rejected synthesis text.
- Production browser requests remain relative to `/ai-api/v1`; development continues to use the Vite `/ai-api` proxy.
- Preserve all pre-existing user changes in the worktree. Commit only files named by each task and never add `.env*`, `.superpowers/`, `node_modules/`, build artifacts, screenshots, or runtime databases.

---

### Task 1: Live LibreNMS Device Suggestions

**Files:**
- Create: `librenms-hybrid-poc/chat_service/suggestions.py`
- Modify: `librenms-hybrid-poc/librenms_backend.py`
- Modify: `librenms-hybrid-poc/chat_service/pipeline_adapter.py`
- Modify: `librenms-hybrid-poc/chat_service/app.py`
- Modify: `librenms-hybrid-poc/tests/test_live_backend.py`
- Create: `librenms-hybrid-poc/tests/test_chat_service_suggestions.py`

**Interfaces:**
- Produces: `LibreNMSBackend.list_devices() -> list[dict]` using the read-only `GET /devices` LibreNMS API call.
- Produces: `PipelineAdapter.list_devices() -> list[dict]`, with an injectable `device_source` test seam and the live backend as its default.
- Produces: `build_suggestions(devices: Iterable[Mapping[str, Any]], limit: int = 4) -> list[dict[str, str]]` returning `{title, label, prompt}` entries for normalized up devices only.
- Produces: authenticated `GET /v1/suggestions` returning `{"suggestions": [...]}` or safe HTTP `503` detail `{code, message}`.
- Consumes: the same `PipelineAdapter` backend factory/configuration already used by the live hybrid pipeline; no separate API token or LibreNMS client configuration.

- [ ] **Step 1: Write failing backend and pure suggestion tests**

Add a `/api/v0/devices` response to the controlled HTTP server in `test_live_backend.py`, then assert the normalized device collection:

```python
def test_list_devices_normalizes_status_and_records_one_read_only_call(self):
    backend = self.make_backend()

    devices = backend.list_devices()

    self.assertEqual([device["hostname"] for device in devices], ["lab-down", "lab-up"])
    self.assertEqual([device["status"] for device in devices], [0, 1])
    self.assertEqual(backend.tool_names, ["list_devices"])
```

Add pure generation tests in `test_chat_service_suggestions.py`:

```python
def test_suggestions_use_only_sorted_up_devices():
    devices = [
        {"hostname": "z-down", "status": 0},
        {"hostname": "b-up", "status": "up"},
        {"hostname": "a-up", "status": 1},
        {"hostname": "", "status": 1},
    ]

    result = build_suggestions(devices)

    assert [item["title"] for item in result] == ["a-up durumunu kontrol et", "b-up portlarını incele"]
    assert all(item["prompt"] and item["label"] for item in result)
    assert all("z-down" not in item["prompt"] for item in result)


def test_suggestions_are_deterministic_and_bounded():
    devices = [{"hostname": f"sw-{index:02d}", "status": 1} for index in range(10, 0, -1)]
    first = build_suggestions(devices, limit=4)
    second = build_suggestions(reversed(devices), limit=4)
    assert first == second
    assert len(first) == 4
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
cd librenms-hybrid-poc
python3 -m unittest -v tests.test_live_backend.LibreNMSBackendContractTests.test_list_devices_normalizes_status_and_records_one_read_only_call
python3 -m unittest -v tests.test_chat_service_suggestions
```

Expected: failures because `list_devices` and `build_suggestions` do not exist.

- [ ] **Step 3: Implement the read-only device collection and deterministic generator**

Add to `LibreNMSBackend`:

```python
def list_devices(self):
    try:
        payload = self._get("/devices")
    except Exception:
        self._record("list_devices", {}, None)
        raise
    result = [self._normalize_device(device) for device in ((payload or {}).get("devices") or [])]
    return self._record("list_devices", {}, result)
```

Create `chat_service/suggestions.py` with four supported prompt families and deterministic hostname ordering:

```python
from collections.abc import Iterable, Mapping
from typing import Any

PROMPTS = (
    ("{hostname} durumunu kontrol et", "Güncel cihaz durumu", "{hostname} cihazının mevcut durumunu göster."),
    ("{hostname} portlarını incele", "Down portlar", "{hostname} üzerindeki down portları göster."),
    ("{hostname} alarmlarını kontrol et", "Aktif alarmlar", "{hostname} için aktif alarmları göster."),
    ("{hostname} olaylarını incele", "Son olaylar", "{hostname} cihazının son olaylarını göster."),
)

def build_suggestions(
    devices: Iterable[Mapping[str, Any]], limit: int = 4
) -> list[dict[str, str]]:
    hostnames = sorted({
        str(device.get("hostname", "")).strip()
        for device in devices
        if device.get("status") in (1, True, "1", "true", "up")
        and str(device.get("hostname", "")).strip()
    })[:limit]
    return [
        {
            "title": PROMPTS[index % len(PROMPTS)][0].format(hostname=hostname),
            "label": PROMPTS[index % len(PROMPTS)][1],
            "prompt": PROMPTS[index % len(PROMPTS)][2].format(hostname=hostname),
        }
        for index, hostname in enumerate(hostnames)
    ]
```

Add a narrow inventory seam to `PipelineAdapter` so the suggestion route and live query share the same LibreNMS configuration:

```python
def __init__(self, orchestrator=None, device_source=None):
    self._orchestrator = orchestrator
    self._device_source = device_source

def list_devices(self):
    source = self._device_source
    if source is None:
        source = LibreNMSBackend().list_devices
    return source()
```

- [ ] **Step 4: Write failing authenticated route tests**

Use a controlled adapter device source in `test_chat_service_suggestions.py` and assert authentication, filtering, and safe failure:

```python
def test_get_suggestions_requires_auth_and_returns_live_prompts(client, auth_header, adapter):
    adapter.backend.list_devices.return_value = [
        {"hostname": "lab-j9775a-01", "status": 1},
        {"hostname": "offline", "status": 0},
    ]
    assert client.get("/v1/suggestions").status_code == 401

    response = client.get("/v1/suggestions", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["suggestions"][0]["prompt"] == "lab-j9775a-01 cihazının mevcut durumunu göster."


def test_get_suggestions_returns_safe_503(client, auth_header, adapter):
    adapter.backend.list_devices.side_effect = RuntimeError("secret upstream body")
    response = client.get("/v1/suggestions", headers=auth_header)
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "librenms_unavailable",
        "message": "Canlı cihaz önerileri şu anda alınamıyor.",
    }
    assert "secret upstream body" not in response.text
```

- [ ] **Step 5: Add the route with an injected suggestion device source**

Expose a narrow `suggestion_devices` callable on `create_app`, defaulting to `adapter.list_devices`. Authenticate before invoking it, call `build_suggestions`, and translate every upstream exception to the safe `503` payload. Do not log the device collection or prompts.

```python
@app.get("/v1/suggestions")
async def list_suggestions(authorization: str | None = Header(default=None)):
    identity(authorization)
    try:
        devices = suggestion_devices()
    except Exception:
        raise HTTPException(503, {
            "code": "librenms_unavailable",
            "message": "Canlı cihaz önerileri şu anda alınamıyor.",
        }) from None
    return {"suggestions": build_suggestions(devices)}
```

- [ ] **Step 6: Run focused and full Python tests**

Run:

```bash
cd librenms-hybrid-poc
python3 -m unittest -v tests.test_chat_service_suggestions tests.test_live_backend
python3 -m unittest discover -s . -p 'test_*.py' -v
```

Expected: all focused tests and the complete Python suite pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add librenms-hybrid-poc/chat_service/suggestions.py librenms-hybrid-poc/chat_service/pipeline_adapter.py librenms-hybrid-poc/chat_service/app.py librenms-hybrid-poc/librenms_backend.py librenms-hybrid-poc/tests/test_chat_service_suggestions.py librenms-hybrid-poc/tests/test_live_backend.py
git commit -m "feat(chat-service): add live device suggestions"
```

---

### Task 2: Approved Answer Chunk Delivery

**Files:**
- Modify: `librenms-hybrid-poc/chat_service/app.py`
- Modify: `librenms-hybrid-poc/tests/test_chat_service_sse.py`
- Modify: `librenms-hybrid-poc/tests/test_chat_service_safety.py`

**Interfaces:**
- Produces: `iter_answer_chunks(answer: str, max_chars: int = 72) -> Iterator[str]` that preserves the accepted answer exactly when chunks are concatenated.
- Produces: multiple `answer.delta` frames only after `adapter.run` returns accepted/fallback text and storage completion succeeds.
- Consumes: existing `PipelineAdapter.run(...)` result containing `answer`, `used_fallback`, and final metrics.

- [ ] **Step 1: Write failing exact-reassembly and no-leak tests**

```python
def test_answer_delta_chunks_reassemble_exactly(client, thread, auth_header, successful_adapter):
    successful_adapter.answer = "Birinci cümle tamamlandı. İkinci cümle ağ durumunu açıklıyor. " * 4
    events = collect_sse(client, thread, auth_header, "current status")
    deltas = [event["data"]["delta"] for event in events if event["event"] == "answer.delta"]
    assert len(deltas) > 1
    assert "".join(deltas) == successful_adapter.answer
    assert event_names(events)[-2:] == ["answer.delta", "completed"] or event_names(events)[-1] == "completed"


def test_rejected_synthesis_never_appears_in_any_delta(client, thread, auth_header, fallback_adapter):
    events = collect_sse(client, thread, auth_header, "why did it fail")
    visible = "".join(event["data"]["delta"] for event in events if event["event"] == "answer.delta")
    assert visible == fallback_adapter.safe_fallback
    assert fallback_adapter.rejected_text not in visible
```

- [ ] **Step 2: Run tests and verify the single-delta implementation fails**

Run:

```bash
cd librenms-hybrid-poc
python3 -m unittest -v tests.test_chat_service_sse tests.test_chat_service_safety
```

Expected: the multi-chunk assertion fails while the existing no-leak behavior remains green.

- [ ] **Step 3: Implement deterministic, lossless chunking after validation**

Add a pure helper that prefers whitespace/punctuation boundaries but never changes content:

```python
def iter_answer_chunks(answer, max_chars=72):
    start = 0
    while start < len(answer):
        end = min(len(answer), start + max_chars)
        if end < len(answer):
            boundary = max(answer.rfind(" ", start + 1, end + 1), answer.rfind("\n", start + 1, end + 1))
            if boundary > start:
                end = boundary + 1
        yield answer[start:end]
        start = end
```

Persist the final accepted assistant message before exposing any chunk. Then emit each chunk synchronously without an artificial sleep. Set `time_to_first_visible_chunk_ms` immediately before the first emitted frame and update its stored metric once.

- [ ] **Step 4: Verify ordering, timing, fallback, and cancellation suites**

Run:

```bash
cd librenms-hybrid-poc
python3 -m unittest -v tests.test_chat_service_sse tests.test_chat_service_safety tests.test_chat_service_cancel
python3 -m unittest discover -s . -p 'test_*.py' -v
```

Expected: exact reassembly, no rejected text leakage, one terminal `completed`, and full regression pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add librenms-hybrid-poc/chat_service/app.py librenms-hybrid-poc/tests/test_chat_service_sse.py librenms-hybrid-poc/tests/test_chat_service_safety.py
git commit -m "feat(chat-service): stream approved answer chunks"
```

---

### Task 3: Runtime-Driven Suggestions and Native Assistant Surface

**Files:**
- Modify: `chat-ui/src/api.js`
- Modify: `chat-ui/src/api.test.js`
- Modify: `chat-ui/src/runtime.jsx`
- Modify: `chat-ui/src/App.jsx`
- Modify: `chat-ui/src/App.module.css`
- Modify: `chat-ui/src/App.round1.test.jsx`
- Modify: `chat-ui/src/components/AssistantThread.jsx`
- Modify: `chat-ui/src/components/AssistantThread.module.css`
- Modify: `chat-ui/src/components/RunProgress.jsx`
- Modify: `chat-ui/src/components/RunProgress.module.css`
- Modify: `chat-ui/src/components/RunMetrics.jsx`
- Modify: `chat-ui/src/components/RunMetrics.module.css`
- Modify: `chat-ui/src/components/ThreadDrawer.module.css`
- Modify: `chat-ui/src/components/ThreadList.module.css`
- Modify: `chat-ui/src/components/ChatShell.test.jsx`

**Interfaces:**
- Produces: `getSuggestions(token) -> Promise<Array<{title: string, label: string, prompt: string}>>`.
- Produces: `useLibreNmsExternalStoreRuntime(store, threadId, onSend, onCancel, suggestions)` with the runtime's `suggestions` field populated.
- Produces: `AssistantThread({canRetry, onRetry, suggestionsUnavailable})` composed from assistant-ui primitives.
- Consumes: existing store messages/runs and the authenticated relative `/ai-api/v1/suggestions` endpoint.

- [ ] **Step 1: Write failing API and runtime suggestion tests**

In `api.test.js`:

```javascript
test("loads authenticated live suggestions", async () => {
  global.fetch.mockResolvedValue(response({ suggestions: [{ title: "sw-01", label: "Status", prompt: "sw-01 durumunu göster." }] }));
  await expect(getSuggestions("signed-token")).resolves.toHaveLength(1);
  expect(fetch).toHaveBeenCalledWith("/ai-api/v1/suggestions", expect.objectContaining({
    headers: expect.objectContaining({ Authorization: "Bearer signed-token" }),
  }));
});
```

In `App.round1.test.jsx`, assert the latest bridge input contains the server suggestions and does not replace them with fixtures when the endpoint fails.

- [ ] **Step 2: Run focused frontend tests and verify failure**

Run:

```bash
cd chat-ui
npm test -- --runInBand src/api.test.js src/App.round1.test.jsx
```

Expected: failures because `getSuggestions` and the runtime `suggestions` bridge do not exist.

- [ ] **Step 3: Implement suggestions fetch and runtime bridge**

Add to `api.js`:

```javascript
export async function getSuggestions(token) {
  const payload = await request("/suggestions", token);
  return Array.isArray(payload.suggestions) ? payload.suggestions : [];
}
```

In `runtime.jsx`, add `suggestions` to the external runtime store:

```javascript
const runtimeStore = useMemo(() => ({
  messages,
  convertMessage,
  suggestions,
  isRunning: state.runs[threadId]?.status === "running",
  onNew: async (message) => onSend(message.content?.[0]?.text || ""),
  onCancel: async () => onCancel(),
}), [messages, convertMessage, suggestions, state.runs, threadId, onSend, onCancel]);
```

In `App.jsx`, load threads and suggestions in parallel after a token becomes available. Store suggestions in component state, clear them on token change, set `suggestionsUnavailable` only for non-401 failure, and pass them into the runtime bridge. A 401 continues to use the existing session-expiry path.

- [ ] **Step 4: Write failing visible primitive and interaction tests**

Extend `ChatShell.test.jsx` and `App.round1.test.jsx` to assert:

```javascript
expect(screen.getByRole("button", { name: /a-up durumunu kontrol et/i })).toBeEnabled();
await user.click(screen.getByRole("button", { name: /a-up durumunu kontrol et/i }));
expect(api.runThread).toHaveBeenCalledWith(expect.any(String), expect.any(String), "a-up cihazının mevcut durumunu göster.", expect.any(String), expect.any(AbortSignal), expect.any(Function));
expect(screen.getByLabelText("Pipeline progress")).toHaveTextContent("resolver");
expect(screen.getByRole("button", { name: /copy response/i })).toBeInTheDocument();
expect(screen.getByText("Canlı cihaz önerileri şu anda alınamıyor.")).toBeInTheDocument();
```

Also assert the rendered DOM contains assistant-ui-owned thread, message, composer, suggestion, and action elements rather than only custom buttons with similar labels.

- [ ] **Step 5: Compose the approved Native Assistant UI from primitives**

Use current v0.15 APIs from the downloaded assistant-ui reference:

```jsx
import {
  ActionBarPrimitive,
  AuiIf,
  ComposerPrimitive,
  MessagePartPrimitive,
  MessagePrimitive,
  SuggestionPrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
```

The empty state renders `ThreadPrimitive.Suggestions`; each item renders `SuggestionPrimitive.Trigger send` with `SuggestionPrimitive.Title` and `SuggestionPrimitive.Description`. Assistant messages render `ActionBarPrimitive.Root` with `ActionBarPrimitive.Copy`. The composer uses `ComposerPrimitive.Input`, `Send`, and `Cancel`. Replace deprecated `ThreadPrimitive.Empty`/`ThreadPrimitive.If` with `AuiIf` selectors. Keep failed-run retry as a thread-level action because there is no accepted assistant message to bind to a message action bar.

Place the question-specific `RunProgress` immediately above the pending/answer region and label each actual stage in plain language:

```javascript
const STAGE_COPY = {
  planner: "Soruyu sınıflandırıyor",
  resolver: "Cihazı çözümlüyor",
  librenms: "LibreNMS verisini okuyor",
  synthesis: "Doğrulanmış yanıtı hazırlıyor",
};
```

Keep technical stage keys accessible in secondary text. Render the seven exact server metrics in a compact collapsible `System vitals` region. Never fabricate unavailable metric values.

- [ ] **Step 6: Apply the Native Assistant visual system with CSS Modules**

Implement the approved A direction:

- retain the LibreNMS dark neutral surfaces and red accent;
- use a persistent desktop thread rail and responsive drawer;
- give the assistant viewport a maximum readable line length while using the full available height;
- distinguish operator and assistant messages without oversized chat bubbles;
- display two-column suggestion cards on desktop and one column below 720px;
- show completed/running/waiting/error stages with icon, text, and color;
- keep focus rings, 44px touch targets, AA contrast, and reduced-motion behavior;
- avoid gradients, global selectors, and any host-page layout reset.

- [ ] **Step 7: Run frontend unit and production build checks**

Run:

```bash
cd chat-ui
npm test -- --runInBand
npm run build
```

Expected: all Jest tests pass and Vite emits a production bundle with no unresolved assistant-ui imports or global stylesheet.

- [ ] **Step 8: Commit Task 3**

```bash
git add chat-ui/src/api.js chat-ui/src/api.test.js chat-ui/src/runtime.jsx chat-ui/src/App.jsx chat-ui/src/App.module.css chat-ui/src/App.round1.test.jsx chat-ui/src/components/AssistantThread.jsx chat-ui/src/components/AssistantThread.module.css chat-ui/src/components/RunProgress.jsx chat-ui/src/components/RunProgress.module.css chat-ui/src/components/RunMetrics.jsx chat-ui/src/components/RunMetrics.module.css chat-ui/src/components/ThreadDrawer.module.css chat-ui/src/components/ThreadList.module.css chat-ui/src/components/ChatShell.test.jsx
git commit -m "feat(chat-ui): build native assistant experience"
```

---

### Task 4: Standalone and UTM Acceptance, Clean Deployment, and Push

**Files:**
- Modify: `chat-ui/e2e/standalone.spec.js`
- Modify: `chat-ui/e2e/utm.spec.js`
- Modify: `integrations/librenms/AiAssistant/resources/views/page.blade.php`
- Modify if hashes change: `integrations/librenms/AiAssistant/deployment-manifest.json`
- Modify if acceptance commands change: `integrations/librenms/AiAssistant/docs/deployment.md`

**Interfaces:**
- Consumes: authenticated `/v1/suggestions`, SSE run events, fixed production assets `ai-assistant.js` and `ai-assistant.css`, and the existing `/plugin/AiAssistant` route.
- Produces: repeatable browser evidence that the standalone shell and real UTM plugin use visible assistant-ui primitives, live devices, real progress, accepted chunks, and server metrics.
- Produces: a clean `codex/librenms-ai-assistant` feature branch pushed to the configured GitHub remote.

- [ ] **Step 1: Write failing standalone Playwright scenarios**

Cover the following with route-controlled data:

```javascript
test("live suggestion starts a real assistant-ui run", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /lab-j9775a-01 durumunu kontrol et/i }).click();
  await expect(page.getByText("lab-j9775a-01 cihazının mevcut durumunu göster.")).toBeVisible();
  await expect(page.getByLabel("Pipeline progress")).toContainText("Cihazı çözümlüyor");
  await expect(page.locator('[data-assistant-ui="thread"]')).toBeVisible();
});
```

Add scenarios for suggestion `503`, exact multi-delta assembly, synthesis absent on a direct fact, synthesis present on an investigation, system-vitals metric disclosure, cancel, retry, and first-send creating a thread.

- [ ] **Step 2: Run standalone Playwright and fix only product/test defects**

Run:

```bash
cd chat-ui
npx playwright test e2e/standalone.spec.js --project=chromium
```

Expected: all standalone scenarios pass. If a failure occurs, record the exact selector/network/event mismatch before changing code; do not weaken an assertion that represents the approved contract.

- [ ] **Step 3: Build and package fixed-name production assets**

Run:

```bash
cd chat-ui
npm run build
cd ..
bash integrations/librenms/AiAssistant/scripts/package-assets.sh
```

Update `page.blade.php` cache-busting values and the deployment manifest using the packaged files' actual SHA-256 hashes. Verify the JavaScript bundle contains no API key, development bearer, shared secret, Mac absolute path, or hard-coded `192.168.64.1` URL.

- [ ] **Step 4: Run the complete offline quality gate**

Run:

```bash
cd librenms-hybrid-poc
python3 -m unittest discover -s . -p 'test_*.py' -v
cd ../chat-ui
npm test -- --runInBand
npm run build
npx playwright test e2e/standalone.spec.js --project=chromium
cd ..
python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v
git diff --check
```

Expected: every command exits zero.

- [ ] **Step 5: Commit acceptance and deployment metadata**

```bash
git add chat-ui/e2e/standalone.spec.js chat-ui/e2e/utm.spec.js integrations/librenms/AiAssistant/resources/views/page.blade.php integrations/librenms/AiAssistant/deployment-manifest.json integrations/librenms/AiAssistant/docs/deployment.md
git commit -m "test(librenms): verify native assistant acceptance"
```

- [ ] **Step 6: Deploy to the authorized UTM lab in rollout order**

Use the existing deployment scripts and SSH user `codex@192.168.64.3`. Do not copy `.env` files. Deploy plugin sources to `/opt/librenms/app/Plugins/AiAssistant/`, packaged assets to `/opt/librenms/html/plugins/ai-assistant/`, validate with `sudo nginx -t`, then reload Nginx. Clear LibreNMS caches from `/opt/librenms` so `artisan` resolves:

```bash
cd /opt/librenms
sudo -u librenms php artisan optimize:clear
sudo nginx -t
sudo systemctl reload nginx
```

Verify the Mac API is listening on `192.168.64.1:8765` with the ignored runtime environment before running browser acceptance.

- [ ] **Step 7: Run real UTM browser acceptance**

Run:

```bash
cd chat-ui
AI_UTM_BASE_URL=http://192.168.64.3 npx playwright test e2e/utm.spec.js --project=chromium
```

Acceptance must visibly prove: plugin route mounts inside LibreNMS; assistant-ui thread/composer/suggestions are present; suggestions contain current up devices from the live API; a direct fact emits planner/resolver/LibreNMS but not synthesis; an investigation emits synthesis and multiple accepted deltas; metrics are non-negative real values; history survives refresh; delete confirmation works; cancel/retry work; and backend-down state is safe.

- [ ] **Step 8: Verify both repositories are clean and no secret is tracked**

Run on the Mac feature worktree:

```bash
git status --short
git ls-files | rg '(^|/)\.env($|\.)|ai-chat\.sqlite|playwright-report|test-results'
git grep -n -E 'LIBRENMS_TOKEN=|AI_ASSISTANT_SHARED_SECRET=|OPENAI_API_KEY=|root password'
```

Expected: worktree status is clean after planned commits; tracked-file and secret scans return no credential/runtime artifacts.

Run on the VM:

```bash
cd /opt/librenms
git status --short
```

Expected: LibreNMS core is clean because the plugin and static assets remain local/ignored integration paths.

- [ ] **Step 9: Push the feature branch to GitHub**

Inspect the exact destination first:

```bash
git branch --show-current
git remote -v
git log --oneline --decorate -8
```

Expected branch: `codex/librenms-ai-assistant`. Then push only that branch:

```bash
git push -u origin codex/librenms-ai-assistant
```

Report the remote branch URL, final commit, complete test counts, UTM acceptance result, Mac worktree status, and `/opt/librenms` core status.

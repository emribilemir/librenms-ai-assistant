import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
const mockUseExternalStoreRuntime = jest.fn(() => ({}));
jest.mock("@assistant-ui/react", () => {
  const actual = jest.requireActual("@assistant-ui/react");
  return { ...actual, AssistantRuntimeProvider: ({ children }) => children, useExternalStoreRuntime: (...args) => mockUseExternalStoreRuntime(...args) };
});
jest.mock("./components/AssistantThread", () => {
  const React = require("react");
  return {
    AssistantThread: ({ messages = [], running, onSend, onCancel, canRetry, onRetry, suggestionsUnavailable }) => {
      const [content, setContent] = React.useState("");
      return <section data-assistant-ui="thread">{messages.map((message) => <p key={message.id}>{message.content}</p>)}{suggestionsUnavailable && <p>Canlı cihaz önerileri şu anda alınamıyor.</p>}<label htmlFor="investigation-question">Ask about network state</label><textarea id="investigation-question" value={content} onChange={(event) => setContent(event.target.value)} />{running ? <button type="button" onClick={onCancel}>Cancel run</button> : <button type="button" disabled={!content.trim()} onClick={() => { onSend(content.trim()); setContent(""); }}>Start investigation</button>}{canRetry && <button type="button" onClick={onRetry}>Retry failed investigation</button>}</section>;
    },
  };
});
jest.mock("./components/ThreadList", () => ({
  ThreadList: ({ threads = [], selectedThreadId, onSelect, onDelete }) => (
    <nav aria-label="Kayıtlı sohbetler">
      {threads.map((thread) => <span key={thread.id}><button type="button" aria-current={thread.id === selectedThreadId ? "page" : undefined} onClick={() => onSelect(thread.id)}>{thread.title || "Yeni sohbet"}</button><button type="button" onClick={(event) => onDelete(thread, event.currentTarget)} aria-label={`Delete ${thread.title || "investigation"}`}>×</button></span>)}
    </nav>
  ),
}));
import App from "./App";
import { ApiError } from "./api";
import { AssistantChatStore, createInitialState } from "./store";

const currentMetrics = { planner_ms: 2, resolver_ms: 3, backend_ms: 4, synthesis_ms: null, time_to_first_token_ms: null, time_to_first_visible_chunk_ms: 6, total_ms: 8 };
const demoScenarios = [
  { id: "port-down", label: "Portu düşür", example_question: "Port down?", supported_target_ids: ["lab-j9772a-01"] },
  { id: "port-up", label: "Portu kaldır", example_question: "Port up?", supported_target_ids: ["lab-j9772a-01", "lab-j9772a-02"] },
  { id: "location-change", label: "Konumu değiştir", example_question: "Where?", supported_target_ids: ["lab-j9772a-01"] },
  { id: "device-down-up", label: "Cihazı düşür / geri getir", example_question: "Last down?", supported_target_ids: ["lab-j9772a-01"] },
  { id: "port-down-up-event", label: "Port olayı üret", example_question: "Events?", supported_target_ids: ["lab-j9772a-01"] },
  { id: "investigation-incident", label: "İnceleme olayı hazırla", example_question: "Investigate?", supported_target_ids: ["lab-j9772a-01"] },
];
const demoMetadata = {
  supportedTargets: [
    { id: "lab-j9772a-01", hostname: "lab-j9772a-01", device_id: 1, supported_scenarios: demoScenarios.map((item) => item.id) },
    { id: "lab-j9772a-02", hostname: "lab-j9772a-02", device_id: 2, supported_scenarios: ["port-up"] },
  ],
  scenarios: demoScenarios,
};
const makeApi = (overrides = {}) => ({ listThreads: jest.fn().mockResolvedValue([]), getSuggestions: jest.fn().mockResolvedValue([]), getDevices: jest.fn().mockResolvedValue([]), getDemoMode: jest.fn().mockRejectedValue(new ApiError(404)), setDemoMode: jest.fn(), getDemoScenarios: jest.fn().mockResolvedValue({ supportedTargets: [], scenarios: [] }), runDemoScenario: jest.fn(), resetDemo: jest.fn(), getThread: jest.fn(), createThread: jest.fn(), deleteThread: jest.fn().mockResolvedValue(), runThread: jest.fn(), ...overrides });

test("demo mode off keeps all simulation UI hidden", async () => {
  const api = makeApi();

  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);

  await waitFor(() => expect(api.getDemoMode).toHaveBeenCalledWith("plugin-token"));
  expect(screen.queryByRole("button", { name: "Demo Kontrolleri" })).not.toBeInTheDocument();
});

test("allowed demo mode renders OFF and updates only after the backend confirms ON", async () => {
  const api = makeApi({
    getDemoMode: jest.fn().mockResolvedValue({ allowed: true, enabled: false }),
    setDemoMode: jest.fn().mockResolvedValue({ allowed: true, enabled: true }),
    getDemoScenarios: jest.fn().mockResolvedValue(demoMetadata),
  });

  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);

  const toggle = await screen.findByRole("checkbox", { name: "Demo Modu" });
  expect(toggle).not.toBeChecked();
  fireEvent.click(toggle);
  await waitFor(() => expect(api.setDemoMode).toHaveBeenCalledWith(true, "plugin-token"));
  expect(await screen.findByRole("button", { name: "Demo Kontrolleri" })).toBeVisible();
});

test("demo drawer is Turkish and sends the selected bounded target", async () => {
  const api = makeApi({
    getDemoMode: jest.fn().mockResolvedValue({ allowed: true, enabled: true }),
    getDemoScenarios: jest.fn().mockResolvedValue(demoMetadata),
    runDemoScenario: jest.fn((scenarioId, targetId) => Promise.resolve({
      scenario_id: scenarioId,
      target_id: targetId,
      snmp_state_changed: true,
      librenms_completed: true,
      verified: `${scenarioId} verified`,
      example_question: "Ask the device",
    })),
  });
  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.click(await screen.findByRole("button", { name: "Demo Kontrolleri" }));

  expect(screen.getByRole("dialog", { name: "Demo Kontrolleri" })).toBeVisible();
  const target = screen.getByRole("combobox", { name: "Hedef cihaz" });
  expect(target).toHaveValue("lab-j9772a-01");
  fireEvent.change(target, { target: { value: "lab-j9772a-02" } });
  expect(screen.getByRole("button", { name: "Portu düşür" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Portu kaldır" }));
  await waitFor(() => expect(api.runDemoScenario).toHaveBeenCalledWith("port-up", "lab-j9772a-02", "plugin-token"));
});

test("demo drawer blocks duplicate clicks and renders success, failure and reset", async () => {
  let finishScenario;
  const pending = new Promise((resolve) => { finishScenario = resolve; });
  const api = makeApi({
    getDemoMode: jest.fn().mockResolvedValue({ allowed: true, enabled: true }),
    getDemoScenarios: jest.fn().mockResolvedValue(demoMetadata),
    runDemoScenario: jest.fn().mockReturnValue(pending),
    resetDemo: jest.fn().mockResolvedValue({
      snmp_state_changed: true,
      librenms_completed: true,
      verified: "Baseline restored",
    }),
  });
  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.click(await screen.findByRole("button", { name: "Demo Kontrolleri" }));
  const portDown = screen.getByRole("button", { name: "Portu düşür" });
  fireEvent.click(portDown);
  fireEvent.click(portDown);

  expect(api.runDemoScenario).toHaveBeenCalledTimes(1);
  expect(screen.getByText("Portu düşür çalıştırılıyor…")).toBeVisible();
  await act(async () => finishScenario({
    scenario_id: "port-down",
    snmp_state_changed: true,
    librenms_completed: true,
    verified: "Port 2 is now down",
    example_question: "lab-j9772a-01 port 2 ne durumda?",
  }));
  expect(await screen.findByText("✓ Port 2 is now down")).toBeVisible();
  expect(screen.getByText(/lab-j9772a-01 port 2 ne durumda/)).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "Laboratuvarı sıfırla" }));
  expect(await screen.findByText("✓ Baseline restored")).toBeVisible();
  expect(api.resetDemo).toHaveBeenCalledWith("lab-j9772a-01", "plugin-token");

  api.runDemoScenario.mockRejectedValueOnce(new ApiError(503));
  fireEvent.click(screen.getByRole("button", { name: "Portu kaldır" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Senaryo tamamlanamadı");
});

test("investigation suggestion uses normal chat once and verifies the matching fresh inspection", async () => {
  const question = "lab-j9772a-01 cihazında şu an ne sorun var, son 24 saatte neler olmuş?";
  const expectation = {
    target_id: "lab-j9772a-01",
    hostname: "lab-j9772a-01",
    device_id: 1,
    required_route: "investigation",
    required_tools: ["get_device", "get_ports", "get_alerts", "get_events"],
    required_finding_types: ["port_admin_up_oper_down", "active_alert", "historical_status_transition"],
    required_event_ids: [201, 202],
    required_synthesis_llm_called: true,
  };
  const api = makeApi({
    listThreads: jest.fn().mockResolvedValue([{ id: "thread-a", title: "" }]),
    getDemoMode: jest.fn().mockResolvedValue({ allowed: true, enabled: true }),
    getDemoScenarios: jest.fn().mockResolvedValue(demoMetadata),
    runDemoScenario: jest.fn().mockResolvedValue({
      scenario_id: "investigation-incident",
      target_id: "lab-j9772a-01",
      snmp_state_changed: true,
      librenms_completed: true,
      verified: "İnceleme olayı hazır",
      proof: [
        { id: "port", status: "passed", label: "Port 2: admin up / oper down" },
        { id: "event", status: "passed", label: "Event #203: ifOperStatus up -> down", event_id: 203 },
        { id: "alert", status: "passed", label: "Aktif alarm #88: warning", alert_id: 88 },
      ],
      expected_investigation: expectation,
      example_question: question,
    }),
    runThread: jest.fn(async (_threadId, _clientId, _content, _token, _signal, onEvent) => {
      onEvent("run.started", { run_id: "run-demo", client_message_id: _clientId });
      onEvent("answer.delta", { run_id: "run-demo", message_id: "answer-demo", delta: "Doğrulandı" });
      onEvent("completed", {
        run_id: "run-demo", message_id: "answer-demo", status: "completed", used_fallback: false, metrics: currentMetrics,
        inspection: {
          resolution: { hostname: "lab-j9772a-01", device_id: 1 },
          route: "investigation",
          tools: expectation.required_tools.map((name) => ({ name, args: { device_id: 1 } })),
          findings: [
            { type: "port_admin_up_oper_down", ifIndex: 2 },
            { type: "active_alert", alert_id: 88 },
            { type: "historical_status_transition", from_event_id: 201, to_event_id: 202 },
          ],
          synthesis_llm_called: true,
        },
      });
    }),
  });
  const store = new AssistantChatStore(createInitialState({
    threads: [{ id: "thread-a", title: "" }], selectedThreadId: "thread-a", messages: { "thread-a": [] },
  }));
  render(<App chatStore={store} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.click(await screen.findByRole("button", { name: "Demo Kontrolleri" }));
  fireEvent.click(screen.getByRole("button", { name: "İnceleme olayı hazırla" }));
  expect(await screen.findByText("✓ Event #203: ifOperStatus up -> down")).toBeVisible();
  const ask = screen.getByRole("button", { name: `Sormayı dene: ${question}` });
  fireEvent.click(ask);
  fireEvent.click(ask);

  await waitFor(() => expect(api.runThread).toHaveBeenCalledTimes(1));
  expect(api.runThread.mock.calls[0][2]).toBe(question);
  expect(store.getSnapshot().messages["thread-a"].filter((message) => message.role === "user")).toHaveLength(1);
  expect(await screen.findByText("✓ Route: investigation")).toBeVisible();
  expect(screen.getByRole("status", { name: "İnceleme doğrulaması" })).toBeVisible();
  expect(screen.getByText("✓ Beklenen event kanıtı görüldü")).toBeVisible();
  expect(screen.getByText("✓ Restricted synthesis çalıştı")).toBeVisible();
});

test("loads live suggestions into ExternalStoreRuntime", async () => {
  const suggestions = [{
    title: "lab-j9775a-01 durumunu kontrol et",
    label: "Güncel cihaz durumu",
    prompt: "lab-j9775a-01 cihazının mevcut durumunu göster.",
  }];
  const api = makeApi({ getSuggestions: jest.fn().mockResolvedValue(suggestions) });

  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);

  await waitFor(() => expect(api.getSuggestions).toHaveBeenCalledWith("plugin-token"));
  await waitFor(() => {
    const bridge = mockUseExternalStoreRuntime.mock.calls.at(-1)[0];
    expect(bridge.suggestions).toEqual(suggestions);
  });
});

test("creating consecutive chats advances the deterministic live suggestion window", async () => {
  const first = [{ title: "Status", label: "Cihaz durumu", prompt: "lab açık mı?" }];
  const second = [{ title: "Alarm", label: "Aktif alarmlar", prompt: "lab alarmı var mı?" }];
  const api = makeApi({
    getSuggestions: jest.fn()
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second),
    createThread: jest.fn().mockResolvedValue({ id: "next", title: "" }),
  });
  const chatStore = new AssistantChatStore(createInitialState({
    threads: [{ id: "active", title: "Current" }],
    selectedThreadId: "active",
    messages: { active: [{ id: "u", role: "user", content: "Current" }] },
  }));
  render(<App chatStore={chatStore} identity={{ token: "plugin-token" }} api={api} />);
  await waitFor(() => expect(api.getSuggestions).toHaveBeenCalledWith("plugin-token"));

  await act(async () => mockUseExternalStoreRuntime.mock.calls.at(-1)[0].adapters.threadList.onSwitchToNewThread());

  await waitFor(() => expect(api.getSuggestions).toHaveBeenCalledWith("plugin-token", 1));
  await waitFor(() => {
    const bridge = mockUseExternalStoreRuntime.mock.calls.at(-1)[0];
    expect(bridge.suggestions).toEqual(second);
  });
});

test("keeps manual chat available when live suggestions fail", async () => {
  const api = makeApi({ getSuggestions: jest.fn().mockRejectedValue(new ApiError(503)) });

  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);

  expect(await screen.findByText("Canlı cihaz önerileri şu anda alınamıyor.")).toBeVisible();
  expect(screen.getByLabelText("Ask about network state")).toBeEnabled();
});

test("empty history keeps the composer writable and creates a thread on first send", async () => {
  const api = makeApi({
    createThread: jest.fn().mockResolvedValue({ id: "new-thread", title: "" }),
    runThread: jest.fn(async (_thread, client, _content, _token, _signal, onEvent) => {
      onEvent("run.started", { run_id: "new-run", client_message_id: client });
      onEvent("completed", { run_id: "new-run", status: "completed", used_fallback: false, metrics: currentMetrics });
    }),
    getThread: jest.fn().mockResolvedValue({ id: "new-thread", title: "First question", messages: [], runs: [] }),
  });
  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);

  const composer = screen.getByLabelText("Ask about network state");
  expect(composer).toBeEnabled();
  fireEvent.change(composer, { target: { value: "Is the core switch up?" } });
  fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));

  await waitFor(() => expect(api.createThread).toHaveBeenCalledWith("plugin-token"));
  expect(api.runThread).toHaveBeenCalledWith(
    "new-thread",
    expect.any(String),
    "Is the core switch up?",
    "plugin-token",
    expect.any(AbortSignal),
    expect.any(Function),
  );
});

test("pristine selected thread makes New Chat idempotent after history hydration", async () => {
  const api = makeApi({
    listThreads: jest.fn().mockResolvedValue([{ id: "empty", title: "" }]),
    getThread: jest.fn().mockResolvedValue({ id: "empty", title: "", messages: [], runs: [] }),
    createThread: jest.fn(),
  });
  const chatStore = new AssistantChatStore(createInitialState({
    threads: [{ id: "empty", title: "" }],
    selectedThreadId: "empty",
    messages: { empty: [] },
  }));
  render(<App chatStore={chatStore} identity={{ token: "plugin-token" }} api={api} />);

  await act(async () => mockUseExternalStoreRuntime.mock.calls.at(-1)[0].adapters.threadList.onSwitchToNewThread());

  expect(api.createThread).not.toHaveBeenCalled();
});

test("New Chat is available after the first message and for a running thread", async () => {
  for (const seed of [
    { title: "First question", messages: [{ id: "u", role: "user", content: "First question" }], runs: {} },
    { title: "", messages: [], runs: { active: { id: "r", status: "running" } } },
  ]) {
    const api = makeApi({ createThread: jest.fn().mockResolvedValue({ id: `new-${seed.title || "running"}`, title: "" }) });
    const chatStore = new AssistantChatStore(createInitialState({
      threads: [{ id: "active", title: seed.title }],
      selectedThreadId: "active",
      messages: { active: seed.messages },
      runs: seed.runs,
    }));
    const view = render(<App chatStore={chatStore} identity={{ token: "plugin-token" }} api={api} />);

    await act(async () => mockUseExternalStoreRuntime.mock.calls.at(-1)[0].adapters.threadList.onSwitchToNewThread());

    expect(api.createThread).toHaveBeenCalledTimes(1);
    view.unmount();
  }
});

test("mounted App binds the supplied reducer store to the transcript and refreshes the deterministic title after completion", async () => {
  const chatStore = new AssistantChatStore(createInitialState({ threads: [{ id: "a", title: "" }], selectedThreadId: "a", messages: { a: [{ id: "saved", role: "assistant", content: "Existing observed result" }] } }));
  const api = makeApi({ listThreads: jest.fn().mockResolvedValue([{ id: "a", title: "" }]), runThread: jest.fn(async (_thread, client, _content, _token, _signal, onEvent) => { onEvent("run.started", { run_id: "r", client_message_id: client }); onEvent("answer.delta", { run_id: "r", message_id: "m", delta: "Validated result" }); onEvent("completed", { run_id: "r", status: "completed", message_id: "m", used_fallback: false, metrics: currentMetrics }); }), getThread: jest.fn().mockResolvedValue({ id: "a", title: "Core uplink degraded", messages: [{ id: "m", role: "assistant", content: "Validated result" }], runs: [] }) });
  render(<App chatStore={chatStore} identity={{ token: "plugin-token" }} api={api} />);
  expect(screen.getByText("Existing observed result")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Ask about network state"), { target: { value: "Why degraded?" } });
  fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "Core uplink degraded" })).toBeVisible());
  expect(screen.getByText("Validated result")).toBeVisible();
  const bridge = mockUseExternalStoreRuntime.mock.calls.at(-1)[0];
  expect(bridge.messages).toEqual([expect.objectContaining({ content: "Validated result" })]);
  expect(bridge.convertMessage(bridge.messages[0])).toMatchObject({ content: [{ type: "text", text: "Validated result" }] });
});

test("mounted App reports a 409 run conflict without retrying or retaining an unsafe optimistic message", async () => {
  const chatStore = new AssistantChatStore(createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a", messages: { a: [] } }));
  const api = makeApi({ listThreads: jest.fn().mockResolvedValue([{ id: "a", title: "Core" }]), runThread: jest.fn().mockRejectedValue(new ApiError(409)) });
  render(<App chatStore={chatStore} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.change(screen.getByLabelText("Ask about network state"), { target: { value: "Check core" } }); fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("already has a run");
  expect(screen.queryByRole("button", { name: "Retry failed investigation" })).not.toBeInTheDocument();
  expect(chatStore.getSnapshot().messages.a).toEqual([]);
});

test("mounted App handles a 401 as an expired session without offering retry", async () => {
  const api = makeApi({ listThreads: jest.fn().mockRejectedValue(new ApiError(401)) });
  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("LibreNMS oturumunun süresi doldu");
  expect(screen.queryByRole("button", { name: "Retry failed investigation" })).not.toBeInTheDocument();
});

test("mounted App aborts an active stream before deletion and ignores its late answer", async () => {
  const chatStore = new AssistantChatStore(createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a", messages: { a: [] } }));
  let lateEvent; let aborted = false;
  const api = makeApi({ listThreads: jest.fn().mockResolvedValue([{ id: "a", title: "Core" }]), runThread: jest.fn((_thread, client, _content, _token, signal, onEvent) => new Promise((resolve, reject) => { lateEvent = onEvent; onEvent("run.started", { run_id: "r", client_message_id: client }); signal.addEventListener("abort", () => { aborted = true; reject(new DOMException("Aborted", "AbortError")); }); })) });
  render(<App chatStore={chatStore} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.change(screen.getByLabelText("Ask about network state"), { target: { value: "Check core" } }); fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));
  await screen.findByRole("button", { name: "Cancel run" });
  fireEvent.click(screen.getByRole("button", { name: "Delete Core" })); fireEvent.click(screen.getByRole("button", { name: "Sohbeti sil" }));
  await waitFor(() => expect(api.deleteThread).toHaveBeenCalledWith("a", "plugin-token"));
  expect(aborted).toBe(true);
  lateEvent("answer.delta", { run_id: "r", message_id: "late", delta: "Late answer" });
  expect(screen.queryByText("Late answer")).not.toBeInTheDocument();
});

test("multiple active streams are tracked per thread so deleting one does not abort the other", async () => {
  const chatStore = new AssistantChatStore(createInitialState({ threads: [{ id: "a", title: "Core" }, { id: "b", title: "Edge" }], selectedThreadId: "a", messages: { a: [], b: [] } }));
  const aborted = [];
  const api = makeApi({ listThreads: jest.fn().mockResolvedValue([{ id: "a", title: "Core" }, { id: "b", title: "Edge" }]), runThread: jest.fn((threadId, client, _content, _token, signal, onEvent) => new Promise((resolve, reject) => { onEvent("run.started", { run_id: `r-${threadId}`, client_message_id: client }); signal.addEventListener("abort", () => { aborted.push(threadId); reject(new DOMException("Aborted", "AbortError")); }); })) });
  render(<App chatStore={chatStore} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.change(screen.getByLabelText("Ask about network state"), { target: { value: "Check core" } }); fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));
  await act(async () => { chatStore.dispatch({ type: "thread.selected", threadId: "b" }); });
  fireEvent.change(screen.getByLabelText("Ask about network state"), { target: { value: "Check edge" } }); fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));
  await waitFor(() => expect(api.runThread).toHaveBeenCalledTimes(2));
  fireEvent.click(screen.getByRole("button", { name: "Delete Core" })); fireEvent.click(screen.getByRole("button", { name: "Sohbeti sil" }));
  await waitFor(() => expect(api.deleteThread).toHaveBeenCalledWith("a", "plugin-token"));
  expect(aborted).toEqual(["a"]);
});

test("completion title refresh does not switch away from a thread selected while the refresh was pending", async () => {
  const chatStore = new AssistantChatStore(createInitialState({ threads: [{ id: "a", title: "" }, { id: "b", title: "Edge" }], selectedThreadId: "a", messages: { a: [], b: [] } }));
  let resolveDetail;
  const api = makeApi({ listThreads: jest.fn().mockResolvedValue([{ id: "a", title: "" }, { id: "b", title: "Edge" }]), runThread: jest.fn(async (_thread, client, _content, _token, _signal, onEvent) => { onEvent("run.started", { run_id: "r-a", client_message_id: client }); onEvent("completed", { run_id: "r-a", status: "completed", used_fallback: false, metrics: currentMetrics }); }), getThread: jest.fn(() => new Promise((resolve) => { resolveDetail = resolve; })) });
  render(<App chatStore={chatStore} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.change(screen.getByLabelText("Ask about network state"), { target: { value: "Check core" } }); fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));
  await waitFor(() => expect(api.getThread).toHaveBeenCalledWith("a", "plugin-token"));
  await act(async () => { chatStore.dispatch({ type: "thread.selected", threadId: "b" }); }); await act(async () => { resolveDetail({ id: "a", title: "Core title", messages: [], runs: [] }); });
  await waitFor(() => expect(chatStore.getSnapshot().threads.find((thread) => thread.id === "a").title).toBe("Core title"));
  expect(chatStore.getSnapshot().selectedThreadId).toBe("b");
});

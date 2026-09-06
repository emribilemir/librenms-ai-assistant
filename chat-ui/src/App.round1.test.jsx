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
  { id: "port-down", label: "Port Down", example_question: "Port down?" },
  { id: "port-up", label: "Port Up", example_question: "Port up?" },
  { id: "location-change", label: "Location Change", example_question: "Where?" },
  { id: "device-down-up", label: "Device Down/Up", example_question: "Last down?" },
  { id: "port-down-up-event", label: "Generate Port Event", example_question: "Events?" },
];
const makeApi = (overrides = {}) => ({ listThreads: jest.fn().mockResolvedValue([]), getSuggestions: jest.fn().mockResolvedValue([]), getDemoScenarios: jest.fn().mockResolvedValue([]), runDemoScenario: jest.fn(), resetDemo: jest.fn(), getThread: jest.fn(), createThread: jest.fn(), deleteThread: jest.fn().mockResolvedValue(), runThread: jest.fn(), ...overrides });

test("demo mode off keeps all simulation UI hidden", async () => {
  const api = makeApi();

  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);

  await waitFor(() => expect(api.getDemoScenarios).toHaveBeenCalledWith("plugin-token"));
  expect(screen.queryByRole("button", { name: "Demo Controls" })).not.toBeInTheDocument();
});

test("demo mode on opens the bounded drawer and triggers all five scenarios", async () => {
  const api = makeApi({
    getDemoScenarios: jest.fn().mockResolvedValue(demoScenarios),
    runDemoScenario: jest.fn((scenarioId) => Promise.resolve({
      scenario_id: scenarioId,
      snmp_state_changed: true,
      librenms_completed: true,
      verified: `${scenarioId} verified`,
      example_question: "Ask the device",
    })),
  });
  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.click(await screen.findByRole("button", { name: "Demo Controls" }));

  expect(screen.getByRole("dialog", { name: "Demo Controls" })).toBeVisible();
  expect(screen.getByText((_, element) => element.textContent === "Target: lab-j9772a-01")).toBeVisible();
  for (const scenario of demoScenarios) {
    fireEvent.click(screen.getByRole("button", { name: scenario.label }));
    await waitFor(() => expect(api.runDemoScenario).toHaveBeenCalledWith(scenario.id, "plugin-token"));
  }
  expect(api.runDemoScenario).toHaveBeenCalledTimes(5);
});

test("demo drawer blocks duplicate clicks and renders success, failure and reset", async () => {
  let finishScenario;
  const pending = new Promise((resolve) => { finishScenario = resolve; });
  const api = makeApi({
    getDemoScenarios: jest.fn().mockResolvedValue(demoScenarios),
    runDemoScenario: jest.fn().mockReturnValue(pending),
    resetDemo: jest.fn().mockResolvedValue({
      snmp_state_changed: true,
      librenms_completed: true,
      verified: "Baseline restored",
    }),
  });
  render(<App chatStore={new AssistantChatStore()} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.click(await screen.findByRole("button", { name: "Demo Controls" }));
  const portDown = screen.getByRole("button", { name: "Port Down" });
  fireEvent.click(portDown);
  fireEvent.click(portDown);

  expect(api.runDemoScenario).toHaveBeenCalledTimes(1);
  expect(screen.getByText("Running Port Down…")).toBeVisible();
  await act(async () => finishScenario({
    scenario_id: "port-down",
    snmp_state_changed: true,
    librenms_completed: true,
    verified: "Port 2 is now down",
    example_question: "lab-j9772a-01 port 2 ne durumda?",
  }));
  expect(await screen.findByText("✓ Port 2 is now down")).toBeVisible();
  expect(screen.getByText(/lab-j9772a-01 port 2 ne durumda/)).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "Reset Lab" }));
  expect(await screen.findByText("✓ Baseline restored")).toBeVisible();
  expect(api.resetDemo).toHaveBeenCalledWith("plugin-token");

  api.runDemoScenario.mockRejectedValueOnce(new ApiError(503));
  fireEvent.click(screen.getByRole("button", { name: "Port Up" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Scenario could not be completed");
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

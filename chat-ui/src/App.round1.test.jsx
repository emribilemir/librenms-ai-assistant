import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
const mockUseExternalStoreRuntime = jest.fn(() => ({}));
jest.mock("@assistant-ui/react", () => ({ AssistantRuntimeProvider: ({ children }) => children, useExternalStoreRuntime: (...args) => mockUseExternalStoreRuntime(...args) }));
jest.mock("./components/AssistantThread", () => {
  const React = require("react");
  return {
    AssistantThread: ({ messages = [], running, onSend, onCancel, canRetry, onRetry, suggestionsUnavailable }) => {
      const [content, setContent] = React.useState("");
      return <section data-assistant-ui="thread">{messages.map((message) => <p key={message.id}>{message.content}</p>)}{suggestionsUnavailable && <p>Canlı cihaz önerileri şu anda alınamıyor.</p>}<label htmlFor="investigation-question">Ask about network state</label><textarea id="investigation-question" value={content} onChange={(event) => setContent(event.target.value)} />{running ? <button type="button" onClick={onCancel}>Cancel run</button> : <button type="button" disabled={!content.trim()} onClick={() => { onSend(content.trim()); setContent(""); }}>Start investigation</button>}{canRetry && <button type="button" onClick={onRetry}>Retry failed investigation</button>}</section>;
    },
  };
});
import App from "./App";
import { ApiError } from "./api";
import { AssistantChatStore, createInitialState } from "./store";

const currentMetrics = { planner_ms: 2, resolver_ms: 3, backend_ms: 4, synthesis_ms: null, time_to_first_token_ms: null, time_to_first_visible_chunk_ms: 6, total_ms: 8 };
const makeApi = (overrides = {}) => ({ listThreads: jest.fn().mockResolvedValue([]), getSuggestions: jest.fn().mockResolvedValue([]), getThread: jest.fn(), createThread: jest.fn(), deleteThread: jest.fn().mockResolvedValue(), runThread: jest.fn(), ...overrides });

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
  expect(await screen.findByRole("alert")).toHaveTextContent("LibreNMS session has expired");
  expect(screen.queryByRole("button", { name: "Retry failed investigation" })).not.toBeInTheDocument();
});

test("mounted App aborts an active stream before deletion and ignores its late answer", async () => {
  const chatStore = new AssistantChatStore(createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a", messages: { a: [] } }));
  let lateEvent; let aborted = false;
  const api = makeApi({ listThreads: jest.fn().mockResolvedValue([{ id: "a", title: "Core" }]), runThread: jest.fn((_thread, client, _content, _token, signal, onEvent) => new Promise((resolve, reject) => { lateEvent = onEvent; onEvent("run.started", { run_id: "r", client_message_id: client }); signal.addEventListener("abort", () => { aborted = true; reject(new DOMException("Aborted", "AbortError")); }); })) });
  render(<App chatStore={chatStore} identity={{ token: "plugin-token" }} api={api} />);
  fireEvent.change(screen.getByLabelText("Ask about network state"), { target: { value: "Check core" } }); fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));
  await screen.findByRole("button", { name: "Cancel run" });
  fireEvent.click(screen.getByRole("button", { name: "Delete Core" })); fireEvent.click(screen.getByRole("button", { name: "Delete investigation" }));
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
  fireEvent.click(screen.getByRole("button", { name: "Delete Core" })); fireEvent.click(screen.getByRole("button", { name: "Delete investigation" }));
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

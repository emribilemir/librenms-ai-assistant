import { createInitialState, reduceAssistantChat } from "./store";

const metrics = {
  planner_ms: 8, resolver_ms: 13, backend_ms: 21, synthesis_ms: null,
  time_to_first_token_ms: null, time_to_first_visible_chunk_ms: 30, total_ms: 34,
};

test("lists, creates, and selects only the current thread", () => {
  let state = createInitialState();
  state = reduceAssistantChat(state, { type: "threads.loaded", threads: [{ id: "a", title: "Core switch" }] });
  state = reduceAssistantChat(state, { type: "thread.created", thread: { id: "b", title: "New investigation" } });
  expect(state.selectedThreadId).toBe("b");
  expect(state.threads.map((thread) => thread.id)).toEqual(["b", "a"]);
});

test("correlates an optimistic client message with the server run", () => {
  let state = createInitialState({ selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "message.optimistic", threadId: "a", clientMessageId: "client-1", content: "Check edge" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", clientMessageId: "client-1", event: "run.started", data: { run_id: "run-1", thread_id: "a", client_message_id: "client-1" } });
  expect(state.messages.a[0]).toMatchObject({ id: "client-1", role: "user", pending: false });
  expect(state.runs.a.clientMessageId).toBe("client-1");
});

test("reduces only exact stream stages and exposes real current progress", () => {
  let state = createInitialState({ selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "planner.started", data: { run_id: "r", stage: "planner" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "planner.completed", data: { run_id: "r", stage: "planner", duration_ms: 8 } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "resolver.started", data: { run_id: "r", stage: "resolver" } });
  expect(state.runs.a.stages).toEqual({ planner: { status: "completed", durationMs: 8 }, resolver: { status: "running" } });
});

test("does not render an answer delta until the server emits a validated delta", () => {
  let state = createInitialState({ selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "r", message_id: "m", delta: "Validated answer" } });
  expect(state.messages.a).toEqual([{ id: "m", role: "assistant", content: "Validated answer", pending: true }]);
});

test("makes retry available only after a retryable terminal error", () => {
  let state = createInitialState({ selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "error", data: { run_id: "r", stage: "librenms", code: "backend_failed", retryable: true, message: "LibreNMS is unavailable" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "r", status: "failed", used_fallback: false, metrics } });
  expect(state.runs.a).toMatchObject({ status: "failed", canRetry: true, error: { code: "backend_failed" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "r", status: "cancelled", used_fallback: false, metrics } });
  expect(state.runs.a.canRetry).toBe(false);
});

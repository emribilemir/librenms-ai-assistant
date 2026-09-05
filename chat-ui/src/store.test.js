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
  expect(state.messages.a[1]).toMatchObject({ id: "run-run-1", role: "assistant", content: "", pending: true, runId: "run-1" });
  expect(state.runs.a.clientMessageId).toBe("client-1");
});

test("reuses the live assistant placeholder when the first validated answer delta arrives", () => {
  let state = createInitialState({ selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "r", message_id: "m", delta: "Validated" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "r", message_id: "m", delta: " answer" } });

  expect(state.messages.a).toEqual([{ id: "m", role: "assistant", content: "Validated answer", pending: true, runId: "r" }]);
});

test("reduces only exact stream stages and exposes real current progress", () => {
  let state = createInitialState({ selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "planner.started", data: { run_id: "r", stage: "planner" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "planner.completed", data: { run_id: "r", stage: "planner", duration_ms: 8 } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "resolver.started", data: { run_id: "r", stage: "resolver" } });
  expect(state.runs.a.stages).toEqual({ planner: { status: "completed", durationMs: 8 }, resolver: { status: "running" } });
});

test("uses REST thread.runs history and exposes the latest persisted metrics", () => {
  let state = createInitialState();
  state = reduceAssistantChat(state, { type: "thread.loaded", thread: { id: "a", title: "Core", messages: [], runs: [{ id: "old", status: "completed", total_ms: 4 }, { id: "new", status: "completed", total_ms: 9, planner_ms: 2 }] } });
  expect(state.runHistory.a).toHaveLength(2);
  expect(state.runs.a).toMatchObject({ id: "new", metrics: { total_ms: 9, planner_ms: 2 } });
});

test("preserves a retryable SSE error when the terminal REST refresh omits its safe message", () => {
  let state = createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "error", data: { run_id: "r", stage: "librenms", code: "backend_unavailable", retryable: true, message: "Unavailable" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "r", status: "failed", used_fallback: false, metrics } });
  state = reduceAssistantChat(state, { type: "thread.loaded", preserveSelection: true, thread: { id: "a", title: "Core", messages: [], runs: [{ id: "r", status: "failed", total_ms: 9 }] } });
  expect(state.runs.a).toMatchObject({ status: "failed", canRetry: true, error: { message: "Unavailable" } });
});

test("rejects stale, wrong-run, and post-terminal stream mutations", () => {
  let state = createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "current", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "current", status: "cancelled", used_fallback: false, metrics } });
  const terminal = state;
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "current", message_id: "late", delta: "must not show" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "planner.started", data: { run_id: "other", stage: "planner" } });
  expect(state).toEqual(terminal);
});

test("does not resurrect a deleted thread from late stream callbacks", () => {
  let state = createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "thread.deleted", threadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "late", message_id: "late", delta: "late answer" } });
  expect(state.messages.a).toBeUndefined();
  expect(state.runs.a).toBeUndefined();
});

test("marks validated fallback answers for the transcript", () => {
  let state = createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "r", message_id: "m", delta: "Safe fallback" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "r", status: "completed", message_id: "m", used_fallback: true, metrics } });
  expect(state.messages.a[0].usedFallback).toBe(true);
});

test("attaches completed navigation targets to the accepted message and preserves them across refresh", () => {
  const navigationTargets = [{ kind: "device", label: "LibreNMS'te cihazı aç", entity_id: 1, href: "/device/1" }];
  let state = createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "r", message_id: "m", delta: "Validated" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "r", status: "completed", message_id: "m", used_fallback: false, navigation_targets: navigationTargets, metrics } });
  expect(state.messages.a[0].navigationTargets).toEqual(navigationTargets);

  state = reduceAssistantChat(state, { type: "thread.loaded", preserveSelection: true, thread: { id: "a", title: "Core", messages: [{ id: "m", role: "assistant", content: "Validated" }], runs: [{ id: "r", status: "completed" }] } });
  expect(state.messages.a[0].navigationTargets).toEqual(navigationTargets);
});

test("attaches completed inspection to the accepted message and preserves it across in-memory refresh", () => {
  const inspection = {
    planner: { request_type: "ports", intent: "device_ports" },
    route: "ports",
    tools: [{ name: "get_ports", args: { device_id: 1 } }],
    findings: [],
    synthesis_llm_called: false,
    navigation_targets: [],
  };
  let state = createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "r", message_id: "m", delta: "Validated" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "r", status: "completed", message_id: "m", used_fallback: false, inspection, metrics } });
  expect(state.messages.a[0].inspection).toEqual(inspection);

  state = reduceAssistantChat(state, { type: "thread.loaded", preserveSelection: true, thread: { id: "a", title: "Core", messages: [{ id: "m", role: "assistant", content: "Validated" }], runs: [{ id: "r", status: "completed" }] } });
  expect(state.messages.a[0].inspection).toEqual(inspection);
});

test("does not render an answer delta until the server emits a validated delta", () => {
  let state = createInitialState({ selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "r", message_id: "m", delta: "Validated answer" } });
  expect(state.messages.a).toEqual([{ id: "m", role: "assistant", content: "Validated answer", pending: true, runId: "r" }]);
});

test("makes retry available only after a retryable terminal error", () => {
  let state = createInitialState({ selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "error", data: { run_id: "r", stage: "librenms", code: "backend_failed", retryable: true, message: "LibreNMS is unavailable" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "r", status: "failed", used_fallback: false, metrics } });
  expect(state.runs.a).toMatchObject({ status: "failed", canRetry: true, error: { code: "backend_failed" } });
  let cancelled = createInitialState({ selectedThreadId: "a" });
  cancelled = reduceAssistantChat(cancelled, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "cancelled", client_message_id: "c" } });
  cancelled = reduceAssistantChat(cancelled, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "cancelled", status: "cancelled", used_fallback: false, metrics } });
  expect(cancelled.runs.a.canRetry).toBe(false);
});

test("error permits only its completed envelope and duplicate run.started cannot reopen a terminal run", () => {
  let state = createInitialState({ selectedThreadId: "a" });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "error", data: { run_id: "r", stage: "librenms", code: "backend_failed", retryable: true, message: "Unavailable" } });
  const errored = state;
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "answer.delta", data: { run_id: "r", message_id: "late", delta: "must not show" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "planner.started", data: { run_id: "r", stage: "planner" } });
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  expect(state).toEqual(errored);
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "completed", data: { run_id: "r", status: "failed", used_fallback: false, metrics } });
  const terminal = state;
  state = reduceAssistantChat(state, { type: "stream.event", threadId: "a", event: "run.started", data: { run_id: "r", client_message_id: "c" } });
  expect(state).toEqual(terminal);
});

test("deleting a thread clears its full run history", () => {
  let state = createInitialState({ threads: [{ id: "a", title: "Core" }], selectedThreadId: "a", runHistory: { a: [{ id: "old" }] } });
  state = reduceAssistantChat(state, { type: "thread.deleted", threadId: "a" });
  expect(state.runHistory.a).toBeUndefined();
});

test("reload maps Task 1 persisted used_fallback summaries onto accepted assistant messages", () => {
  let state = createInitialState();
  state = reduceAssistantChat(state, { type: "thread.loaded", thread: { id: "a", title: "Core", messages: [{ id: "u1", role: "user", content: "Check" }, { id: "a1", role: "assistant", content: "Safe evidence summary" }], runs: [{ id: "r1", client_message_id: "c1", status: "completed", used_fallback: 1, total_ms: 9 }] } });
  expect(state.messages.a.find((message) => message.id === "a1")).toMatchObject({ usedFallback: true });
});

test("background thread refresh updates a detail without stealing another selected thread", () => {
  let state = createInitialState({ threads: [{ id: "a", title: "Old" }, { id: "b", title: "Other" }], selectedThreadId: "b" });
  state = reduceAssistantChat(state, { type: "thread.loaded", preserveSelection: true, thread: { id: "a", title: "Updated", messages: [], runs: [] } });
  expect(state.selectedThreadId).toBe("b");
  expect(state.threads.find((thread) => thread.id === "a").title).toBe("Updated");
});

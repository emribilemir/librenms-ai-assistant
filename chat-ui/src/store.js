export const STAGES = ["planner", "resolver", "librenms", "synthesis"];

export function createInitialState(seed = {}) {
  return { threads: [], selectedThreadId: null, messages: {}, runs: {}, runHistory: {}, drawerOpen: false, ...seed };
}

function messagesFor(state, threadId) { return state.messages[threadId] || []; }

function restoredMessages(messages, history, currentMessages = []) {
  const acceptedRuns = history.filter((run) => run.status === "completed"); let acceptedIndex = 0;
  const currentById = new Map(currentMessages.map((message) => [message.id, message]));
  return messages.map((message) => {
    if (message.role !== "assistant") return message;
    const run = acceptedRuns[acceptedIndex++];
    const current = currentById.get(message.id);
    const navigationTargets = current?.navigationTargets || (Array.isArray(message.navigation_targets) ? message.navigation_targets : null);
    const structuredResult = current?.structuredResult || (message.structured_result && typeof message.structured_result === "object" && !Array.isArray(message.structured_result) ? message.structured_result : null);
    const inspection = current?.inspection;
    return run ? { ...message, runId: run.id, usedFallback: Boolean(run.used_fallback), ...(navigationTargets ? { navigationTargets } : {}), ...(structuredResult ? { structuredResult } : {}), ...(inspection ? { inspection } : {}) } : message;
  });
}

function updateRun(state, threadId, update) {
  return { ...state, runs: { ...state.runs, [threadId]: { ...(state.runs[threadId] || {}), ...update } } };
}

export function reduceAssistantChat(state, action) {
  switch (action.type) {
    case "threads.loaded": return { ...state, threads: action.threads };
    case "thread.created": return { ...state, threads: [action.thread, ...state.threads.filter((thread) => thread.id !== action.thread.id)], selectedThreadId: action.thread.id, messages: { ...state.messages, [action.thread.id]: [] }, drawerOpen: false };
    case "thread.selected": return { ...state, selectedThreadId: action.threadId, drawerOpen: false };
    case "thread.loaded": {
      const history = action.thread.runs || [];
      const latest = history.at(-1);
      const currentRun = state.runs[action.thread.id];
      const persistedMetrics = latest ? Object.fromEntries(Object.entries(latest).filter(([key]) => key.endsWith("_ms"))) : null;
      const run = latest ? {
        ...latest,
        clientMessageId: latest.client_message_id || (
          currentRun?.id === latest.id ? currentRun.clientMessageId : undefined
        ),
        usedFallback: Boolean(latest.used_fallback),
        metrics: persistedMetrics,
        // The REST summary intentionally excludes the safe error message and
        // retryability. Preserve the stream terminal envelope for this run.
        ...(currentRun?.id === latest.id && currentRun.error ? {
          error: currentRun.error,
          canRetry: latest.status === "failed" && Boolean(currentRun.error.retryable),
        } : {}),
      } : currentRun;
      const thread = { ...action.thread }; delete thread.messages; delete thread.runs;
      const threads = state.threads.some((item) => item.id === thread.id) ? state.threads.map((item) => item.id === thread.id ? { ...item, ...thread } : item) : [thread, ...state.threads];
      return { ...state, threads, selectedThreadId: action.preserveSelection ? state.selectedThreadId : action.thread.id, messages: { ...state.messages, [action.thread.id]: restoredMessages(action.thread.messages || [], history, messagesFor(state, action.thread.id)) }, runs: run ? { ...state.runs, [action.thread.id]: run } : state.runs, runHistory: { ...state.runHistory, [action.thread.id]: history } };
    }
    case "thread.deleted": {
      const threads = state.threads.filter((thread) => thread.id !== action.threadId);
      const { [action.threadId]: deletedMessages, ...messages } = state.messages;
      const { [action.threadId]: deletedRun, ...runs } = state.runs;
      const { [action.threadId]: deletedHistory, ...runHistory } = state.runHistory;
      return { ...state, threads, messages, runs, runHistory, selectedThreadId: state.selectedThreadId === action.threadId ? (threads[0]?.id || null) : state.selectedThreadId };
    }
    case "drawer.open": return { ...state, drawerOpen: true };
    case "drawer.close": return { ...state, drawerOpen: false };
    case "message.optimistic": return { ...state, messages: { ...state.messages, [action.threadId]: [...messagesFor(state, action.threadId), { id: action.clientMessageId, role: "user", content: action.content, pending: true }] } };
    case "message.discard": return { ...state, messages: { ...state.messages, [action.threadId]: messagesFor(state, action.threadId).filter((message) => message.id !== action.clientMessageId) } };
    case "run.failed": return (state.selectedThreadId === action.threadId || state.threads.some((thread) => thread.id === action.threadId)) ? updateRun(state, action.threadId, { status: "failed", error: action.error, canRetry: Boolean(action.error.retryable) }) : state;
    case "stream.event": return reduceStreamEvent(state, action);
    default: return state;
  }
}

function reduceStreamEvent(state, { threadId, clientMessageId, event, data }) {
  const threadExists = state.selectedThreadId === threadId || state.threads.some((thread) => thread.id === threadId);
  if (!threadExists) return state;
  if (event === "run.started") {
    const existing = state.runs[threadId];
    const correlation = data.client_message_id || clientMessageId;
    if ((clientMessageId && correlation !== clientMessageId) || (existing && (existing.id === data.run_id || existing.status === "running" || existing.status === "error"))) return state;
    const acknowledged = messagesFor(state, threadId).map((message) => message.id === (data.client_message_id || clientMessageId) ? { ...message, pending: false } : message);
    const placeholder = { id: `run-${data.run_id}`, role: "assistant", content: "", pending: true, runId: data.run_id };
    const messages = acknowledged.some((message) => message.runId === data.run_id) ? acknowledged : [...acknowledged, placeholder];
    return updateRun({ ...state, messages: { ...state.messages, [threadId]: messages } }, threadId, { id: data.run_id, clientMessageId: correlation, status: "running", stages: {}, canRetry: false, error: null });
  }
  const currentRun = state.runs[threadId];
  if (!currentRun || currentRun.id !== data.run_id || (currentRun.status !== "running" && !(event === "completed" && currentRun.status === "error"))) return state;
  if (event.endsWith(".started") || event.endsWith(".completed")) {
    const stage = data.stage;
    if (!STAGES.includes(stage)) return state;
    const run = currentRun;
    const status = event.endsWith(".started") ? "running" : "completed";
    return updateRun(state, threadId, { stages: { ...run.stages, [stage]: status === "completed" ? { status, durationMs: data.duration_ms } : { status } } });
  }
  if (event === "answer.delta") {
    const prior = messagesFor(state, threadId);
    const existing = prior.find((message) => message.id === data.message_id);
    const placeholder = prior.find((message) => message.role === "assistant" && message.runId === data.run_id && message.pending);
    const messages = existing
      ? prior.map((message) => message.id === data.message_id ? { ...message, content: `${message.content}${data.delta}` } : message)
      : placeholder
        ? prior.map((message) => message === placeholder ? { ...message, id: data.message_id, content: data.delta } : message)
        : [...prior, { id: data.message_id, role: "assistant", content: data.delta, pending: true, runId: data.run_id }];
    return { ...state, messages: { ...state.messages, [threadId]: messages } };
  }
  if (event === "error") return updateRun(state, threadId, { status: "error", error: { stage: data.stage, code: data.code, message: data.message, retryable: data.retryable } });
  if (event === "completed") {
    const messages = messagesFor(state, threadId).map((message) => {
      const isAnswer = data.message_id ? message.id === data.message_id : message.runId === data.run_id;
      return isAnswer ? { ...message, pending: false, usedFallback: Boolean(data.used_fallback), ...(Array.isArray(data.navigation_targets) ? { navigationTargets: data.navigation_targets } : {}), ...(data.structured_result && typeof data.structured_result === "object" && !Array.isArray(data.structured_result) ? { structuredResult: data.structured_result } : {}), ...(data.inspection && typeof data.inspection === "object" && !Array.isArray(data.inspection) ? { inspection: data.inspection } : {}) } : message;
    });
    return updateRun({ ...state, messages: { ...state.messages, [threadId]: messages } }, threadId, { status: data.status, metrics: data.metrics, usedFallback: data.used_fallback, canRetry: data.status === "failed" && Boolean(state.runs[threadId]?.error?.retryable) });
  }
  return state;
}

export class AssistantChatStore {
  constructor(initialState = createInitialState()) { this.state = initialState; this.listeners = new Set(); }
  getSnapshot = () => this.state;
  subscribe = (listener) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  dispatch = (action) => { this.state = reduceAssistantChat(this.state, action); this.listeners.forEach((listener) => listener()); };
}

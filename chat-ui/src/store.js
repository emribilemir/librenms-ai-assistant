export const STAGES = ["planner", "resolver", "librenms", "synthesis"];

export function createInitialState(seed = {}) {
  return { threads: [], selectedThreadId: null, messages: {}, runs: {}, runHistory: {}, drawerOpen: false, ...seed };
}

function messagesFor(state, threadId) { return state.messages[threadId] || []; }

function restoredMessages(messages, history) {
  const acceptedRuns = history.filter((run) => run.status === "completed"); let acceptedIndex = 0;
  return messages.map((message) => {
    if (message.role !== "assistant") return message;
    const run = acceptedRuns[acceptedIndex++];
    return run ? { ...message, usedFallback: Boolean(run.used_fallback) } : message;
  });
}

function updateRun(state, threadId, update) {
  return { ...state, runs: { ...state.runs, [threadId]: { ...(state.runs[threadId] || {}), ...update } } };
}

export function reduceAssistantChat(state, action) {
  switch (action.type) {
    case "threads.loaded": return { ...state, threads: action.threads };
    case "thread.created": return { ...state, threads: [action.thread, ...state.threads], selectedThreadId: action.thread.id, messages: { ...state.messages, [action.thread.id]: [] }, drawerOpen: false };
    case "thread.selected": return { ...state, selectedThreadId: action.threadId, drawerOpen: false };
    case "thread.loaded": {
      const history = action.thread.runs || [];
      const latest = history.at(-1);
      const run = latest ? { ...latest, usedFallback: Boolean(latest.used_fallback), metrics: Object.fromEntries(Object.entries(latest).filter(([key]) => key.endsWith("_ms"))) } : state.runs[action.thread.id];
      const thread = { ...action.thread }; delete thread.messages; delete thread.runs;
      const threads = state.threads.some((item) => item.id === thread.id) ? state.threads.map((item) => item.id === thread.id ? { ...item, ...thread } : item) : [thread, ...state.threads];
      return { ...state, threads, selectedThreadId: action.preserveSelection ? state.selectedThreadId : action.thread.id, messages: { ...state.messages, [action.thread.id]: restoredMessages(action.thread.messages || [], history) }, runs: run ? { ...state.runs, [action.thread.id]: run } : state.runs, runHistory: { ...state.runHistory, [action.thread.id]: history } };
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
    const messages = messagesFor(state, threadId).map((message) => message.id === (data.client_message_id || clientMessageId) ? { ...message, pending: false } : message);
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
    const messages = existing ? prior.map((message) => message.id === data.message_id ? { ...message, content: `${message.content}${data.delta}` } : message) : [...prior, { id: data.message_id, role: "assistant", content: data.delta, pending: true }];
    return { ...state, messages: { ...state.messages, [threadId]: messages } };
  }
  if (event === "error") return updateRun(state, threadId, { status: "error", error: { stage: data.stage, code: data.code, message: data.message, retryable: data.retryable } });
  if (event === "completed") {
    const messages = data.message_id ? messagesFor(state, threadId).map((message) => message.id === data.message_id ? { ...message, pending: false, usedFallback: Boolean(data.used_fallback) } : message) : messagesFor(state, threadId);
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

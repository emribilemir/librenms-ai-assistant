export const STAGES = ["planner", "resolver", "librenms", "synthesis"];

export function createInitialState(seed = {}) {
  return { threads: [], selectedThreadId: null, messages: {}, runs: {}, drawerOpen: false, ...seed };
}

function messagesFor(state, threadId) { return state.messages[threadId] || []; }

function updateRun(state, threadId, update) {
  return { ...state, runs: { ...state.runs, [threadId]: { ...(state.runs[threadId] || {}), ...update } } };
}

export function reduceAssistantChat(state, action) {
  switch (action.type) {
    case "threads.loaded": return { ...state, threads: action.threads };
    case "thread.created": return { ...state, threads: [action.thread, ...state.threads], selectedThreadId: action.thread.id, messages: { ...state.messages, [action.thread.id]: [] }, drawerOpen: false };
    case "thread.selected": return { ...state, selectedThreadId: action.threadId, drawerOpen: false };
    case "thread.loaded": return { ...state, selectedThreadId: action.thread.id, messages: { ...state.messages, [action.thread.id]: action.thread.messages || [] }, runs: { ...state.runs, [action.thread.id]: action.thread.run || state.runs[action.thread.id] } };
    case "thread.deleted": {
      const threads = state.threads.filter((thread) => thread.id !== action.threadId);
      const { [action.threadId]: deletedMessages, ...messages } = state.messages;
      const { [action.threadId]: deletedRun, ...runs } = state.runs;
      return { ...state, threads, messages, runs, selectedThreadId: state.selectedThreadId === action.threadId ? (threads[0]?.id || null) : state.selectedThreadId };
    }
    case "drawer.open": return { ...state, drawerOpen: true };
    case "drawer.close": return { ...state, drawerOpen: false };
    case "message.optimistic": return { ...state, messages: { ...state.messages, [action.threadId]: [...messagesFor(state, action.threadId), { id: action.clientMessageId, role: "user", content: action.content, pending: true }] } };
    case "stream.event": return reduceStreamEvent(state, action);
    default: return state;
  }
}

function reduceStreamEvent(state, { threadId, clientMessageId, event, data }) {
  if (event === "run.started") {
    const messages = messagesFor(state, threadId).map((message) => message.id === (data.client_message_id || clientMessageId) ? { ...message, pending: false } : message);
    return updateRun({ ...state, messages: { ...state.messages, [threadId]: messages } }, threadId, { id: data.run_id, clientMessageId: data.client_message_id || clientMessageId, status: "running", stages: {}, canRetry: false, error: null });
  }
  if (event.endsWith(".started") || event.endsWith(".completed")) {
    const stage = data.stage;
    if (!STAGES.includes(stage)) return state;
    const run = state.runs[threadId] || { stages: {} };
    const status = event.endsWith(".started") ? "running" : "completed";
    return updateRun(state, threadId, { stages: { ...run.stages, [stage]: status === "completed" ? { status, durationMs: data.duration_ms } : { status } } });
  }
  if (event === "answer.delta") {
    const prior = messagesFor(state, threadId);
    const existing = prior.find((message) => message.id === data.message_id);
    const messages = existing ? prior.map((message) => message.id === data.message_id ? { ...message, content: `${message.content}${data.delta}` } : message) : [...prior, { id: data.message_id, role: "assistant", content: data.delta, pending: true }];
    return { ...state, messages: { ...state.messages, [threadId]: messages } };
  }
  if (event === "error") return updateRun(state, threadId, { error: { stage: data.stage, code: data.code, message: data.message, retryable: data.retryable } });
  if (event === "completed") {
    const messages = data.message_id ? messagesFor(state, threadId).map((message) => message.id === data.message_id ? { ...message, pending: false } : message) : messagesFor(state, threadId);
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

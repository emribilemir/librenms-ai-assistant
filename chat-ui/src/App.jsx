import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { createThread, deleteThread, getThread, listThreads, runThread } from "./api";
import { useLibreNmsExternalStoreRuntime } from "./runtime";
import { AssistantChatStore } from "./store";
import { ChatTranscript } from "./components/ChatTranscript";
import { Composer } from "./components/Composer";
import { DeleteThreadDialog } from "./components/DeleteThreadDialog";
import { RunMetrics } from "./components/RunMetrics";
import { RunProgress } from "./components/RunProgress";
import { ThreadDrawer } from "./components/ThreadDrawer";
import { ThreadList } from "./components/ThreadList";
import styles from "./App.module.css";

const store = new AssistantChatStore();
const token = window.__LIBRENMS_AI_ASSISTANT__?.token || "";
const clientMessageId = () => globalThis.crypto?.randomUUID?.() || `message-${Date.now()}`;
export default function App() {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const [deleteTarget, setDeleteTarget] = useState(null); const controllerRef = useRef(null);
  useEffect(() => { if (!token) return; listThreads(token).then((threads) => store.dispatch({ type: "threads.loaded", threads })).catch(() => {}); }, []);
  const select = async (threadId) => { const thread = await getThread(threadId, token); store.dispatch({ type: "thread.loaded", thread }); };
  const create = async () => { const thread = await createThread(token); store.dispatch({ type: "thread.created", thread }); };
  const send = async (content) => { const threadId = state.selectedThreadId; if (!threadId) return; const id = clientMessageId(); const controller = new AbortController(); controllerRef.current = controller; store.dispatch({ type: "message.optimistic", threadId, clientMessageId: id, content }); try { await runThread(threadId, id, content, token, controller.signal, (event, data) => store.dispatch({ type: "stream.event", threadId, clientMessageId: id, event, data })); } catch (error) { if (error.name === "AbortError") store.dispatch({ type: "stream.event", threadId, event: "completed", data: { run_id: state.runs[threadId]?.id, status: "cancelled", used_fallback: false, metrics: null } }); else { store.dispatch({ type: "stream.event", threadId, event: "error", data: { stage: "transport", code: "transport_failed", retryable: true, message: "The connection ended before the investigation completed." } }); store.dispatch({ type: "stream.event", threadId, event: "completed", data: { run_id: state.runs[threadId]?.id, status: "failed", used_fallback: false, metrics: null } }); } } finally { controllerRef.current = null; } };
  const confirmDelete = async () => { await deleteThread(deleteTarget.id, token); store.dispatch({ type: "thread.deleted", threadId: deleteTarget.id }); setDeleteTarget(null); };
  const selectedMessages = state.selectedThreadId ? state.messages[state.selectedThreadId] || [] : []; const run = state.selectedThreadId ? state.runs[state.selectedThreadId] : null;
  const runtime = useLibreNmsExternalStoreRuntime(store, state.selectedThreadId, send, () => controllerRef.current?.abort());
  return <AssistantRuntimeProvider runtime={runtime}><div className={styles.shell}><a className={styles.skip} href="#investigation-main">Skip saved investigations</a><ThreadDrawer open={state.drawerOpen} onClose={() => store.dispatch({ type: "drawer.close" })} onCreate={create}><ThreadList threads={state.threads} selectedThreadId={state.selectedThreadId} onSelect={select} onDelete={setDeleteTarget} /></ThreadDrawer><main id="investigation-main" className={styles.main}><header className={styles.header}><button type="button" className={styles.menu} onClick={() => store.dispatch({ type: "drawer.open" })} aria-label="Open investigations">☰</button><div><p>Read-only network investigation</p><h1>{state.threads.find((thread) => thread.id === state.selectedThreadId)?.title || "Start an investigation"}</h1></div></header>{run?.error && <p className={styles.error} role="alert">{run.error.message}</p>}<RunProgress run={run} /><ChatTranscript messages={selectedMessages} /><RunMetrics metrics={run?.metrics} /><Composer disabled={!state.selectedThreadId || !token} running={run?.status === "running"} canRetry={run?.canRetry} onSend={send} onCancel={() => controllerRef.current?.abort()} onRetry={() => { const last = [...selectedMessages].reverse().find((message) => message.role === "user"); if (last) send(last.content); }} /></main><DeleteThreadDialog open={Boolean(deleteTarget)} threadTitle={deleteTarget?.title} onCancel={() => setDeleteTarget(null)} onConfirm={confirmDelete} /></div></AssistantRuntimeProvider>;
}

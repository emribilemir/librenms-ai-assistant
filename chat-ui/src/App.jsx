import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import * as apiClient from "./api";
import { useLibreNmsExternalStoreRuntime } from "./runtime";
import { AssistantChatStore } from "./store";
import { readPluginIdentity } from "./identity";
import { verifyDemoInvestigation } from "./demoVerification";
import { AssistantThread } from "./components/AssistantThread";
import { DeleteThreadDialog } from "./components/DeleteThreadDialog";
import { DemoControls } from "./components/DemoControls";
import { ThreadDrawer } from "./components/ThreadDrawer";
import { ThreadList } from "./components/ThreadList";
import styles from "./App.module.css";

const defaultStore = new AssistantChatStore();
const defaultIdentity = readPluginIdentity();
const clientMessageId = () => globalThis.crypto?.randomUUID?.() || `message-${Date.now()}`;
export default function App({ chatStore = defaultStore, identity = defaultIdentity, api = apiClient }) {
  const state = useSyncExternalStore(chatStore.subscribe, chatStore.getSnapshot, chatStore.getSnapshot);
  const [deleteTarget, setDeleteTarget] = useState(null); const [sessionExpired, setSessionExpired] = useState(false); const [suggestions, setSuggestions] = useState([]); const [suggestionsUnavailable, setSuggestionsUnavailable] = useState(false); const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [devices, setDevices] = useState([]); const [devicesUnavailable, setDevicesUnavailable] = useState(false); const [recentDevices, setRecentDevices] = useState([]);
  const [demoMode, setDemoMode] = useState(null); const [demoChanging, setDemoChanging] = useState(false); const [demoScenarios, setDemoScenarios] = useState([]); const [demoTargets, setDemoTargets] = useState([]); const [demoTargetId, setDemoTargetId] = useState(""); const [demoOpen, setDemoOpen] = useState(false); const [demoRunning, setDemoRunning] = useState(""); const [demoResult, setDemoResult] = useState(null); const [demoExpectation, setDemoExpectation] = useState(null); const [demoQuestionRunning, setDemoQuestionRunning] = useState(false); const [demoError, setDemoError] = useState("");
  const [queueContextKey, setQueueContextKey] = useState(0);
  const activeRunsRef = useRef(new Map()); const demoActiveRef = useRef(false); const demoQuestionActiveRef = useRef(false); const deleteTriggerRef = useRef(null); const mainRef = useRef(null); const queueControllerRef = useRef(null); const token = identity?.token || "";
  const devicesLoadedAtRef = useRef(0); const suggestionRotationRef = useRef(0); const suggestionRequestRef = useRef(0);
  const replaceQueueContext = () => { queueControllerRef.current?.clear(); setQueueContextKey((value) => value + 1); };
  const loadDemoMetadata = (metadata) => { const targets = metadata?.supportedTargets || []; setDemoTargets(targets); setDemoScenarios(metadata?.scenarios || []); setDemoTargetId((current) => targets.some((target) => target.id === current) ? current : (targets[0]?.id || "")); };
  const expireSession = (threadId, messageId) => { if (messageId) chatStore.dispatch({ type: "message.discard", threadId, clientMessageId: messageId }); setSessionExpired(true); };
  const refreshThread = async (threadId) => { try { const thread = await api.getThread(threadId, token); if (chatStore.getSnapshot().threads.some((item) => item.id === threadId)) chatStore.dispatch({ type: "thread.loaded", preserveSelection: true, thread }); } catch (error) { if (error.status === 401) expireSession(); } };
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setSuggestions([]);
    setSuggestionsUnavailable(false);
    setDevices([]);
    setDevicesUnavailable(false);
    devicesLoadedAtRef.current = Date.now();
    suggestionRotationRef.current = 0;
    api.listThreads(token).then((threads) => { if (!cancelled) chatStore.dispatch({ type: "threads.loaded", threads }); }).catch((error) => { if (!cancelled && error.status === 401) expireSession(); });
    api.getSuggestions(token).then((items) => { if (!cancelled) setSuggestions(items); }).catch((error) => {
      if (cancelled) return;
      if (error.status === 401) expireSession();
      else setSuggestionsUnavailable(true);
    });
    api.getDevices(token).then((items) => { if (!cancelled) { setDevices(items); devicesLoadedAtRef.current = Date.now(); } }).catch((error) => {
      if (cancelled) return;
      if (error.status === 401) expireSession();
      else setDevicesUnavailable(true);
    });
    api.getDemoMode(token).then((mode) => {
      if (cancelled || mode?.allowed !== true || typeof mode.enabled !== "boolean") return;
      setDemoMode(mode);
      if (mode.enabled) api.getDemoScenarios(token).then((metadata) => { if (!cancelled) loadDemoMetadata(metadata); }).catch((error) => {
        if (!cancelled && error.status === 401) expireSession();
      });
    }).catch((error) => {
      if (!cancelled && error.status === 401) expireSession();
    });
    return () => { cancelled = true; };
  }, [api, chatStore, token]);
  const toggleDemoMode = async () => {
    if (!demoMode || demoChanging) return;
    setDemoChanging(true);
    try {
      const mode = await api.setDemoMode(!demoMode.enabled, token);
      if (mode?.allowed !== true || typeof mode.enabled !== "boolean") return;
      setDemoMode(mode);
      if (mode.enabled) loadDemoMetadata(await api.getDemoScenarios(token));
      else { setDemoScenarios([]); setDemoTargets([]); setDemoTargetId(""); setDemoOpen(false); setDemoResult(null); setDemoExpectation(null); setDemoError(""); }
    } catch (error) {
      if (error.status === 401) expireSession();
    } finally { setDemoChanging(false); }
  };
  const refreshDevices = () => {
    if (!token || Date.now() - devicesLoadedAtRef.current < 30000) return;
    devicesLoadedAtRef.current = Date.now();
    setDevicesUnavailable(false);
    api.getDevices(token).then((items) => { setDevices(items); devicesLoadedAtRef.current = Date.now(); }).catch((error) => {
      if (error.status === 401) expireSession();
      else setDevicesUnavailable(true);
    });
  };
  const rotateSuggestions = () => {
    const rotation = suggestionRotationRef.current + 1;
    suggestionRotationRef.current = rotation;
    const requestId = suggestionRequestRef.current + 1;
    suggestionRequestRef.current = requestId;
    setSuggestionsUnavailable(false);
    api.getSuggestions(token, rotation).then((items) => {
      if (suggestionRequestRef.current === requestId) setSuggestions(items);
    }).catch((error) => {
      if (suggestionRequestRef.current !== requestId) return;
      if (error.status === 401) expireSession();
      else setSuggestionsUnavailable(true);
    });
  };
  const select = async (threadId) => { if (threadId !== chatStore.getSnapshot().selectedThreadId) replaceQueueContext(); try { const thread = await api.getThread(threadId, token); if (chatStore.getSnapshot().threads.some((item) => item.id === threadId)) chatStore.dispatch({ type: "thread.loaded", thread }); } catch (error) { if (error.status === 401) expireSession(); } };
  const isCurrentThreadPristine = () => { const snapshot = chatStore.getSnapshot(); const threadId = snapshot.selectedThreadId; if (!threadId) return false; const thread = snapshot.threads.find((item) => item.id === threadId); const queued = (queueControllerRef.current?.adapter.items.length || 0) + (queueControllerRef.current?.adapter.steerItems.length || 0); return !thread?.title && (snapshot.messages[threadId] || []).length === 0 && snapshot.runs[threadId]?.status !== "running" && queued === 0; };
  const create = async () => { if (isCurrentThreadPristine()) return; replaceQueueContext(); try { const thread = await api.createThread(token); chatStore.dispatch({ type: "thread.created", thread }); rotateSuggestions(); } catch (error) { if (error.status === 401) expireSession(); } };
  const terminalFailure = (threadId, messageId, error) => { const runId = chatStore.getSnapshot().runs[threadId]?.id; if (runId) { chatStore.dispatch({ type: "stream.event", threadId, clientMessageId: messageId, event: "error", data: { run_id: runId, ...error } }); chatStore.dispatch({ type: "stream.event", threadId, clientMessageId: messageId, event: "completed", data: { run_id: runId, status: "failed", used_fallback: false, metrics: null } }); } else chatStore.dispatch({ type: "run.failed", threadId, error }); };
  const send = async (content, expectation = null) => { let threadId = chatStore.getSnapshot().selectedThreadId; if (sessionExpired || !token) return; if (!threadId) { try { const thread = await api.createThread(token); chatStore.dispatch({ type: "thread.created", thread }); threadId = thread.id; } catch (error) { if (error.status === 401) expireSession(); return; } } const id = clientMessageId(); if (expectation) setDemoExpectation({ ...expectation, threadId, clientMessageId: id }); const controller = new AbortController(); chatStore.dispatch({ type: "message.optimistic", threadId, clientMessageId: id, content }); const onEvent = (event, data) => { chatStore.dispatch({ type: "stream.event", threadId, clientMessageId: id, event, data }); if (event === "completed") refreshThread(threadId); }; const promise = api.runThread(threadId, id, content, token, controller.signal, onEvent); const active = { controller, promise }; activeRunsRef.current.set(threadId, active); try { await promise; } catch (error) { if (error.name === "AbortError") { const runId = chatStore.getSnapshot().runs[threadId]?.id; if (runId) chatStore.dispatch({ type: "stream.event", threadId, clientMessageId: id, event: "completed", data: { run_id: runId, status: "cancelled", used_fallback: false, metrics: null } }); } else if (error.status === 401) expireSession(threadId, id); else if (error.status === 409) { chatStore.dispatch({ type: "message.discard", threadId, clientMessageId: id }); terminalFailure(threadId, id, { stage: "transport", code: "run_conflict", retryable: false, message: "This investigation already has a run." }); } else terminalFailure(threadId, id, { stage: "transport", code: "transport_failed", retryable: true, message: "The connection ended before the investigation completed." }); } finally { if (activeRunsRef.current.get(threadId) === active) activeRunsRef.current.delete(threadId); } };
  const closeDelete = () => { setDeleteTarget(null); requestAnimationFrame(() => deleteTriggerRef.current?.focus()); };
  const confirmDelete = async () => { const target = deleteTarget; if (!target) return; if (target.id === chatStore.getSnapshot().selectedThreadId) replaceQueueContext(); const active = activeRunsRef.current.get(target.id); if (active) { active.controller.abort(); await active.promise.catch(() => {}); } try { await api.deleteThread(target.id, token); chatStore.dispatch({ type: "thread.deleted", threadId: target.id }); setDeleteTarget(null); requestAnimationFrame(() => mainRef.current?.focus()); } catch (error) { if (error.status === 401) expireSession(); } };
  const runDemo = async (scenario) => { if (demoActiveRef.current || !demoTargetId) return; demoActiveRef.current = true; setDemoRunning(scenario.id); setDemoResult(null); setDemoExpectation(null); setDemoError(""); try { const result = await api.runDemoScenario(scenario.id, demoTargetId, token); setDemoResult({ ...result, title: scenario.label }); } catch (error) { if (error.status === 401) expireSession(); else setDemoError(error.userMessage || "Senaryo güvenli doğrulama adımında tamamlanamadı. Hedefi sıfırlayıp yeniden dene."); } finally { demoActiveRef.current = false; setDemoRunning(""); } };
  const resetDemo = async () => { if (demoActiveRef.current || !demoTargetId) return; demoActiveRef.current = true; setDemoRunning("reset"); setDemoResult(null); setDemoExpectation(null); setDemoError(""); try { const result = await api.resetDemo(demoTargetId, token); setDemoResult({ ...result, title: "Laboratuvar sıfırlandı" }); } catch (error) { if (error.status === 401) expireSession(); else setDemoError(error.userMessage || "Laboratuvar başlangıç durumuna döndürülemedi. Yeniden dene."); } finally { demoActiveRef.current = false; setDemoRunning(""); } };
  const askDemoQuestion = async (question, expectation) => { if (demoQuestionActiveRef.current || !question) return; demoQuestionActiveRef.current = true; setDemoQuestionRunning(true); try { await send(question, expectation || null); } finally { demoQuestionActiveRef.current = false; setDemoQuestionRunning(false); } };
  const selectedMessages = state.selectedThreadId ? state.messages[state.selectedThreadId] || [] : [];
  const run = state.selectedThreadId ? state.runs[state.selectedThreadId] : null;
  const expectedRun = demoExpectation ? state.runs[demoExpectation.threadId] : null;
  const expectedAnswer = expectedRun && expectedRun.clientMessageId === demoExpectation?.clientMessageId && expectedRun.status === "completed" ? (state.messages[demoExpectation.threadId] || []).find((message) => message.role === "assistant" && message.runId === expectedRun.id) : null;
  const demoVerification = expectedAnswer?.inspection ? verifyDemoInvestigation(demoExpectation, expectedAnswer.inspection) : null;
  const newThreadDisabled = Boolean(state.selectedThreadId) && !state.threads.find((thread) => thread.id === state.selectedThreadId)?.title && selectedMessages.length === 0 && run?.status !== "running";
  const runtime = useLibreNmsExternalStoreRuntime(
    chatStore,
    state.selectedThreadId,
    send,
    () => activeRunsRef.current.get(state.selectedThreadId)?.controller.abort(),
    suggestions,
    { onCreate: create, onSelect: select },
    { contextKey: queueContextKey, controllerRef: queueControllerRef },
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className={styles.shell} data-sidebar-collapsed={sidebarCollapsed || undefined} data-demo-open={demoMode?.enabled && demoOpen && demoScenarios.length ? "true" : undefined}>
        <a className={styles.skip} href="#investigation-main">Sohbet geçmişini atla</a>
        <ThreadDrawer
          open={state.drawerOpen}
          collapsed={sidebarCollapsed}
          onClose={() => chatStore.dispatch({ type: "drawer.close" })}
          onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        >
          <ThreadList threads={state.threads} selectedThreadId={state.selectedThreadId} newThreadDisabled={newThreadDisabled} onSelect={select} onDelete={(thread, trigger) => { deleteTriggerRef.current = trigger; setDeleteTarget(thread); }} />
        </ThreadDrawer>
        <main ref={mainRef} tabIndex="-1" id="investigation-main" className={styles.main}>
          <header className={styles.header}>
            <button type="button" className={styles.menu} onClick={() => chatStore.dispatch({ type: "drawer.open" })} aria-label="Sohbet geçmişini aç">☰</button>
            <div><p>LibreNMS · Salt okunur</p><h1>{state.threads.find((thread) => thread.id === state.selectedThreadId)?.title || "AI Assistant"}</h1></div>
            {demoMode ? <label className={styles.demoMode}>Demo Modu <input type="checkbox" checked={demoMode.enabled} disabled={demoChanging} onChange={toggleDemoMode} /></label> : null}
            <span className={styles.status}>Canlı</span>
          </header>
          {sessionExpired ? <p className={styles.error} role="alert">LibreNMS oturumunun süresi doldu. Devam etmek için sayfayı yenile.</p> : run?.error && <p className={styles.error} role="alert">{run.error.message}</p>}
          <AssistantThread messages={selectedMessages} running={run?.status === "running"} onSend={send} onCancel={() => activeRunsRef.current.get(state.selectedThreadId)?.controller.abort()} canRetry={!sessionExpired && run?.canRetry} onRetry={() => { const last = [...selectedMessages].reverse().find((message) => message.role === "user"); if (last) send(last.content); }} suggestionsUnavailable={suggestionsUnavailable} devices={devices} devicesUnavailable={devicesUnavailable} recentDevices={recentDevices} onDeviceUsed={(hostname) => setRecentDevices((items) => [hostname, ...items.filter((item) => item !== hostname)].slice(0, 4))} onRequestDevices={refreshDevices} showInspection={Boolean(demoMode?.enabled)} />
        </main>
        <DeleteThreadDialog open={Boolean(deleteTarget)} threadTitle={deleteTarget?.title} onCancel={closeDelete} onConfirm={confirmDelete} />
        <DemoControls available={Boolean(demoMode?.enabled && demoScenarios.length)} open={demoOpen} scenarios={demoScenarios} targets={demoTargets} selectedTargetId={demoTargetId} runningScenarioId={demoRunning} result={demoResult} verification={demoVerification} questionRunning={demoQuestionRunning} error={demoError} onOpen={() => setDemoOpen(true)} onClose={() => setDemoOpen(false)} onTargetChange={(targetId) => { setDemoTargetId(targetId); setDemoResult(null); setDemoExpectation(null); setDemoError(""); }} onRun={runDemo} onReset={resetDemo} onAsk={askDemoQuestion} />
      </div>
    </AssistantRuntimeProvider>
  );
}

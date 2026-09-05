import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useExternalStoreRuntime } from "@assistant-ui/react";

const STAGE_COPY = {
  planner: { running: "Soruyu sınıflandırıyor", completed: "Soruyu sınıflandırdı" },
  resolver: { running: "Cihazı çözümlüyor", completed: "Cihazı çözümledi" },
  librenms: { running: "LibreNMS verisini okuyor", completed: "LibreNMS verisini okudu" },
  synthesis: { running: "Doğrulanmış yanıtı hazırlıyor", completed: "Yanıtı doğruladı" },
};

const STAGE_METRIC = {
  planner: "planner_ms",
  resolver: "resolver_ms",
  librenms: "backend_ms",
  synthesis: "synthesis_ms",
};

export function pipelineReasoningText(run) {
  if (!run) return "";
  return Object.entries(STAGE_COPY).flatMap(([stage, copy]) => {
    const persistedDuration = run[STAGE_METRIC[stage]];
    const state = run.stages?.[stage] || (persistedDuration != null ? { status: "completed", durationMs: persistedDuration } : null);
    if (!state) return [];
    const duration = state.status === "completed" && state.durationMs != null ? ` · ${state.durationMs} ms` : "";
    return [`${state.status === "completed" ? copy.completed : copy.running}${duration}`];
  }).join("\n");
}

// The application reducer remains the source of truth; this bridge only exposes
// its message snapshot to assistant-ui's local ExternalStoreRuntime interface.
const METRIC_KEYS = ["planner_ms", "resolver_ms", "backend_ms", "synthesis_ms", "time_to_first_token_ms", "time_to_first_visible_chunk_ms", "total_ms"];

function publicMetrics(run) {
  if (!run) return null;
  if (run.metrics) return run.metrics;
  const metrics = Object.fromEntries(METRIC_KEYS.map((key) => [key, run[key] ?? null]));
  return METRIC_KEYS.some((key) => metrics[key] != null) ? metrics : null;
}

export function useLibreNmsExternalStoreRuntime(store, threadId, onSend, onCancel, suggestions = [], threadActions = {}) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const messages = state.messages[threadId] || [];
  const convertMessage = useCallback((message) => {
    const liveRun = state.runs[threadId];
    const persistedRun = (state.runHistory[threadId] || []).find((run) => run.id === message.runId);
    const run = liveRun?.id === message.runId ? liveRun : persistedRun;
    const reasoning = message.role === "assistant" ? pipelineReasoningText(run) : "";
    const content = [];
    if (reasoning) content.push({ type: "reasoning", text: reasoning });
    if (message.content) content.push({ type: "text", text: message.content });
    return {
      id: message.id,
      role: message.role,
      content,
      createdAt: new Date(),
      metadata: { custom: { usedFallback: Boolean(message.usedFallback), metrics: publicMetrics(run), navigationTargets: message.navigationTargets } },
    };
  }, [state.runs, state.runHistory, threadId]);
  const runtimeStore = useMemo(() => ({
    messages,
    convertMessage,
    suggestions,
    isRunning: state.runs[threadId]?.status === "running",
    onNew: async (message) => onSend(message.content?.[0]?.text || ""),
    onCancel: async () => onCancel(),
    adapters: {
      threadList: {
        threadId: threadId || undefined,
        threads: state.threads.map((thread) => ({
          id: thread.id,
          remoteId: thread.id,
          status: "regular",
          title: thread.title || undefined,
        })),
        onSwitchToNewThread: threadActions.onCreate,
        onSwitchToThread: threadActions.onSelect,
      },
    },
  }), [messages, convertMessage, suggestions, state.runs, state.threads, threadId, onSend, onCancel, threadActions.onCreate, threadActions.onSelect]);
  return useExternalStoreRuntime(runtimeStore);
}

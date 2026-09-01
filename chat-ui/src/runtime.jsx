import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useExternalStoreRuntime } from "@assistant-ui/react";

// The application reducer remains the source of truth; this bridge only exposes
// its message snapshot to assistant-ui's local ExternalStoreRuntime interface.
export function useLibreNmsExternalStoreRuntime(store, threadId, onSend, onCancel) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const messages = state.messages[threadId] || [];
  const convertMessage = useCallback((message) => ({
    id: message.id,
    role: message.role,
    content: [{ type: "text", text: message.content }],
    createdAt: new Date(),
  }), []);
  const runtimeStore = useMemo(() => ({
    messages,
    convertMessage,
    isRunning: state.runs[threadId]?.status === "running",
    onNew: async (message) => onSend(message.content?.[0]?.text || ""),
    onCancel: async () => onCancel(),
  }), [messages, convertMessage, state.runs, threadId, onSend, onCancel]);
  return useExternalStoreRuntime(runtimeStore);
}

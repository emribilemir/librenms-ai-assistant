export function readPluginIdentity(win = globalThis, root = typeof document === "undefined" ? null : document.getElementById("root")) {
  const encoded = root?.dataset?.aiAssistantConfig;
  if (encoded) {
    try { return JSON.parse(encoded); } catch { return {}; }
  }
  return win.__LIBRENMS_AI_ASSISTANT__ || {};
}

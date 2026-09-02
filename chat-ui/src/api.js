export const API_BASE = "/ai-api/v1";
export class ApiError extends Error { constructor(status) { super(`Request failed (${status})`); this.name = "ApiError"; this.status = status; } }
export class IncompleteStreamError extends Error { constructor() { super("The event stream ended before completion."); this.name = "IncompleteStreamError"; } }

function headers(token, json = false) { return { Authorization: `Bearer ${token}`, ...(json ? { "Content-Type": "application/json" } : {}) }; }
async function request(path, token, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers: { ...headers(token, Boolean(options.body)), ...options.headers } });
  if (!response.ok) throw new ApiError(response.status);
  return response;
}
export async function listThreads(token) { return (await request("/threads", token)).json(); }
export async function getSuggestions(token) {
  const payload = await (await request("/suggestions", token)).json();
  return Array.isArray(payload.suggestions) ? payload.suggestions : [];
}
export async function getThread(threadId, token) { return (await request(`/threads/${encodeURIComponent(threadId)}`, token)).json(); }
export async function createThread(token) { return (await request("/threads", token, { method: "POST", body: "{}" })).json(); }
export async function deleteThread(threadId, token) { await request(`/threads/${encodeURIComponent(threadId)}`, token, { method: "DELETE" }); }

export async function readEventStream(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let boundary;
    while ((boundary = buffer.search(/\r?\n\r?\n/)) >= 0) {
      const separator = buffer.match(/\r?\n\r?\n/)[0];
      const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + separator.length);
      const lines = frame.split(/\r?\n/);
      const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const dataLines = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).replace(/^ /, ""));
      if (event && dataLines.length) { onEvent(event, JSON.parse(dataLines.join("\n"))); completed ||= event === "completed"; }
    }
    if (done) { if (!completed) throw new IncompleteStreamError(); return; }
  }
}
export async function runThread(threadId, clientMessageId, content, token, signal, onEvent) {
  const response = await request(`/threads/${encodeURIComponent(threadId)}/runs`, token, { method: "POST", signal, body: JSON.stringify({ client_message_id: clientMessageId, content }) });
  await readEventStream(response, onEvent);
}

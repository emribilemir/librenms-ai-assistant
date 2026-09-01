export const API_BASE = "/ai-api/v1";

function headers(token, json = false) { return { Authorization: `Bearer ${token}`, ...(json ? { "Content-Type": "application/json" } : {}) }; }
async function request(path, token, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers: { ...headers(token, Boolean(options.body)), ...options.headers } });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response;
}
export async function listThreads(token) { return (await request("/threads", token)).json(); }
export async function getThread(threadId, token) { return (await request(`/threads/${encodeURIComponent(threadId)}`, token)).json(); }
export async function createThread(token) { return (await request("/threads", token, { method: "POST", body: "{}" })).json(); }
export async function deleteThread(threadId, token) { await request(`/threads/${encodeURIComponent(threadId)}`, token, { method: "DELETE" }); }

export async function readEventStream(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      const event = frame.match(/^event:\s*(.+)$/m)?.[1];
      const data = frame.match(/^data:\s*(.+)$/m)?.[1];
      if (event && data) onEvent(event, JSON.parse(data));
    }
    if (done) return;
  }
}
export async function runThread(threadId, clientMessageId, content, token, signal, onEvent) {
  const response = await request(`/threads/${encodeURIComponent(threadId)}/runs`, token, { method: "POST", signal, body: JSON.stringify({ client_message_id: clientMessageId, content }) });
  await readEventStream(response, onEvent);
}

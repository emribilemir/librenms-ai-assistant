import { API_BASE, createThread, readEventStream, runThread } from "./api";

test("uses only the relative production API base with no embedded identity", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "thread-a" }) });
  await createThread("signed-plugin-token");
  expect(API_BASE).toBe("/ai-api/v1");
  expect(global.fetch.mock.calls[0][0]).toBe("/ai-api/v1/threads");
  expect(global.fetch.mock.calls[0][0]).not.toMatch(/192\\.168|localhost|dev-auth/);
  expect(global.fetch.mock.calls[0][1].headers.Authorization).toBe("Bearer signed-plugin-token");
});

test("parses fetch SSE events and forwards exact event names", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({ start(controller) { controller.enqueue(encoder.encode("event: planner.started\ndata: {\"run_id\":\"r\",\"stage\":\"planner\"}\n\n")); controller.close(); } });
  const events = [];
  await readEventStream({ body: stream }, (event, data) => events.push([event, data]));
  expect(events).toEqual([["planner.started", { run_id: "r", stage: "planner" }]]);
});

test("passes AbortController signal to the run request", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, body: new ReadableStream({ start(c) { c.close(); } }) });
  const controller = new AbortController();
  await runThread("thread-a", "client-a", "Check edge", "token", controller.signal, () => {});
  expect(global.fetch.mock.calls[0][1].signal).toBe(controller.signal);
});

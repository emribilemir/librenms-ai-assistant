import { API_BASE, ApiError, IncompleteStreamError, createThread, deleteThread, getDemoMode, getDemoScenarios, getDevices, getSuggestions, getThread, listThreads, readEventStream, resetDemo, runDemoScenario, runThread, setDemoMode } from "./api";

test("uses only the relative production API base with no embedded identity", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "thread-a" }) });
  await createThread("signed-plugin-token");
  expect(API_BASE).toBe("/ai-api/v1");
  expect(global.fetch.mock.calls[0][0]).toBe("/ai-api/v1/threads");
  expect(global.fetch.mock.calls[0][0]).not.toMatch(/192\\.168|localhost|dev-auth/);
  expect(global.fetch.mock.calls[0][1].headers.Authorization).toBe("Bearer signed-plugin-token");
});

test("loads authenticated live suggestions for a deterministic rotation", async () => {
  const suggestion = {
    title: "sw-01 durumunu kontrol et",
    label: "Güncel cihaz durumu",
    prompt: "sw-01 cihazının mevcut durumunu göster.",
  };
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ suggestions: [suggestion] }),
  });

  await expect(getSuggestions("signed-plugin-token", 2)).resolves.toEqual([suggestion]);
  expect(global.fetch).toHaveBeenCalledWith(
    "/ai-api/v1/suggestions?rotation=2",
    expect.objectContaining({
      headers: expect.objectContaining({
        Authorization: "Bearer signed-plugin-token",
      }),
    }),
  );
});

test("loads only the bounded live device picker payload", async () => {
  const devices = [
    { hostname: "lab-up", status: "up", examples: ["lab-up açık mı?"] },
    { hostname: "core-down", status: "down", examples: [] },
  ];
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ devices }),
  });

  await expect(getDevices("signed-plugin-token")).resolves.toEqual(devices);
  expect(global.fetch).toHaveBeenCalledWith(
    "/ai-api/v1/devices",
    expect.objectContaining({
      headers: expect.objectContaining({
        Authorization: "Bearer signed-plugin-token",
      }),
    }),
  );
});

test("demo requests send only the bounded scenario and target ids", async () => {
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ supported_targets: [{ id: "lab-01" }], scenarios: [{ id: "port-down" }] }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ scenario_id: "port-down" }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ scenario_id: "reset" }) });

  await expect(getDemoScenarios("token")).resolves.toEqual({
    supportedTargets: [{ id: "lab-01" }],
    scenarios: [{ id: "port-down" }],
  });
  await runDemoScenario("port-down", "lab-01", "token");
  await resetDemo("lab-01", "token");

  expect(global.fetch.mock.calls[1]).toEqual([
    "/ai-api/v1/demo/scenarios",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ scenario_id: "port-down", target_id: "lab-01" }) }),
  ]);
  expect(global.fetch.mock.calls[2]).toEqual([
    "/ai-api/v1/demo/reset",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ target_id: "lab-01" }) }),
  ]);
});

test("demo mode state reads and writes only its bounded boolean", async () => {
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ allowed: true, enabled: false }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ allowed: true, enabled: true }) });

  await expect(getDemoMode("token")).resolves.toEqual({ allowed: true, enabled: false });
  await expect(setDemoMode(true, "token")).resolves.toEqual({ allowed: true, enabled: true });
  expect(global.fetch.mock.calls[1]).toEqual([
    "/ai-api/v1/demo-mode",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ enabled: true }) }),
  ]);
});

test("parses fetch SSE events and forwards exact event names", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({ start(controller) { controller.enqueue(encoder.encode("event: planner.started\ndata: {\"run_id\":\"r\",\"stage\":\"planner\"}\n\nevent: completed\ndata: {\"run_id\":\"r\",\"status\":\"completed\"}\n\n")); controller.close(); } });
  const events = [];
  await readEventStream({ body: stream }, (event, data) => events.push([event, data]));
  expect(events).toEqual([["planner.started", { run_id: "r", stage: "planner" }], ["completed", { run_id: "r", status: "completed" }]]);
});

test("passes AbortController signal to the run request", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode("event: completed\ndata: {\"run_id\":\"r\",\"status\":\"cancelled\"}\n\n")); c.close(); } }) });
  const controller = new AbortController();
  await runThread("thread-a", "client-a", "Check edge", "token", controller.signal, () => {});
  expect(global.fetch.mock.calls[0][1].signal).toBe(controller.signal);
});

test("parses CRLF-delimited, split, multi-line SSE data frames", async () => {
  const encoder = new TextEncoder();
  const chunks = ["event: answer.delta\r\ndata: {\"run_id\":\"r\",", "\r\ndata: \"message_id\":\"m\",\"delta\":\"safe\"}\r\n\r", "\n", "event: completed\r\ndata: {\"run_id\":\"r\",\"status\":\"completed\"}\r\n\r\n"];
  const stream = new ReadableStream({ start(controller) { chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk))); controller.close(); } });
  const events = [];
  await readEventStream({ body: stream }, (event, data) => events.push([event, data]));
  expect(events).toEqual([["answer.delta", { run_id: "r", message_id: "m", delta: "safe" }], ["completed", { run_id: "r", status: "completed" }]]);
});

test("gives each validated answer delta a paint frame before processing completion", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({ start(controller) {
    controller.enqueue(encoder.encode("event: answer.delta\ndata: {\"run_id\":\"r\",\"message_id\":\"m\",\"delta\":\"Visible answer\"}\n\nevent: completed\ndata: {\"run_id\":\"r\",\"status\":\"completed\"}\n\n"));
    controller.close();
  } });
  const events = [];
  const originalAnimationFrame = global.requestAnimationFrame;
  let releaseFrame;
  global.requestAnimationFrame = jest.fn((callback) => { releaseFrame = callback; return 1; });

  try {
    const reading = readEventStream({ body: stream }, (event, data) => events.push([event, data]));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(events.map(([event]) => event)).toEqual(["answer.delta"]);
    expect(releaseFrame).toEqual(expect.any(Function));
    releaseFrame();
    await reading;
    expect(events.map(([event]) => event)).toEqual(["answer.delta", "completed"]);
  } finally {
    global.requestAnimationFrame = originalAnimationFrame;
  }
});

test("rejects an SSE response that ends before a completed event", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({ start(controller) { controller.enqueue(encoder.encode("event: run.started\ndata: {\"run_id\":\"r\"}\n\n")); controller.close(); } });
  await expect(readEventStream({ body: stream }, () => {})).rejects.toBeInstanceOf(IncompleteStreamError);
});

test("preserves typed 401 and 409 API errors for central UI handling", async () => {
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockResolvedValueOnce({ ok: false, status: 409 });
  await expect(listThreads("token")).rejects.toMatchObject({ status: 401 });
  await expect(createThread("token")).rejects.toBeInstanceOf(ApiError);
  await expect(getThread("a", "token")).rejects.toMatchObject({ status: 401 });
  await expect(deleteThread("a", "token")).rejects.toMatchObject({ status: 401 });
  await expect(runThread("a", "client", "content", "token", undefined, () => {})).rejects.toMatchObject({ status: 409 });
});

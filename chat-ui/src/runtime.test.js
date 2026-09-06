import { createLibreNmsMessageQueue, pipelineReasoningText } from "./runtime";

const appendMessage = (text) => ({
  role: "user",
  content: [{ type: "text", text }],
  attachments: [],
  createdAt: new Date(),
  parentId: null,
  sourceId: null,
  metadata: { custom: {} },
});

const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

test("reconstructs completed investigation steps from persisted public timing metrics", () => {
  expect(pipelineReasoningText({
    status: "completed",
    planner_ms: 7,
    resolver_ms: 11,
    backend_ms: 13,
    synthesis_ms: null,
  })).toBe("Soruyu sınıflandırdı · 7 ms\nCihazı çözümledi · 11 ms\nLibreNMS verisini okudu · 13 ms");
});

test("native message queue drains follow-ups exactly once in FIFO order", async () => {
  const runs = [deferred(), deferred(), deferred()];
  const started = [];
  const queue = createLibreNmsMessageQueue((text) => {
    started.push(text);
    return runs[started.length - 1].promise;
  });

  queue.adapter.enqueue(appendMessage("Soru A"));
  queue.adapter.enqueue(appendMessage("Soru B"));
  queue.adapter.enqueue(appendMessage("Soru C"));
  expect(started).toEqual(["Soru A"]);

  runs[0].resolve();
  await runs[0].promise;
  await Promise.resolve();
  expect(started).toEqual(["Soru A", "Soru B"]);

  runs[1].resolve();
  await runs[1].promise;
  await Promise.resolve();
  expect(started).toEqual(["Soru A", "Soru B", "Soru C"]);

  runs[2].resolve();
  await runs[2].promise;
  await Promise.resolve();
  expect(started).toEqual(["Soru A", "Soru B", "Soru C"]);
});

test("removing a native queued item prevents it from running", async () => {
  const first = deferred();
  const started = [];
  const queue = createLibreNmsMessageQueue((text) => {
    started.push(text);
    return first.promise;
  });

  queue.adapter.enqueue(appendMessage("Soru A"));
  queue.adapter.enqueue(appendMessage("Silinecek soru"));
  queue.adapter.remove(queue.adapter.items[0].id);
  first.resolve();
  await first.promise;
  await Promise.resolve();

  expect(started).toEqual(["Soru A"]);
});

test("explicit stop preserves queued follow-ups and pauses drain", async () => {
  const first = deferred();
  const started = [];
  const queue = createLibreNmsMessageQueue((text) => {
    started.push(text);
    return first.promise;
  });

  queue.adapter.enqueue(appendMessage("Çalışan soru"));
  queue.adapter.steer(appendMessage("Bekleyen soru"));
  queue.notifyCancelled();
  first.resolve();
  await first.promise;
  await Promise.resolve();

  expect(started).toEqual(["Çalışan soru"]);
  expect(queue.adapter.steerItems.map((item) => item.prompt)).toEqual(["Bekleyen soru"]);
});

test("clearing a conversation queue prevents stale drain after its run settles", async () => {
  const first = deferred();
  const started = [];
  const queue = createLibreNmsMessageQueue((text) => {
    started.push(text);
    return first.promise;
  });

  queue.adapter.enqueue(appendMessage("Eski çalışan soru"));
  queue.adapter.enqueue(appendMessage("Eski bekleyen soru"));
  queue.clear();
  first.resolve();
  await first.promise;
  await Promise.resolve();

  expect(started).toEqual(["Eski çalışan soru"]);
  expect(queue.adapter.items).toHaveLength(0);
  expect(queue.adapter.steerItems).toHaveLength(0);
});

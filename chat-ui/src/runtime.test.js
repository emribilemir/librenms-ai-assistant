import { pipelineReasoningText } from "./runtime";

test("reconstructs completed investigation steps from persisted public timing metrics", () => {
  expect(pipelineReasoningText({
    status: "completed",
    planner_ms: 7,
    resolver_ms: 11,
    backend_ms: 13,
    synthesis_ms: null,
  })).toBe("Soruyu sınıflandırdı · 7 ms\nCihazı çözümledi · 11 ms\nLibreNMS verisini okudu · 13 ms");
});

import fs from "node:fs";
import path from "node:path";

const suite = fs.readFileSync(path.resolve(__dirname, "../e2e/utm.spec.js"), "utf8");

test("authorized UTM suite retains explicit live-progress, metric, and retry-order parity", () => {
  expect(suite).toContain("AI_UTM_LIVE_PROGRESS_QUERY");
  expect(suite).toContain('aria-live", "polite"');
  expect(suite).toContain("persistedRunFor");
  expect(suite).toContain("assertCoherentMetrics");
  expect(suite).toContain("planner completed");
  expect(suite).toContain("resolver completed");
  expect(suite).toContain("librenms running");
  expect(suite).not.toContain("AI_UTM_RETRY_STAGE_GATE");
  expect(suite).toContain("live target must be configured to expose this sequence");
});

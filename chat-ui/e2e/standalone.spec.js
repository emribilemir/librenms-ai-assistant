import { expect, test } from "@playwright/test";

const metrics = [
  "planner_ms",
  "resolver_ms",
  "backend_ms",
  "synthesis_ms",
  "time_to_first_token_ms",
  "time_to_first_visible_chunk_ms",
  "total_ms",
];

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__LIBRENMS_AI_ASSISTANT__ = { token: "standalone-development" };
  });
  const initialThreadList = page.waitForResponse((response) =>
    response.url().endsWith("/ai-api/v1/threads") && response.request().method() === "GET",
  );
  await page.goto("/");
  expect((await initialThreadList).status()).toBe(200);
});

async function createThread(page) {
  await page.getByRole("button", { name: "New investigation" }).click();
  const item = page.getByRole("navigation", { name: "Saved investigations" }).getByRole("button", { name: "Untitled investigation" }).first();
  await expect(item).toBeVisible();
  return item;
}

async function ask(page, question) {
  await page.getByLabel("Ask LibreNMS").fill(question);
  await page.getByRole("button", { name: "Soruyu gönder" }).click();
}

async function persistedRunFor(page, title) {
  return page.evaluate(async ({ threadTitle }) => {
    const token = window.__LIBRENMS_AI_ASSISTANT__?.token;
    const threads = await (await fetch("/ai-api/v1/threads", { headers: { Authorization: `Bearer ${token}` } })).json();
    const thread = threads.find((candidate) => candidate.title === threadTitle);
    if (!thread) throw new Error(`Missing persisted thread: ${threadTitle}`);
    const detail = await (await fetch(`/ai-api/v1/threads/${thread.id}`, { headers: { Authorization: `Bearer ${token}` } })).json();
    return detail.runs.at(-1);
  }, { threadTitle: title });
}

test("sends the first assistant-ui message without pre-creating a thread", async ({ page }) => {
  const composer = page.getByLabel("Ask LibreNMS");
  await expect(composer).toBeEnabled();
  await ask(page, "first direct question");
  await expect(page.getByText("Deterministic standalone result.")).toBeVisible();
  await expect(page.locator("[data-message-id]")).toHaveCount(2);
  await expect(page.getByRole("navigation", { name: "Saved investigations" }).getByRole("button", { name: "first direct question", exact: true })).toBeVisible();
});

test("builds assistant-ui starter prompts from currently up devices", async ({ page }) => {
  const liveSuggestion = page.getByRole("button", { name: /lab-j9775a-01 durumunu kontrol et/i });
  await expect(liveSuggestion).toBeVisible();
  await liveSuggestion.click();
  await expect(page.getByText("lab-j9775a-01 cihazının mevcut durumunu göster.")).toBeVisible();
  await expect(page.getByText("Deterministic standalone result.")).toBeVisible();
  await expect(page.getByRole("button", { name: /lab-offline-01/i })).toHaveCount(0);
});

test("creates, selects, and deletes a saved thread only after confirmation", async ({ page }) => {
  await createThread(page);
  await ask(page, "ambiguous core uplink");
  await expect(page.getByText("Several matching devices need clarification.")).toBeVisible();
  const titledFirst = page.getByRole("navigation", { name: "Saved investigations" }).getByRole("button", { name: "ambiguous core uplink", exact: true });
  await expect(titledFirst).toBeVisible();

  await createThread(page);
  const saved = page.getByRole("navigation", { name: "Saved investigations" });
  await expect(saved.getByRole("button", { name: "Untitled investigation" })).toBeVisible();
  await titledFirst.click();
  await expect(page.getByRole("heading", { name: "ambiguous core uplink" })).toBeVisible();
  await expect(page.getByText("Several matching devices need clarification.")).toBeVisible();

  const remove = page.getByRole("button", { name: "Delete ambiguous core uplink" });
  await remove.click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Keep thread" })).toBeFocused();
  await dialog.getByRole("button", { name: "Keep thread" }).click();
  await expect(dialog).toBeHidden();
  await expect(remove).toBeFocused();
  await expect(titledFirst).toBeVisible();

  await remove.click();
  await dialog.getByRole("button", { name: "Delete investigation" }).click();
  await expect(page.getByRole("button", { name: "Delete ambiguous core uplink" })).toHaveCount(0);
});

test("renders only real received stage progress for a successful no-match result", async ({ page }) => {
  await createThread(page);
  await ask(page, "no-match branch switch");
  const progress = page.getByRole("region", { name: "Pipeline progress" });
  const live = progress.locator("p[aria-live='polite']");
  await expect(live).toContainText(/Soruyu sınıflandır/);
  await expect(live).toContainText(/Cihazı çözüml/);
  await expect(page.getByText("No monitored device matches that name.")).toBeVisible();
  await expect(page.locator('[data-assistant-ui="thread"]')).toBeVisible();
  await expect(page.locator("[data-message-id]")).toHaveCount(2);
  await expect(progress).toHaveCount(0);
  await expect(page.getByText("No monitored device matches that name.")).toBeVisible();
});

test("shows a retryable backend failure and allows a real retried stream to succeed", async ({ page }) => {
  await page.getByRole("button", { name: "New investigation" }).click();
  await ask(page, "retryable backend question");
  const progress = page.getByRole("region", { name: "Pipeline progress" });
  await expect(progress.locator("p[aria-live='polite']")).toContainText(/Soruyu sınıflandırdı.*Cihazı çözümledi.*LibreNMS verisini okuyor/);
  expect(await page.evaluate(async () => (await fetch("/ai-api/__test__/release-retryable-failure", { method: "POST" })).status)).toBe(204);
  await expect(page.getByRole("alert")).toHaveText("LibreNMS is temporarily unavailable.");
  const retry = page.getByRole("button", { name: "Retry failed investigation" });
  await expect(retry).toBeVisible();
  await retry.click();
  await expect(page.getByText("Backend recovered on retry.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry failed investigation" })).toHaveCount(0);
});

test("labels a validated fallback answer and exposes its complete metric disclosure", async ({ page }, testInfo) => {
  await createThread(page);
  await ask(page, "fallback investigation evidence");
  await expect(page.getByText("Safe evidence fallback summary.")).toBeVisible();
  await expect(page.getByText("Validated fallback result")).toBeVisible();
  const disclosure = page.getByRole("button", { name: /System vitals/ });
  await expect(disclosure).toHaveAttribute("aria-expanded", "false");
  await disclosure.click();
  await expect(disclosure).toHaveAttribute("aria-expanded", "true");
  for (const metric of metrics) await expect(page.getByText(metric, { exact: true })).toBeVisible();
  for (const value of ["7 ms", "11 ms", "13 ms", "17 ms", "48 ms"]) await expect(page.getByText(value, { exact: true })).toBeVisible();
  const persistedRun = await persistedRunFor(page, "fallback investigation evidence");
  expect(persistedRun).toMatchObject({ planner_ms: 7, resolver_ms: 11, backend_ms: 13, synthesis_ms: 17, total_ms: 48 });
  expect(persistedRun.total_ms).toBe(persistedRun.planner_ms + persistedRun.resolver_ms + persistedRun.backend_ms + persistedRun.synthesis_ms);
  await page.screenshot({ path: testInfo.outputPath("fallback-metrics.png"), fullPage: true });
});

test("cancelling a real stream prevents later stages and answer output", async ({ page }, testInfo) => {
  await page.getByRole("button", { name: "New investigation" }).click();
  await ask(page, "cancel after planner");
  const progress = page.getByRole("region", { name: "Pipeline progress" });
  await expect(progress.locator("p[aria-live='polite']")).toContainText(/Soruyu sınıflandırdı/);
  await page.getByRole("button", { name: "Çalışmayı iptal et" }).click();
  await expect(progress).toHaveCount(0);
  await expect(page.getByText("This answer must never be visible.")).toHaveCount(0);
  await expect(page.getByText("resolver", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("cancelled-run.png"), fullPage: true });
});

test("supports keyboard focus, live stage announcements, and the responsive drawer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "Open investigations" })).toBeVisible();
  await expect(page.getByLabel("Investigations", { exact: true })).toHaveAttribute("aria-hidden", "true");
  await page.getByRole("button", { name: "Open investigations" }).press("Enter");
  await expect(page.getByRole("button", { name: "New investigation" })).toBeVisible();
  await page.getByRole("button", { name: "New investigation" }).click();
  const composer = page.getByLabel("Ask LibreNMS");
  await composer.click();
  await expect(composer).toBeFocused();
  await ask(page, "ambiguous keyboard check");
  const live = page.getByRole("region", { name: "Pipeline progress" }).locator("p[aria-live='polite']");
  await expect(live).toHaveAttribute("aria-live", "polite");
});

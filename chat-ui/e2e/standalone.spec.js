import { expect, test } from "@playwright/test";

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
  const created = page.waitForResponse((response) =>
    response.url().endsWith("/ai-api/v1/threads") && response.request().method() === "POST",
  );
  await page.locator('[data-slot="aui_thread-list-new"]').click();
  expect((await created).status()).toBe(201);
  const item = page.getByRole("navigation", { name: "Kayıtlı sohbetler" }).getByRole("button", { name: "Yeni sohbet", exact: true }).first();
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
  await expect(page.getByRole("navigation", { name: "Kayıtlı sohbetler" }).getByRole("button", { name: "first direct question", exact: true })).toBeVisible();
});

test("builds assistant-ui starter prompts from currently up devices", async ({ page }) => {
  const liveSuggestion = page.getByRole("button", { name: /lab-j9775a-01 durumunu kontrol et/i });
  await expect(liveSuggestion).toBeVisible();
  await liveSuggestion.click();
  await expect(page.getByText("lab-j9775a-01 cihazının mevcut durumunu göster.")).toBeVisible();
  await expect(page.getByText("Deterministic standalone result.")).toBeVisible();
  await expect(page.getByRole("button", { name: /lab-offline-01/i })).toHaveCount(0);
});

test("fills the available conversation height without clipping starter prompts", async ({ page }) => {
  const [threadBox, mainBox] = await Promise.all([
    page.locator('[data-assistant-ui="thread"]').boundingBox(),
    page.locator("#investigation-main").boundingBox(),
  ]);
  expect(Math.abs((threadBox.y + threadBox.height) - (mainBox.y + mainBox.height))).toBeLessThanOrEqual(1);
  const suggestions = page.getByLabel("Canlı cihaz önerileri");
  await expect(suggestions).toBeInViewport();
  const suggestionBox = await suggestions.boundingBox();
  expect(suggestionBox.y + suggestionBox.height).toBeLessThanOrEqual(threadBox.y + threadBox.height);
});

test("collapses the assistant-ui history rail without taking space from the conversation", async ({ page }) => {
  const drawer = page.getByLabel("Sohbet geçmişi", { exact: true });
  await expect(drawer).toHaveCSS("width", "272px");
  await page.getByRole("button", { name: "Sohbet geçmişini daralt" }).click();
  await expect(drawer).toHaveCSS("width", "56px");
  await expect(page.locator('[data-slot="aui_thread-list-new"]')).toBeVisible();
  await page.getByRole("button", { name: "Sohbet geçmişini genişlet" }).click();
  await expect(drawer).toHaveCSS("width", "272px");
});

test("reveals validated answer chunks progressively and keeps long conversations scrollable", async ({ page }) => {
  await createThread(page);
  await page.evaluate(() => {
    window.__answerSnapshots = [];
    const observer = new MutationObserver(() => {
      const answers = document.querySelectorAll('[data-slot="assistant-answer"]');
      const text = answers[answers.length - 1]?.textContent?.trim() || "";
      if (text && window.__answerSnapshots.at(-1) !== text) window.__answerSnapshots.push(text);
    });
    observer.observe(document.querySelector("#root"), { childList: true, characterData: true, subtree: true });
    window.__answerObserver = observer;
  });
  await ask(page, "streaming cadence and scroll");
  await expect(page.getByText(/Port grubu 24:/)).toBeVisible();
  const snapshots = await page.evaluate(() => {
    window.__answerObserver?.disconnect();
    return window.__answerSnapshots || [];
  });
  expect(new Set(snapshots.map((text) => text.length)).size).toBeGreaterThan(2);
  const viewport = page.locator('[data-slot="thread-viewport"]');
  const dimensions = await viewport.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    overflowY: getComputedStyle(element).overflowY,
  }));
  expect(dimensions.overflowY).toBe("auto");
  expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.clientHeight);
  await viewport.evaluate((element) => { element.scrollTop = 0; });
  await expect(page.getByRole("button", { name: "En yeni mesaja git" })).toBeVisible();
});

test("creates, selects, and deletes a saved thread only after confirmation", async ({ page }) => {
  await createThread(page);
  await ask(page, "ambiguous core uplink");
  await expect(page.getByText("Several matching devices need clarification.")).toBeVisible();
  const titledFirst = page.getByRole("navigation", { name: "Kayıtlı sohbetler" }).getByRole("button", { name: "ambiguous core uplink", exact: true });
  await expect(titledFirst).toBeVisible();

  await createThread(page);
  const saved = page.getByRole("navigation", { name: "Kayıtlı sohbetler" });
  await expect(saved.getByRole("button", { name: "Yeni sohbet", exact: true }).first()).toBeVisible();
  await titledFirst.click();
  await expect(page.getByRole("heading", { name: "ambiguous core uplink" })).toBeVisible();
  await expect(page.getByText("Several matching devices need clarification.")).toBeVisible();

  const remove = page.getByRole("button", { name: "ambiguous core uplink için seçenekler" });
  await remove.click();
  await page.getByRole("menuitem", { name: "Sohbeti sil" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveCSS("background-color", "rgb(43, 48, 53)");
  await expect(dialog).toHaveCSS("color", "rgb(237, 240, 242)");
  await expect(dialog.getByRole("button", { name: "Sohbeti tut" })).toBeFocused();
  await dialog.getByRole("button", { name: "Sohbeti tut" }).click();
  await expect(dialog).toBeHidden();
  await expect(remove).toBeFocused();
  await expect(titledFirst).toBeVisible();

  await remove.click();
  await page.getByRole("menuitem", { name: "Sohbeti sil" }).click();
  await dialog.getByRole("button", { name: "Sohbeti sil" }).click();
  await expect(page.getByRole("button", { name: "ambiguous core uplink için seçenekler" })).toHaveCount(0);
});

test("renders only real received stage progress for a successful no-match result", async ({ page }) => {
  await createThread(page);
  await ask(page, "no-match branch switch");
  const reasoning = page.locator("[data-streaming] button[aria-expanded]");
  const live = page.locator("[aria-live='polite']").last();
  await expect(reasoning).toHaveAttribute("aria-expanded", "true");
  await expect(live).toContainText(/Soruyu sınıflandır/);
  await expect(live).toContainText(/Cihazı çözüml/);
  await expect(page.getByText("No monitored device matches that name.")).toBeVisible();
  await expect(page.locator('[data-assistant-ui="thread"]')).toBeVisible();
  await expect(page.locator("[data-message-id]")).toHaveCount(2);
  await expect(page.getByRole("button", { name: /İşlem ayrıntıları/i })).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByText("No monitored device matches that name.")).toBeVisible();
});

test("shows a retryable backend failure and allows a real retried stream to succeed", async ({ page }) => {
  await createThread(page);
  await ask(page, "retryable backend question");
  const live = page.locator("[aria-live='polite']").last();
  await expect(live).toContainText(/Soruyu sınıflandırdı.*Cihazı çözümledi.*LibreNMS verisini okuyor/);
  expect(await page.evaluate(async () => (await fetch("/ai-api/__test__/release-retryable-failure", { method: "POST" })).status)).toBe(204);
  await expect(page.getByRole("alert")).toHaveText("LibreNMS is temporarily unavailable.");
  const retry = page.getByRole("button", { name: "Yeniden dene" });
  await expect(retry).toBeVisible();
  await retry.click();
  await expect(page.getByText("Backend recovered on retry.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Yeniden dene" })).toHaveCount(0);
});

test("labels a validated fallback answer and keeps telemetry in its single process disclosure", async ({ page }, testInfo) => {
  await createThread(page);
  await ask(page, "fallback investigation evidence");
  await expect(page.getByText("Safe evidence fallback summary.")).toBeVisible();
  await expect(page.getByText("Doğrulanmış güvenli yanıt")).toBeVisible();
  const disclosure = page.getByRole("button", { name: /İşlem ayrıntıları/ });
  await expect(disclosure).toHaveAttribute("aria-expanded", "false");
  await disclosure.click();
  await expect(disclosure).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("Soruyu sınıflandırdı · 7 ms", { exact: true })).toBeVisible();
  await expect(page.getByText("Cihazı çözümledi · 11 ms", { exact: true })).toBeVisible();
  await expect(page.getByText("LibreNMS verisini okudu · 13 ms", { exact: true })).toBeVisible();
  await expect(page.getByText("Yanıtı doğruladı · 17 ms", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Yanıt aktarım süreleri")).toBeVisible();
  await expect(page.getByText(/Ekrana aktarım/)).toBeVisible();
  await expect(page.getByText("Çalışma ayrıntıları")).toHaveCount(0);
  const persistedRun = await persistedRunFor(page, "fallback investigation evidence");
  expect(persistedRun).toMatchObject({ planner_ms: 7, resolver_ms: 11, backend_ms: 13, synthesis_ms: 17 });
  expect(persistedRun.total_ms).toBeGreaterThanOrEqual(48);
  expect(persistedRun.total_ms).toBeGreaterThanOrEqual(persistedRun.time_to_first_visible_chunk_ms);
  await expect(disclosure).toContainText(`${persistedRun.total_ms} ms`);
  await page.screenshot({ path: testInfo.outputPath("fallback-metrics.png"), fullPage: true });
});

test("cancelling a real stream prevents later stages and answer output", async ({ page }, testInfo) => {
  await createThread(page);
  await ask(page, "cancel after planner");
  const live = page.locator("[aria-live='polite']").last();
  await expect(live).toContainText(/Soruyu sınıflandırdı/);
  await page.getByRole("button", { name: "Çalışmayı iptal et" }).click();
  await expect(page.getByRole("button", { name: /İşlem ayrıntıları/i })).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByText("This answer must never be visible.")).toHaveCount(0);
  await expect(page.getByText("resolver", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("cancelled-run.png"), fullPage: true });
});

test("supports keyboard focus, live stage announcements, and the responsive drawer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "Sohbet geçmişini aç" })).toBeVisible();
  await expect(page.getByLabel("Sohbet geçmişi", { exact: true })).toHaveAttribute("aria-hidden", "true");
  await page.getByRole("button", { name: "Sohbet geçmişini aç" }).press("Enter");
  await expect(page.locator('[data-slot="aui_thread-list-new"]')).toBeVisible();
  await createThread(page);
  const composer = page.getByLabel("Ask LibreNMS");
  await composer.click();
  await expect(composer).toBeFocused();
  await ask(page, "ambiguous keyboard check");
  const live = page.locator("[aria-live='polite']").last();
  await expect(live).toHaveAttribute("aria-live", "polite");
});

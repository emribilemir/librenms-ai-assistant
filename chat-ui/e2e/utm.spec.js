import fs from "node:fs";
import { expect, test } from "@playwright/test";

// This suite has no remote default. An operator supplies an authorized target,
// two isolated signed-in browser states, and curated read-only test queries.
const pluginRoute = "/plugin/AiAssistant";
const baseRequirements = () => [
  ...(process.env.AI_UTM_AUTHORIZED === "1" ? [] : ["AI_UTM_AUTHORIZED=1"]),
  ...(process.env.AI_UTM_BASE_URL ? [] : ["AI_UTM_BASE_URL"]),
];

function missingStorage(name) {
  const state = process.env[name];
  return !state ? [name] : fs.existsSync(state) ? [] : [`${name} (readable local storage-state file)`];
}

function missing(...requirements) {
  return [...baseRequirements(), ...requirements.flatMap((name) => name.endsWith("_STORAGE_STATE") ? missingStorage(name) : process.env[name] ? [] : [name])];
}

function skipWithout(testInfo, ...requirements) {
  const absent = missing(...requirements);
  testInfo.skip(absent.length > 0, `Authorized UTM acceptance is inert; missing explicit prerequisites: ${absent.join(", ")}.`);
}

async function signedPluginPage(browser, storageState) {
  const context = await browser.newContext({ storageState });
  const page = await context.newPage();
  await page.goto(pluginRoute);
  const root = page.locator("#root");
  await expect(root).toHaveAttribute("data-ai-assistant-config", /.+/);
  const identity = await root.evaluate((element) => {
    const config = JSON.parse(element.dataset.aiAssistantConfig || "{}");
    const [, encodedPayload] = String(config.token || "").split(".");
    const base64 = encodedPayload.replace(/-/g, "+").replace(/_/g, "/");
    const payload = encodedPayload ? JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="))) : {};
    return { apiBase: config.apiBase, tokenVersion: String(config.token || "").split(".")[0], payload };
  });
  expect(identity.tokenVersion).toBe("v1");
  expect(identity.apiBase).toBe("/ai-api/v1");
  expect(identity.payload).toMatchObject({ iss: "librenms", aud: "ai-assistant" });
  expect(identity.payload.sub).toEqual(expect.any(String));
  await expect(page.getByRole("main")).toBeVisible();
  return { context, page, subject: identity.payload.sub };
}

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

async function persistedRunFor(page, threadTitle) {
  return page.evaluate(async (title) => {
    const config = JSON.parse(document.querySelector("#root")?.dataset.aiAssistantConfig || "{}");
    const headers = { Authorization: `Bearer ${config.token}` };
    const threads = await (await fetch("/ai-api/v1/threads", { headers })).json();
    const thread = threads.find((candidate) => candidate.title === title);
    if (!thread) throw new Error(`Missing persisted UTM test thread: ${title}`);
    const detail = await (await fetch(`/ai-api/v1/threads/${thread.id}`, { headers })).json();
    return detail.runs.at(-1);
  }, threadTitle);
}

function assertCoherentMetrics(run) {
  const names = ["planner_ms", "resolver_ms", "backend_ms", "synthesis_ms", "time_to_first_token_ms", "time_to_first_visible_chunk_ms"];
  for (const name of names) {
    expect(run).toHaveProperty(name);
    if (run[name] !== null) {
      expect(typeof run[name]).toBe("number");
      expect(Number.isFinite(run[name])).toBe(true);
      expect(run[name]).toBeGreaterThanOrEqual(0);
    }
  }
  expect(typeof run.total_ms).toBe("number");
  expect(Number.isFinite(run.total_ms)).toBe(true);
  expect(run.total_ms).toBeGreaterThanOrEqual(0);
  const nonBackendComponentTotal = [run.planner_ms, run.resolver_ms, run.synthesis_ms]
    .filter((value) => typeof value === "number")
    .reduce((sum, value) => sum + value, 0);
  // backend_ms measures the adapter/backend call itself and may overlap other
  // wall-clock work, so it must fit within total but is not blindly added.
  expect(run.total_ms).toBeGreaterThanOrEqual(nonBackendComponentTotal);
  if (typeof run.backend_ms === "number") expect(run.total_ms).toBeGreaterThanOrEqual(run.backend_ms);
}

test.describe("authorized UTM acceptance", () => {
  test("shows live-device assistant-ui suggestions from the signed backend", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE");
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      const suggestions = await page.evaluate(async () => {
        const config = JSON.parse(document.querySelector("#root")?.dataset.aiAssistantConfig || "{}");
        const response = await fetch("/ai-api/v1/suggestions", {
          headers: { Authorization: `Bearer ${config.token}` },
        });
        if (!response.ok) throw new Error(`Suggestion request failed: ${response.status}`);
        return (await response.json()).suggestions;
      });
      expect(suggestions.length).toBeGreaterThan(0);
      const first = suggestions[0];
      const trigger = page.getByRole("button", { name: new RegExp(first.title, "i") });
      await expect(trigger).toBeVisible();
      await trigger.click();
      await expect(page.getByText(first.prompt, { exact: true })).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("loads the signed plugin route and keeps the responsive drawer keyboard-accessible", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE");
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await page.setViewportSize({ width: 390, height: 844 });
      await expect(page.getByRole("button", { name: "Sohbet geçmişini aç" })).toBeVisible();
      await expect(page.getByLabel("Sohbet geçmişi", { exact: true })).toHaveAttribute("aria-hidden", "true");
      await page.getByRole("button", { name: "Sohbet geçmişini aç" }).press("Enter");
      await expect(page.locator('[data-slot="aui_thread-list-new"]')).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("creates, reselects, and deletes a signed user's saved investigation after confirmation", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE", "AI_UTM_AMBIGUOUS_QUERY", "AI_UTM_AMBIGUOUS_EXPECTED_TEXT");
    const query = process.env.AI_UTM_AMBIGUOUS_QUERY;
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await createThread(page);
      await ask(page, query);
      await expect(page.getByText(process.env.AI_UTM_AMBIGUOUS_EXPECTED_TEXT, { exact: true })).toBeVisible();
      const saved = page.getByRole("navigation", { name: "Kayıtlı sohbetler" });
      const titled = saved.getByRole("button", { name: query, exact: true });
      await expect(titled).toBeVisible();
      await createThread(page);
      await titled.click();
      await expect(page.getByText(process.env.AI_UTM_AMBIGUOUS_EXPECTED_TEXT, { exact: true })).toBeVisible();
      const remove = page.getByRole("button", { name: `${query} için seçenekler` });
      await remove.click();
      await page.getByRole("menuitem", { name: "Sohbeti sil" }).click();
      const dialog = page.getByRole("alertdialog");
      await expect(dialog.getByRole("button", { name: "Sohbeti tut" })).toBeFocused();
      await dialog.getByRole("button", { name: "Sohbeti tut" }).click();
      await expect(remove).toBeFocused();
      await remove.click();
      await page.getByRole("menuitem", { name: "Sohbeti sil" }).click();
      await dialog.getByRole("button", { name: "Sohbeti sil" }).click();
      await expect(titled).toHaveCount(0);
    } finally {
      await context.close();
    }
  });

  test("streams a curated no-match result through the signed plugin page", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE", "AI_UTM_NO_MATCH_QUERY", "AI_UTM_NO_MATCH_EXPECTED_TEXT");
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await createThread(page);
      await ask(page, process.env.AI_UTM_NO_MATCH_QUERY);
      const progress = page.locator("[data-streaming]");
      await expect(progress.locator("[aria-live='polite']")).toContainText(/Soruyu sınıflandır/);
      await expect(page.getByText(process.env.AI_UTM_NO_MATCH_EXPECTED_TEXT, { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: /İşlem ayrıntıları/i })).toHaveAttribute("aria-expanded", "false");
    } finally {
      await context.close();
    }
  });

  test("announces live stage text changes and preserves keyboard focus during a curated stream", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE", "AI_UTM_LIVE_PROGRESS_QUERY", "AI_UTM_LIVE_PROGRESS_EXPECTED_TEXT");
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await createThread(page);
      const composer = page.getByLabel("Ask LibreNMS");
      await composer.click();
      await expect(composer).toBeFocused();
      await ask(page, process.env.AI_UTM_LIVE_PROGRESS_QUERY);
      const live = page.locator("[data-streaming] [aria-live='polite']");
      await expect(live).toHaveAttribute("aria-live", "polite");
      await expect(live).toContainText(/Soruyu sınıflandır|Cihaz çözümlen|LibreNMS verisi okun|Yanıt hazırlan/);
      await expect(page.locator("[data-streaming] button[aria-expanded]")).toHaveCount(0);
      await expect(page.getByText(process.env.AI_UTM_LIVE_PROGRESS_EXPECTED_TEXT, { exact: true })).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("labels a curated fallback result and exposes one process disclosure", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE", "AI_UTM_FALLBACK_QUERY", "AI_UTM_FALLBACK_EXPECTED_TEXT", "AI_UTM_FALLBACK_THREAD_TITLE");
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await createThread(page);
      await ask(page, process.env.AI_UTM_FALLBACK_QUERY);
      await expect(page.getByText(process.env.AI_UTM_FALLBACK_EXPECTED_TEXT, { exact: true })).toBeVisible();
      await expect(page.getByText("Doğrulanmış güvenli yanıt")).toBeVisible();
      const disclosure = page.getByRole("button", { name: /İşlem ayrıntıları/ });
      await disclosure.click();
      await expect(disclosure).toHaveAttribute("aria-expanded", "true");
      await expect(page.getByLabel("Yanıt aktarım süreleri")).toBeVisible();
      await expect(page.getByText("Çalışma ayrıntıları")).toHaveCount(0);
      assertCoherentMetrics(await persistedRunFor(page, process.env.AI_UTM_FALLBACK_THREAD_TITLE));
    } finally {
      await context.close();
    }
  });

  test("renders live plural down ports as persisted compact rows with inline read-only links", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE");
    const query = "lab-j9772a-02'in down portları hangileri?";
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await createThread(page);
      await ask(page, query);
      const table = page.getByRole("table", { name: "lab-j9772a-02 portları" });
      await expect(table).toBeVisible();
      await expect(page.getByText(/admin=up oper=down/)).toHaveCount(0);
      const port2 = table.getByRole("link", { name: "Port 2" });
      const port3 = table.getByRole("link", { name: "Port 3" });
      await expect(port2).toHaveAttribute("href", /^\/device\/[1-9]\d*\/port\/port=[1-9]\d*$/);
      await expect(port3).toHaveAttribute("href", /^\/device\/[1-9]\d*\/port\/port=[1-9]\d*$/);
      await expect(table.getByRole("cell", { name: "Down" }).first()).toHaveAttribute("data-status", "problem");
      await expect(table.getByRole("cell", { name: "Disabled" }).first()).toHaveAttribute("data-status", "neutral");
      await expect(page.getByRole("link", { name: "Port detayını aç" })).toHaveCount(0);

      const assistant = page.locator("[data-message-id]").last();
      const compact = await assistant.evaluate((message) => {
        const answer = message.querySelector('[data-slot="assistant-answer"]').getBoundingClientRect();
        const actions = message.querySelector('[aria-label="Mesaj eylemleri"]').getBoundingClientRect();
        const details = message.querySelector('[data-slot="pipeline-reasoning"] button');
        const panel = details.nextElementSibling;
        return { gap: actions.top - answer.bottom, panelHeight: panel.getBoundingClientRect().height, panelHidden: panel.hidden };
      });
      expect(compact.gap).toBeLessThanOrEqual(12);
      expect(compact.panelHeight).toBe(0);
      expect(compact.panelHidden).toBe(true);

      const details = assistant.getByRole("button", { name: /İşlem ayrıntıları/i });
      await details.click();
      await expect(assistant.getByRole("region", { name: "İşleme ayrıntıları" })).toBeVisible();
      await details.click();
      await expect(details).toHaveAttribute("aria-expanded", "false");

      await page.reload();
      await page.getByRole("navigation", { name: "Kayıtlı sohbetler" }).getByRole("button", { name: query, exact: true }).click();
      await expect(table).toBeVisible();
      await expect(table.getByRole("link", { name: "Port 2" })).toHaveAttribute("href", /^\/device\/[1-9]\d*\/port\/port=[1-9]\d*$/);

      await page.setViewportSize({ width: 390, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    } finally {
      await context.close();
    }
  });

  test("shows a curated backend failure after streamed progress and retries only when the service permits it", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE", "AI_UTM_RETRY_QUERY", "AI_UTM_RETRY_ERROR_TEXT", "AI_UTM_RETRY_SUCCESS_TEXT");
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await createThread(page);
      await ask(page, process.env.AI_UTM_RETRY_QUERY);
      // The live target must be configured to expose this sequence. This suite
      // observes the product stream; it does not claim to control its timing.
      const live = page.locator("[data-streaming] [aria-live='polite']");
      await expect(live).toContainText("LibreNMS verisi okunuyor");
      await expect(page.getByRole("alert")).toHaveText(process.env.AI_UTM_RETRY_ERROR_TEXT);
      await page.getByRole("button", { name: "Yeniden dene" }).click();
      await expect(page.getByText(process.env.AI_UTM_RETRY_SUCCESS_TEXT, { exact: true })).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("cancels a curated run before its forbidden later answer can appear", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE", "AI_UTM_CANCEL_QUERY", "AI_UTM_CANCEL_FORBIDDEN_TEXT");
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await createThread(page);
      await ask(page, process.env.AI_UTM_CANCEL_QUERY);
      await expect(page.locator("[data-streaming] [aria-live='polite']")).toContainText(/Soruyu sınıflandır/);
      await page.getByRole("button", { name: "Çalışmayı iptal et" }).click();
      await expect(page.locator("[data-streaming]")).toHaveCount(0);
      await expect(page.getByText(process.env.AI_UTM_CANCEL_FORBIDDEN_TEXT, { exact: true })).toHaveCount(0);
    } finally {
      await context.close();
    }
  });

  test("keeps signed-user thread ownership isolated across two authorized browser states", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE", "AI_UTM_SECONDARY_STORAGE_STATE");
    const primary = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    const secondary = await signedPluginPage(browser, process.env.AI_UTM_SECONDARY_STORAGE_STATE);
    try {
      expect(primary.subject).not.toBe(secondary.subject);
      const createResponse = primary.page.waitForResponse((response) => response.url().endsWith("/ai-api/v1/threads") && response.request().method() === "POST");
      await createThread(primary.page);
      const thread = await (await createResponse).json();
      const ownershipStatus = await secondary.page.evaluate(async (threadId) => {
        const config = JSON.parse(document.querySelector("#root")?.dataset.aiAssistantConfig || "{}");
        const response = await fetch(`/ai-api/v1/threads/${threadId}`, { headers: { Authorization: `Bearer ${config.token}` } });
        return response.status;
      }, thread.id);
      expect(ownershipStatus).toBe(404);
    } finally {
      await primary.context.close();
      await secondary.context.close();
    }
  });
});

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
    const payload = encodedPayload ? JSON.parse(atob(encodedPayload.replace(/-/g, "+").replace(/_/g, "/"))) : {};
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
  await page.getByRole("button", { name: "New investigation" }).click();
  const item = page.getByRole("navigation", { name: "Saved investigations" }).getByRole("button", { name: "Untitled investigation" }).first();
  await expect(item).toBeVisible();
  return item;
}

async function ask(page, question) {
  await page.getByLabel("Ask about network state").fill(question);
  await page.getByRole("button", { name: "Start investigation" }).click();
}

test.describe("authorized UTM acceptance", () => {
  test("loads the signed plugin route and keeps the responsive drawer keyboard-accessible", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE");
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await page.setViewportSize({ width: 390, height: 844 });
      await expect(page.getByRole("button", { name: "Open investigations" })).toBeVisible();
      await expect(page.getByLabel("Investigations", { exact: true })).toHaveAttribute("aria-hidden", "true");
      await page.getByRole("button", { name: "Open investigations" }).press("Enter");
      await expect(page.getByRole("button", { name: "New investigation" })).toBeVisible();
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
      const saved = page.getByRole("navigation", { name: "Saved investigations" });
      const titled = saved.getByRole("button", { name: query, exact: true });
      await expect(titled).toBeVisible();
      await createThread(page);
      await titled.click();
      await expect(page.getByText(process.env.AI_UTM_AMBIGUOUS_EXPECTED_TEXT, { exact: true })).toBeVisible();
      const remove = page.getByRole("button", { name: `Delete ${query}` });
      await remove.click();
      const dialog = page.getByRole("alertdialog");
      await expect(dialog.getByRole("button", { name: "Keep thread" })).toBeFocused();
      await dialog.getByRole("button", { name: "Keep thread" }).click();
      await expect(remove).toBeFocused();
      await remove.click();
      await dialog.getByRole("button", { name: "Delete investigation" }).click();
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
      const progress = page.getByRole("region", { name: "Pipeline progress" });
      await expect(progress.getByText(/Pipeline status: planner/)).toBeVisible();
      await expect(page.getByText(process.env.AI_UTM_NO_MATCH_EXPECTED_TEXT, { exact: true })).toBeVisible();
      await expect(progress).toHaveCount(0);
    } finally {
      await context.close();
    }
  });

  test("labels a curated fallback result and exposes the real metric disclosure", async ({ browser }) => {
    skipWithout(test, "AI_UTM_PRIMARY_STORAGE_STATE", "AI_UTM_FALLBACK_QUERY", "AI_UTM_FALLBACK_EXPECTED_TEXT");
    const { context, page } = await signedPluginPage(browser, process.env.AI_UTM_PRIMARY_STORAGE_STATE);
    try {
      await createThread(page);
      await ask(page, process.env.AI_UTM_FALLBACK_QUERY);
      await expect(page.getByText(process.env.AI_UTM_FALLBACK_EXPECTED_TEXT, { exact: true })).toBeVisible();
      await expect(page.getByText("Validated fallback result")).toBeVisible();
      const disclosure = page.getByRole("button", { name: "Show run metrics" });
      await disclosure.click();
      await expect(page.getByRole("button", { name: "Hide run metrics" })).toHaveAttribute("aria-expanded", "true");
      await expect(page.getByText("total_ms", { exact: true })).toBeVisible();
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
      await expect(page.getByRole("region", { name: "Pipeline progress" }).getByText(/Pipeline status:/)).toBeVisible();
      await expect(page.getByRole("alert")).toHaveText(process.env.AI_UTM_RETRY_ERROR_TEXT);
      await page.getByRole("button", { name: "Retry failed investigation" }).click();
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
      await expect(page.getByRole("region", { name: "Pipeline progress" }).getByText(/Pipeline status:/)).toBeVisible();
      await page.getByRole("button", { name: "Cancel run" }).click();
      await expect(page.getByRole("region", { name: "Pipeline progress" })).toHaveCount(0);
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

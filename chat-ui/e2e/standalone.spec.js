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
  const removedExistingThreads = await page.evaluate(async () => {
    const token = window.__LIBRENMS_AI_ASSISTANT__?.token;
    const headers = { Authorization: `Bearer ${token}` };
    const threads = await (await fetch("/ai-api/v1/threads", { headers })).json();
    await Promise.all(threads.map((thread) => fetch(`/ai-api/v1/threads/${thread.id}`, { method: "DELETE", headers })));
    return threads.length;
  });
  if (removedExistingThreads) await page.reload();
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

test("keeps New Chat idempotent while pristine and enables it after the first message", async ({ page }) => {
  const newChat = page.locator('[data-slot="aui_thread-list-new"]');
  await createThread(page);
  await expect(newChat).toBeDisabled();
  const pristineCount = await page.evaluate(async () => {
    const token = window.__LIBRENMS_AI_ASSISTANT__?.token;
    return (await (await fetch("/ai-api/v1/threads", { headers: { Authorization: `Bearer ${token}` } })).json()).length;
  });

  await newChat.click({ force: true });
  const afterDuplicate = await page.evaluate(async () => {
    const token = window.__LIBRENMS_AI_ASSISTANT__?.token;
    return (await (await fetch("/ai-api/v1/threads", { headers: { Authorization: `Bearer ${token}` } })).json()).length;
  });
  expect(afterDuplicate).toBe(pristineCount);

  await ask(page, "first meaningful message");
  await expect(page.getByText("Deterministic standalone result.")).toBeVisible();
  await expect(newChat).toBeEnabled();
  await createThread(page);
  const afterContent = await page.evaluate(async () => {
    const token = window.__LIBRENMS_AI_ASSISTANT__?.token;
    return (await (await fetch("/ai-api/v1/threads", { headers: { Authorization: `Bearer ${token}` } })).json()).length;
  });
  expect(afterContent).toBe(pristineCount + 1);
});

test("restores safe navigation after reload and suppresses malformed targets", async ({ page }) => {
  await ask(page, "navigation persistence");
  const navigation = page.getByRole("navigation", { name: "LibreNMS bağlantıları" });
  await expect(navigation.getByRole("link", { name: /LibreNMS'te cihazı aç/ })).toHaveAttribute("href", "/device/1");

  await page.reload();
  await page.getByRole("navigation", { name: "Kayıtlı sohbetler" }).getByRole("button", { name: "navigation persistence", exact: true }).click();
  await expect(navigation.getByRole("link", { name: /LibreNMS'te cihazı aç/ })).toHaveAttribute("href", "/device/1");

  await ask(page, "malformed navigation");
  await expect(page.getByText("Validated result without an action.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Unsafe" })).toHaveCount(0);
});

test("renders compact structured port rows, inline links, and the action row after reload without overflow", async ({ page }) => {
  await ask(page, "structured port list");
  const table = page.getByRole("table", { name: "lab-j9772a-02 portları" });
  await expect(table).toBeVisible();
  await expect(page.getByText(/admin=up oper=down/)).toHaveCount(0);
  await expect(table.getByRole("link", { name: "Port 2" })).toHaveAttribute("href", "/device/7/port/port=41");
  await expect(table.getByRole("link", { name: "Port 3" })).toHaveAttribute("href", "/device/7/port/port=42");
  await expect(table.getByRole("cell", { name: "Down" }).first()).toHaveAttribute("data-status", "problem");
  await expect(table.getByRole("cell", { name: "Disabled" }).first()).toHaveAttribute("data-status", "neutral");
  await expect(page.getByRole("link", { name: "Port detayını aç" })).toHaveCount(0);

  const actions = page.getByRole("group", { name: "Mesaj eylemleri" });
  await expect(actions.getByRole("button", { name: "Yanıtı kopyala" })).toBeVisible();
  const details = actions.getByRole("button", { name: /İşlem ayrıntıları/i });
  await expect(details).toHaveAttribute("aria-expanded", "false");
  const compactGap = await page.locator("[data-message-id]").last().evaluate((message) => {
    const answer = message.querySelector('[data-slot="assistant-answer"]').getBoundingClientRect();
    const actionRow = message.querySelector('[aria-label="Mesaj eylemleri"]').getBoundingClientRect();
    return actionRow.top - answer.bottom;
  });
  expect(compactGap).toBeLessThanOrEqual(12);

  await details.click();
  await expect(page.getByRole("region", { name: "İşleme ayrıntıları" })).toBeVisible();
  await details.click();
  await expect(details).toHaveAttribute("aria-expanded", "false");

  await page.reload();
  await page.getByRole("navigation", { name: "Kayıtlı sohbetler" }).getByRole("button", { name: "structured port list", exact: true }).click();
  await expect(table).toBeVisible();
  await expect(table.getByRole("link", { name: "Port 2" })).toHaveAttribute("href", "/device/7/port/port=41");

  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("renders structured alert rows and empty state from persisted metadata", async ({ page }) => {
  await ask(page, "structured alert list");
  const table = page.getByRole("table", { name: "lab-j9772a-01 aktif alarmları" });
  await expect(table).toBeVisible();
  await expect(page.getByText(/severity=critical|state=1/)).toHaveCount(0);
  await expect(page.getByText("3 aktif alarm")).toBeVisible();
  await expect(table.getByRole("cell", { name: "Kritik" })).toHaveAttribute("data-severity", "critical");
  await expect(table.getByRole("cell", { name: "Uyarı" })).toHaveAttribute("data-severity", "warning");
  await expect(table.getByRole("cell", { name: "Bilinmiyor" })).toHaveAttribute("data-severity", "neutral");
  await expect(page.getByRole("link", { name: /LibreNMS'te aç/ })).toHaveAttribute("href", "/device/7/alerts");
  await expect(page.getByRole("link", { name: "Cihaz alarmlarını aç" })).toHaveCount(0);

  await page.reload();
  await page.getByRole("navigation", { name: "Kayıtlı sohbetler" }).getByRole("button", { name: "structured alert list", exact: true }).click();
  await expect(table).toBeVisible();
  await expect(table.getByRole("cell", { name: "#88" })).toBeVisible();

  await createThread(page);
  await ask(page, "structured alert empty");
  await expect(page.getByText("Aktif alarm bulunmuyor.")).toBeVisible();
  await expect(page.getByText("developer empty fallback")).toHaveCount(0);
  await expect(page.getByRole("table")).toHaveCount(0);
});

test("uses the same sanitized inspection for dark JSON and Python code views", async ({ page }) => {
  await page.evaluate(async () => {
    const token = window.__LIBRENMS_AI_ASSISTANT__?.token;
    await fetch("/ai-api/v1/demo-mode", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });
  });
  await page.reload();
  const demoMode = page.getByLabel("Demo Mode");
  await expect(demoMode).toBeChecked();
  await ask(page, "inspector code surface");
  await expect(page.getByText("Validated inspector result.")).toBeVisible();
  await page.getByRole("button", { name: /İşlem ayrıntılarını göster/ }).click();
  const panel = page.getByRole("region", { name: "İşleme ayrıntıları" });
  await panel.getByRole("tab", { name: "JSON" }).click();
  const jsonCode = panel.locator("pre");
  await expect(jsonCode).toContainText('"route": "alerts"');
  const jsonStyle = await jsonCode.evaluate((element) => ({
    background: getComputedStyle(element).backgroundColor,
    overflowX: getComputedStyle(element).overflowX,
    font: getComputedStyle(element).fontFamily,
  }));
  expect(jsonStyle.background).toBe("rgb(17, 22, 26)");
  expect(jsonStyle.overflowX).toBe("auto");
  expect(jsonStyle.font).toContain("monospace");

  await panel.getByRole("tab", { name: "Python" }).click();
  const pythonCode = panel.locator("pre");
  await expect(pythonCode).toContainText("'route': 'alerts'");
  await expect(pythonCode).toContainText("'synthesis_llm_called': False");
  await expect(pythonCode).not.toContainText(/secret|token|system prompt|raw model/i);
  await expect(pythonCode).toHaveCSS("background-color", jsonStyle.background);
});

test("builds assistant-ui starter prompts from currently up devices", async ({ page }) => {
  const liveSuggestion = page.getByRole("button", { name: /lab-j9775a-01 açık mı/i });
  await expect(liveSuggestion).toBeVisible();
  await liveSuggestion.click();
  await expect(page.getByText("lab-j9775a-01 açık mı?")).toBeVisible();
  await expect(page.getByText("Deterministic standalone result.")).toBeVisible();
  await expect(page.getByRole("button", { name: /lab-offline-01/i })).toHaveCount(0);
});

test("uses one live device picker for icon and at-search without auto-submitting", async ({ page }) => {
  const composer = page.getByLabel("Ask LibreNMS");
  await page.getByRole("button", { name: "Cihaz seç" }).click();
  let picker = page.getByRole("dialog", { name: "Canlı cihaz seçici" });
  await expect(picker.getByRole("option", { name: "lab-j9775a-01 Up" })).toBeVisible();
  await expect(picker.getByRole("option", { name: "lab-offline-01 Down" })).toBeVisible();
  await expect(picker.getByRole("option", { name: "lab-unknown-01 Unknown" })).toBeVisible();
  await picker.getByRole("option", { name: "lab-offline-01 Down" }).click();
  await expect(composer).toHaveValue("lab-offline-01 ");
  await expect(page.locator("[data-message-id]")).toHaveCount(0);

  await composer.fill("");
  await expect(composer).toHaveValue("");
  await composer.fill("@lab-j9775");
  picker = page.getByRole("dialog", { name: "Canlı cihaz seçici" });
  await expect(picker.getByRole("listbox", { name: "Canlı cihazlar" }).getByRole("option")).toHaveCount(1);
  await composer.press("Enter");
  await expect(composer).toHaveValue("lab-j9775a-01 ");
  await expect(page.locator("[data-message-id]")).toHaveCount(0);

  await page.getByRole("button", { name: "Cihaz seç" }).click();
  const recent = page.getByRole("listbox", { name: "Son kullanılan cihazlar" });
  await expect(recent.getByRole("option").first()).toHaveAccessibleName("lab-j9775a-01 Up");
});

test("keeps contextual discovery optional and leaves its selected example editable", async ({ page }) => {
  const composer = page.getByLabel("Ask LibreNMS");
  await composer.fill("@lab-j9775");
  await page.getByRole("option", { name: "lab-j9775a-01 Up" }).click();
  const discovery = page.getByRole("button", { name: "Neler sorabilirim?" });
  await expect(discovery).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("region", { name: "Bağlamsal soru örnekleri" })).toHaveCount(0);
  await discovery.click();
  const examples = page.getByRole("region", { name: "Bağlamsal soru örnekleri" });
  await expect(examples.getByRole("button")).toHaveCount(3);
  await examples.getByRole("button", { name: "lab-j9775a-01 üzerinde aktif alarm var mı?" }).click();
  await expect(composer).toHaveValue("lab-j9775a-01 üzerinde aktif alarm var mı?");
  await composer.fill("lab-j9775a-01 için farklı bir doğal dil sorusu");
  await expect(composer).toHaveValue("lab-j9775a-01 için farklı bir doğal dil sorusu");
  await expect(page.locator("[data-message-id]")).toHaveCount(0);
});

test("rotates the capability-first suggestion set on a consecutive new chat", async ({ page }) => {
  const suggestions = page.getByLabel("Canlı cihaz önerileri").getByRole("button");
  await expect(suggestions).toHaveCount(4);
  const firstSet = new Set(await suggestions.allTextContents());
  expect([...firstSet].some((text) => text.includes("Aktif alarmlar"))).toBe(true);
  expect([...firstSet].some((text) => text.includes("Son olaylar"))).toBe(true);

  await ask(page, "prepare suggestion rotation");
  await expect(page.getByText("Deterministic standalone result.")).toBeVisible();
  await createThread(page);
  await expect(suggestions).toHaveCount(4);
  const secondSet = new Set(await suggestions.allTextContents());
  expect(secondSet).not.toEqual(firstSet);
  expect([...secondSet].every((text) => !firstSet.has(text))).toBe(true);
  expect([...secondSet].some((text) => text.includes("Cihaz incelemesi"))).toBe(true);
});

test("fills the available conversation height without clipping starter prompts", async ({ page }, testInfo) => {
  const [threadBox, mainBox] = await Promise.all([
    page.locator('[data-assistant-ui="thread"]').boundingBox(),
    page.locator("#investigation-main").boundingBox(),
  ]);
  expect(Math.abs((threadBox.y + threadBox.height) - (mainBox.y + mainBox.height))).toBeLessThanOrEqual(1);
  const suggestions = page.getByLabel("Canlı cihaz önerileri");
  await expect(suggestions).toBeInViewport();
  const suggestionBox = await suggestions.boundingBox();
  expect(suggestionBox.y + suggestionBox.height).toBeLessThanOrEqual(threadBox.y + threadBox.height);
  const shellBox = await page.locator("#root > div").boundingBox();
  expect(Math.abs((shellBox.y + shellBox.height) - page.viewportSize().height)).toBeLessThanOrEqual(1);

  const [headingBox, composerBox] = await Promise.all([
    page.getByRole("heading", { name: "Ağında neyi inceleyelim?" }).boundingBox(),
    page.getByLabel("Ask LibreNMS").boundingBox(),
  ]);
  const contentCenter = (headingBox.y + composerBox.y + composerBox.height) / 2;
  const availableCenter = threadBox.y + (threadBox.height / 2);
  expect(Math.abs(contentCenter - availableCenter)).toBeLessThan(threadBox.height * 0.18);
  await page.screenshot({ path: testInfo.outputPath("new-chat-balanced-layout.png"), fullPage: true });
});

test("keeps empty and completed composers inside the host shell with a long thread history", async ({ page }) => {
  const seeded = await page.evaluate(async () => {
    const token = window.__LIBRENMS_AI_ASSISTANT__?.token;
    for (let index = 0; index < 40; index += 1) {
      const response = await fetch("/ai-api/v1/threads", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: "{}",
      });
      if (!response.ok) return response.status;
    }
    return 201;
  });
  expect(seeded).toBe(201);

  const reloadedThreads = page.waitForResponse((response) =>
    response.url().endsWith("/ai-api/v1/threads") && response.request().method() === "GET",
  );
  await page.reload();
  expect((await reloadedThreads).status()).toBe(200);

  const assertComposerWithinShell = async () => {
    const geometry = await page.evaluate(() => {
      const shell = document.querySelector("#root > div").getBoundingClientRect();
      const main = document.querySelector("#investigation-main").getBoundingClientRect();
      const composer = document.querySelector('textarea[aria-label="Ask LibreNMS"]').getBoundingClientRect();
      return {
        shellBottom: shell.bottom,
        mainBottom: main.bottom,
        composerTop: composer.top,
        composerBottom: composer.bottom,
      };
    });
    expect(Math.abs(geometry.mainBottom - geometry.shellBottom)).toBeLessThanOrEqual(1);
    expect(geometry.composerTop).toBeGreaterThanOrEqual(0);
    expect(geometry.composerBottom).toBeLessThanOrEqual(geometry.shellBottom);
    await expect(page.getByLabel("Ask LibreNMS")).toBeInViewport();
  };

  await assertComposerWithinShell();
  await ask(page, "completed composer remains visible");
  await expect(page.getByText("Deterministic standalone result.")).toBeVisible();
  await assertComposerWithinShell();
  await expect(page.getByLabel("Ask LibreNMS")).toBeEnabled();
});

test("keeps the composer visible and drains queued follow-ups once in FIFO order", async ({ page }, testInfo) => {
  const runRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/runs") && request.method() === "POST") runRequests.push(request.postDataJSON().content);
  });

  await createThread(page);
  await ask(page, "queue barrier first");
  await expect(page.locator("[data-streaming] [aria-live='polite']")).toContainText("Soruyu sınıflandırdı");
  const composer = page.getByLabel("Ask LibreNMS");
  await expect(composer).toBeVisible();
  await expect(composer).toBeEnabled();

  await composer.fill("queue follow-up second");
  await composer.press("Enter");
  await composer.fill("queue follow-up third");
  await composer.press("Enter");
  await expect(page.getByLabel("Sıradaki sorular")).toContainText("2 sırada");
  expect(runRequests).toEqual(["queue barrier first"]);
  await page.screenshot({ path: testInfo.outputPath("active-run-visible-composer-and-queue.png"), fullPage: true });

  const releaseStatus = await page.evaluate(async () => (await fetch("/ai-api/__test__/release-queue-barrier", { method: "POST" })).status);
  expect(releaseStatus).toBe(204);
  await expect.poll(() => runRequests).toEqual([
    "queue barrier first",
    "queue follow-up second",
    "queue follow-up third",
  ]);
  await expect(page.getByLabel("Sıradaki sorular")).toHaveCount(0);
  await expect(page.locator("[data-message-id]")).toHaveCount(6);
});

test("removes queued items and Stop preserves the remaining queue without draining", async ({ page }) => {
  const runRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/runs") && request.method() === "POST") runRequests.push(request.postDataJSON().content);
  });

  await createThread(page);
  await ask(page, "cancel after planner queue policy");
  await expect(page.locator("[data-streaming] [aria-live='polite']")).toContainText("Soruyu sınıflandırdı");
  const composer = page.getByLabel("Ask LibreNMS");
  await composer.fill("remove this queued question");
  await composer.press("Enter");
  await composer.fill("keep this queued question");
  await composer.press("Enter");
  await expect(page.getByLabel("Sıradaki sorular")).toContainText("2 sırada");

  await page.getByRole("button", { name: "Sıradaki soruyu kaldır: remove this queued question" }).click();
  await expect(page.getByLabel("Sıradaki sorular")).toContainText("1 sırada");
  await page.getByRole("button", { name: "Çalışmayı iptal et" }).click();
  await expect(page.locator("[data-streaming]")).toHaveCount(0);
  await expect(page.getByLabel("Sıradaki sorular")).toContainText("keep this queued question");
  expect(runRequests).toEqual(["cancel after planner queue policy"]);
});

test("clears queued work when the active conversation is replaced", async ({ page }) => {
  const runRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/runs") && request.method() === "POST") runRequests.push(request.postDataJSON().content);
  });

  await createThread(page);
  await ask(page, "queue barrier isolation");
  await expect(page.locator("[data-streaming] [aria-live='polite']")).toContainText("Soruyu sınıflandırdı");
  const composer = page.getByLabel("Ask LibreNMS");
  await composer.fill("must never reach another thread");
  await composer.press("Enter");
  await expect(page.getByLabel("Sıradaki sorular")).toBeVisible();

  await createThread(page);
  await expect(page.getByLabel("Sıradaki sorular")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Ağında neyi inceleyelim?" })).toBeVisible();
  await page.evaluate(async () => { await fetch("/ai-api/__test__/release-queue-barrier", { method: "POST" }); });
  await page.waitForTimeout(350);
  expect(runRequests).toEqual(["queue barrier isolation"]);
  await expect(page.getByText("must never reach another thread", { exact: true })).toHaveCount(0);
});

test("clears queued work when switching to a saved conversation", async ({ page }) => {
  const runRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/runs") && request.method() === "POST") runRequests.push(request.postDataJSON().content);
  });

  await createThread(page);
  await ask(page, "saved switch target");
  await expect(page.getByText("Deterministic standalone result.")).toBeVisible();
  const savedTarget = page.getByRole("navigation", { name: "Kayıtlı sohbetler" }).getByRole("button", { name: "saved switch target", exact: true });
  await createThread(page);
  await ask(page, "queue barrier switch source");
  await expect(page.locator("[data-streaming] [aria-live='polite']")).toContainText("Soruyu sınıflandırdı");
  const composer = page.getByLabel("Ask LibreNMS");
  await composer.fill("stale switch follow-up");
  await composer.press("Enter");
  await savedTarget.click();
  await expect(page.getByLabel("Sıradaki sorular")).toHaveCount(0);

  await page.evaluate(async () => { await fetch("/ai-api/__test__/release-queue-barrier", { method: "POST" }); });
  await page.waitForTimeout(350);
  expect(runRequests).toEqual(["saved switch target", "queue barrier switch source"]);
  await expect(page.getByText("stale switch follow-up", { exact: true })).toHaveCount(0);
});

test("clears queued work before deleting its running conversation", async ({ page }) => {
  const runRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/runs") && request.method() === "POST") runRequests.push(request.postDataJSON().content);
  });

  await createThread(page);
  await ask(page, "queue barrier delete source");
  await expect(page.locator("[data-streaming] [aria-live='polite']")).toContainText("Soruyu sınıflandırdı");
  const composer = page.getByLabel("Ask LibreNMS");
  await composer.fill("stale delete follow-up");
  await composer.press("Enter");
  await page.getByRole("button", { name: "Yeni sohbet için seçenekler" }).first().click();
  await page.getByRole("menuitem", { name: "Sohbeti sil" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Sohbeti sil" }).click();

  await expect(page.getByLabel("Sıradaki sorular")).toHaveCount(0);
  await page.waitForTimeout(250);
  expect(runRequests).toEqual(["queue barrier delete source"]);
  await expect(page.getByText("stale delete follow-up", { exact: true })).toHaveCount(0);
});

test("reload discards the in-memory queue", async ({ page }) => {
  const runRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/runs") && request.method() === "POST") runRequests.push(request.postDataJSON().content);
  });

  await createThread(page);
  await ask(page, "queue barrier reload source");
  await expect(page.locator("[data-streaming] [aria-live='polite']")).toContainText("Soruyu sınıflandırdı");
  const composer = page.getByLabel("Ask LibreNMS");
  await composer.fill("stale reload follow-up");
  await composer.press("Enter");
  await expect(page.getByLabel("Sıradaki sorular")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Sıradaki sorular")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Ağında neyi inceleyelim?" })).toBeVisible();
  await page.evaluate(async () => { await fetch("/ai-api/__test__/release-queue-barrier", { method: "POST" }); });
  await page.waitForTimeout(350);
  expect(runRequests).toEqual(["queue barrier reload source"]);
  await expect(page.getByText("stale reload follow-up", { exact: true })).toHaveCount(0);
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
  const live = page.locator("[data-streaming] [aria-live='polite']");
  await expect(page.locator("[data-streaming] button[aria-expanded]")).toHaveCount(0);
  await expect(live).toContainText(/Soruyu sınıflandır/);
  await expect(live).toContainText(/Cihaz çözüml/);
  await expect(page.getByText("No monitored device matches that name.")).toBeVisible();
  await expect(page.locator('[data-assistant-ui="thread"]')).toBeVisible();
  await expect(page.locator("[data-message-id]")).toHaveCount(2);
  await expect(page.getByRole("button", { name: /İşlem ayrıntıları/i })).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByText("No monitored device matches that name.")).toBeVisible();
});

test("completed process disclosure follows the answer without a closed layout row", async ({ page }) => {
  await createThread(page);
  await ask(page, "no-match branch switch");
  await expect(page.getByText("No monitored device matches that name.")).toBeVisible();
  const assistant = page.locator("[data-message-id]").last();
  const closed = await assistant.evaluate((message) => {
    const answer = message.querySelector('[data-slot="assistant-answer"]');
    const reasoning = message.querySelector('[data-slot="pipeline-reasoning"]');
    const trigger = reasoning.querySelector("button");
    const panel = trigger.nextElementSibling;
    return {
      answerBeforeReasoning: Boolean(
        answer.compareDocumentPosition(reasoning) & Node.DOCUMENT_POSITION_FOLLOWING
      ),
      gap: trigger.getBoundingClientRect().top - answer.getBoundingClientRect().bottom,
      panelHeight: panel.getBoundingClientRect().height,
      panelDisplay: getComputedStyle(panel).display,
      panelHidden: panel.hidden,
    };
  });
  expect(closed).toMatchObject({
    answerBeforeReasoning: true,
    panelHeight: 0,
    panelDisplay: "none",
    panelHidden: true,
  });
  expect(closed.gap).toBeLessThanOrEqual(12);

  await page.getByRole("button", { name: /İşlem ayrıntıları/i }).click();
  const open = await assistant.evaluate((message) => {
    const reasoning = message.querySelector('[data-slot="pipeline-reasoning"]');
    const trigger = reasoning.querySelector("button");
    const panel = trigger.nextElementSibling;
    return {
      triggerToPanelGap: panel.getBoundingClientRect().top - trigger.getBoundingClientRect().bottom,
      panelHeight: panel.getBoundingClientRect().height,
      panelDisplay: getComputedStyle(panel).display,
      panelHidden: panel.hidden,
    };
  });
  expect(open.triggerToPanelGap).toBeLessThanOrEqual(12);
  expect(open.panelHeight).toBeGreaterThan(0);
  expect(open.panelDisplay).toBe("block");
  expect(open.panelHidden).toBe(false);
});

test("shows a retryable backend failure and allows a real retried stream to succeed", async ({ page }) => {
  await createThread(page);
  await ask(page, "retryable backend question");
  const live = page.locator("[data-streaming] [aria-live='polite']");
  await expect(live).toContainText(/LibreNMS verisi okunuyor/);
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
  await expect(disclosure).not.toContainText(`${persistedRun.total_ms} ms`);
  await expect(page.getByText(`${persistedRun.total_ms} ms`, { exact: true })).toBeVisible();
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

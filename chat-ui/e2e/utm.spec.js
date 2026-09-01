import { expect, test } from "@playwright/test";

const hasAuthorizedTarget = process.env.AI_UTM_AUTHORIZED === "1" && Boolean(process.env.AI_UTM_BASE_URL);

test.describe("authorized UTM acceptance", () => {
  test.skip(!hasAuthorizedTarget, "UTM target and explicit authorization are required; no default host is used.");

  test("opens the plugin route before authorized signed-user acceptance", async ({ page }) => {
    await page.goto("/plugin/AiAssistant");
    await expect(page.getByRole("main")).toBeVisible();
  });
});

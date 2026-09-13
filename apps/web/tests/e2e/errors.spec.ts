import { expect, test } from "@playwright/test";
import { VIEWPORTS, msg, waitForProgrammeResults } from "./helpers";

test("inventory request failure is not an empty result and retry restores the list", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.phone);
  let failed = false;
  await page.route("**/browse/nine-hei-inventory.json", async (route) => {
    if (!failed) {
      failed = true;
      await route.fulfill({ status: 503, contentType: "text/plain", body: "upstream unavailable" });
      return;
    }
    await route.continue();
  });
  await page.goto("/en/programmes?teachingLanguage=en");
  await expect(page.getByRole("heading", { name: msg("en", "error.loadFailed") })).toBeVisible();
  await expect(page.locator(".empty.card").getByText(msg("en", "error.partialCatalog"))).toBeVisible();
  await expect(page.getByRole("heading", { name: msg("en", "empty.title") })).toHaveCount(0);
  await page.getByRole("button", { name: msg("en", "error.retry") }).click();
  await waitForProgrammeResults(page, "en");
  await expect(page.locator("article.result-card").first()).toBeVisible();
});

import { expect, test } from "@playwright/test";
import { LOCALES, msg } from "./helpers";

// Packet 5 acceptance: the new UHK postdocs are public in the all-tracks
// route, link to official application instructions, and stay out of the
// funded-doctoral filter, in all three locales.
const NEW_ID = "job-18000-0b0de28455a7";

for (const locale of LOCALES) {
  test(`UHK postdoc visible in all-tracks and hidden from funded (${locale})`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/${locale}/research-jobs?applied=1&track=all`);
    await expect(page.locator("article.result-card").first()).toBeVisible();
    const newId = NEW_ID;
    const allIds = await page.evaluate((id) => document.body.innerHTML.includes(id) ? "yes" : "no", newId);
    // Search by the institution name to land on the UHK records deterministically.
    await page.goto(`/${locale}/research-jobs?applied=1&track=all&q=Hradec`);
    await expect(page.locator("article.result-card").first()).toBeVisible({ timeout: 20_000 });
    const found = await page.locator("article.result-card", { hasText: "Bioorganic" }).count();
    expect(found, "bioorganic postdoc should be searchable by topic").toBeGreaterThan(0);
    expect(allIds === "yes" || found > 0).toBeTruthy();

    await page.goto(`/${locale}/research-jobs?applied=1&funded=1`);
    await expect(page.locator("article.result-card").first()).toBeVisible();
    const fundedIds = await page.evaluate((id) => document.body.innerHTML.includes(id), newId);
    expect(fundedIds, "postdoc must stay out of funded-doctoral results").toBeFalsy();

    await page.goto(`/${locale}/research-jobs/${NEW_ID}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator("main").getByRole("link", { name: /www\.uhk\.cz/ }).first()).toBeVisible();
  });

  test(`UHK postdoc title renders in ${locale}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/${locale}/research-jobs/${NEW_ID}`);
    const h1 = await page.locator("h1").innerText();
    if (locale === "zh-CN") {
      expect(h1).toContain("生物有机化学博士后");
    } else if (locale === "cs") {
      expect(h1).toContain("Postdoktorand v bioorganické chemii");
    } else {
      expect(h1).toContain("Postdoctoral Researcher in Bioorganic Chemistry");
    }
  });
}

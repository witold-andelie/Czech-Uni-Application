import { expect, test } from "@playwright/test";
import { LOCALES, VIEWPORTS, msg } from "./helpers";

// A80: the product is anonymous browsing. Shortlist and comparison were
// removed; these checks keep them from silently returning. Labels are gone
// from the locale bundles, so assertions work on links/routes instead.
const REMOVED_HREFS = 'a[href$="/saved"], a[href$="/compare"]';

for (const locale of LOCALES) {
  test(`navigation exposes only browse entries (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto(`/${locale}/programmes`);
    const nav = page.getByRole("navigation", { name: msg(locale, "nav.main") });
    await expect(nav).toBeVisible();
    for (const key of ["nav.programmes", "nav.institutions", "nav.map", "nav.research", "nav.guides"]) {
      await expect(nav.getByRole("link", { name: msg(locale, key) })).toHaveCount(1);
    }
    // The removed entries must exist neither in the desktop nor mobile nav.
    await expect(page.locator(REMOVED_HREFS)).toHaveCount(0);

    await page.setViewportSize(VIEWPORTS.phone);
    await page.goto(`/${locale}/research-jobs`);
    await expect(page.locator(REMOVED_HREFS)).toHaveCount(0);
  });

  test(`cards and details link to no save or compare surface (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto(`/${locale}/programmes?teachingLanguage=en`);
    await expect(page.locator("article.result-card").first()).toBeVisible();
    await expect(page.locator(REMOVED_HREFS)).toHaveCount(0);

    await page.goto(`/${locale}/research-jobs`);
    await expect(page.locator("article.result-card").first()).toBeVisible();
    await expect(page.locator(REMOVED_HREFS)).toHaveCount(0);

    const firstJob = page.locator("article.result-card a").first();
    if (await firstJob.count()) {
      const detailHref = await firstJob.getAttribute("href");
      if (detailHref && detailHref.startsWith(`/${locale}/research-jobs/`)) {
        await page.goto(detailHref);
        await expect(page.locator(REMOVED_HREFS)).toHaveCount(0);
      }
    }
  });

  test(`legacy saved/compare URLs land on the browse list (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto(`/${locale}/saved`);
    await expect(page).toHaveURL(new RegExp(`/${locale}/programmes`));
    await page.goto(`/${locale}/compare`);
    await expect(page).toHaveURL(new RegExp(`/${locale}/programmes`));
  });
}

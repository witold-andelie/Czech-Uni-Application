import { expect, test } from "@playwright/test";
import { LOCALES, msg } from "./helpers";

// The latest official-source check invalidated the evidence previously used to
// publish this UHK postdoc. Keep a browser-level regression around the safety
// boundary: a review-invalidated candidate must disappear from every public
// list and its former detail URL must resolve to the localized not-found page.
const REVIEW_INVALIDATED_ID = "job-18000-0b0de28455a7";

for (const locale of LOCALES) {
  test(`review-invalidated UHK postdoc is not public (${locale})`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    for (const query of ["applied=1&track=all", "applied=1&funded=1"]) {
      await page.goto(`/${locale}/research-jobs?${query}`);
      await expect(page.locator("article.result-card").first()).toBeVisible();
      const isPresent = await page.evaluate(
        (id) => document.body.innerHTML.includes(id),
        REVIEW_INVALIDATED_ID,
      );
      expect(isPresent, "review-invalidated job must not remain in public results").toBeFalsy();
    }

    await page.goto(`/${locale}/research-jobs/${REVIEW_INVALIDATED_ID}`);
    await expect(page.getByRole("heading", { level: 1, name: msg(locale, "error.notFound") })).toBeVisible();
  });
}

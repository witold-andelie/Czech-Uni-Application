import { expect, test } from "@playwright/test";
import { LOCALES, VIEWPORTS, assertNoHorizontalOverflow, msg, type TestLocale } from "./helpers";

// The 2026-09-26 owner decision turned /guides from three paragraphs into a
// structured page. What it must keep doing is pointing at lists that really
// exist and reusing the exact vocabulary the cards and detail pages show, so
// this spec walks the page in all three languages and follows every link it
// offers.
const SECTION_IDS = ["language", "rounds", "tuition", "languages", "jobs", "institutions", "limits"];

for (const locale of LOCALES) {
  test(`guides lists every section and every anchor resolves (${locale})`, async ({ page }) => {
    await page.goto(`/${locale}/guides`);
    await expect(page.getByRole("heading", { level: 1, name: msg(locale, "guides.title") })).toBeVisible();

    const contents = page.locator('nav[aria-labelledby="guides-contents"] a');
    await expect(contents).toHaveCount(SECTION_IDS.length);
    const hrefs = await contents.evaluateAll((links) => links.map((link) => link.getAttribute("href") ?? ""));
    expect(hrefs).toEqual(SECTION_IDS.map((id) => `#${id}`));
    for (const id of SECTION_IDS) {
      await expect(page.locator(`section.panel#${id}`)).toHaveCount(1);
    }

    // One h1, and every section heading below it: no skipped levels.
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    await expect(page.locator("h3, h4, h5, h6")).toHaveCount(0);
  });

  test(`guides stays inside the phone viewport (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.phone);
    await page.goto(`/${locale}/guides`);
    await expect(page.getByRole("heading", { level: 1, name: msg(locale, "guides.title") })).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });

  test(`guides speaks the same vocabulary as the cards it links to (${locale})`, async ({ page }) => {
    await page.goto(`/${locale}/guides`);
    const jobs = page.locator("section.panel#jobs");
    // The two independent axes and the three pay states are named with the
    // strings the job detail and cards use, not with paraphrases.
    await expect(jobs.getByText(msg(locale, "jobs.trackHint"), { exact: false }).first()).toBeVisible();
    await expect(jobs.getByText(msg(locale, "jobs.thresholdHint"), { exact: false }).first()).toBeVisible();
    await expect(jobs.getByText(msg(locale, "jobs.masterMeansDegree"), { exact: false }).first()).toBeVisible();
    for (const key of ["jobs.paidConfirmed", "jobs.payUnstated", "jobs.payUnpaid"]) {
      await expect(jobs.getByText(msg(locale, key), { exact: true }).first()).toBeVisible();
    }
    for (const key of ["jobs.phd.required", "jobs.phd.optional", "jobs.phd.no", "jobs.phd.unknown"]) {
      await expect(jobs.getByText(msg(locale, key), { exact: true }).first()).toBeVisible();
    }
    // Tuition and recognition disclaimers are repeated verbatim on the guide.
    await expect(page.locator("section.panel#tuition").getByText(msg(locale, "tuition.unpublishedNotFree"), { exact: true })).toBeVisible();
    await expect(page.locator("section.panel#institutions").getByText(msg(locale, "recognition.disclaimer"), { exact: true })).toBeVisible();
    await expect(page.locator("section.panel#limits").getByText(msg(locale, "detail.notSubmitted"), { exact: true })).toBeVisible();
  });

  test(`every list link on guides opens a real page (${locale})`, async ({ page }) => {
    await page.goto(`/${locale}/guides`);
    const hrefs = await page
      .locator("main a[href]")
      .evaluateAll((links) =>
        links
          .map((link) => link.getAttribute("href") ?? "")
          .filter((href) => href.startsWith("/") || href.startsWith("http")),
      );
    const internal = [...new Set(hrefs)].filter((href) => href.startsWith("/"));
    expect(internal.length).toBeGreaterThan(8);

    for (const href of internal) {
      await page.goto(href);
      // A route that no longer exists renders the 404 page; the guide must not
      // point at one.
      await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(msg(locale, "error.notFound"));
      const title = await page.title();
      expect(title, `${href} should render`).not.toBe("");
    }
  });
}

test("guides keeps its page identity in every locale", async ({ page }) => {
  for (const locale of LOCALES as readonly TestLocale[]) {
    await page.goto(`/${locale}/guides`);
    await expect(page.locator("html")).toHaveAttribute("lang", locale);
    await expect(page.locator(`link[rel="canonical"]`)).toHaveAttribute("href", new RegExp(`/${locale}/guides/?$`));
  }
});

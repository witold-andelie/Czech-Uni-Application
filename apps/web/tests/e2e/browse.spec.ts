import { expect, test } from "@playwright/test";
import {
  LOCALES,
  VIEWPORTS,
  assertNoHorizontalOverflow,
  msg,
  waitForProgrammeResults,
  type TestLocale,
} from "./helpers";

const viewports = ["phone", "tablet", "desktop"] as const;

for (const locale of LOCALES) {
  for (const size of viewports) {
    test(`teaching-language first then populated list (${locale} ${size})`, async ({ page }) => {
      await page.setViewportSize(VIEWPORTS[size]);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(String(error)));
      await page.goto(`/${locale}/`);
      await expect(page.getByRole("heading", { level: 1, name: msg(locale, "teaching.prompt") })).toBeVisible();
      await page.locator("a.choice-card", { hasText: msg(locale, "teaching.en") }).click();
      await expect(page).toHaveURL(new RegExp(`/${locale}/programmes\\?teachingLanguage=en`));
      await waitForProgrammeResults(page, locale);
      await expect(page.locator("article.result-card").first()).toBeVisible();
      await assertNoHorizontalOverflow(page);
      expect(errors, errors.join("\n")).toEqual([]);
    });
  }

  test(`programme detail keeps locale (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto(`/${locale}/programmes?teachingLanguage=en`);
    await waitForProgrammeResults(page, locale);
    const title = page.locator("article.result-card h3 a").first();
    const name = (await title.innerText()).trim();
    await title.click();
    await expect(page).toHaveURL(new RegExp(`/${locale}/programmes/`));
    await expect(page.getByRole("heading", { level: 1 })).toContainText(name);
  });

  test(`empty result and clear filters (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.phone);
    await page.goto(`/${locale}/research-jobs?q=zzz-no-such-job-e2e`);
    await expect(page.getByRole("heading", { name: msg(locale, "empty.title") })).toBeVisible();
    await expect(page.getByText(msg(locale, "jobs.empty.help"))).toBeVisible();
    await page.locator(".empty.card").getByRole("button", { name: msg(locale, "filter.clear") }).click();
    await expect(page.locator("article.result-card").first()).toBeVisible();
  });

  test(`localized 404 (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.tablet);
    const response = await page.goto(`/${locale}/programmes/not-a-real-offering-e2e`);
    expect([404, 200]).toContain(response?.status() ?? 0);
    await expect(page.getByRole("heading", { name: msg(locale, "error.notFound") })).toBeVisible();
    await expect(page.getByText(msg(locale, "error.notFound.help"))).toBeVisible();
  });
}

test("locale switch keeps teaching-language query and does not restore the previous UI locale on back", async ({
  page,
}) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await page.goto("/zh-CN/programmes?teachingLanguage=en");
  await waitForProgrammeResults(page, "zh-CN");
  await page.locator(".tools-desktop").getByRole("link", { name: msg("zh-CN", "locale.en") }).click();
  await expect(page).toHaveURL(/\/en\/programmes\?teachingLanguage=en/);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.goBack();
  await expect(page).not.toHaveURL(/\/zh-CN\//);
});

test("job list and detail stay in the active locale", async ({ page }) => {
  const locale: TestLocale = "cs";
  await page.setViewportSize(VIEWPORTS.desktop);
  await page.goto(`/${locale}/research-jobs`);
  const card = page.locator("article.result-card").first();
  await expect(card).toBeVisible();
  await card.getByRole("link", { name: msg(locale, "action.siteInterpretation") }).click();
  await expect(page).toHaveURL(new RegExp(`/${locale}/research-jobs/`));
  await expect(page.locator("html")).toHaveAttribute("lang", "cs");
});

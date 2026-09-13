import { expect, test } from "@playwright/test";

// Packet 5 OSU batch acceptance (zh + one other locale): a master's-entry lab
// role appears in default results, a postdoc stays in all-tracks, and a
// doctorate-only role is out of the default master's list.
const MASTER_ENTRY = "job-17000-184";
const POSTDOC = "job-17000-177";
const DOC_ONLY = "job-17000-183";

test("OSU records land in the correct tracks (zh-CN)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/zh-CN/research-jobs/?applied=1&masterEligible=1");
  await expect(page.locator("article.result-card").first()).toBeVisible();
  const defaultBody = await page.evaluate(() => document.body.innerHTML);
  expect(defaultBody.includes(MASTER_ENTRY), "master's-entry lab role in default results").toBeTruthy();
  expect(defaultBody.includes(POSTDOC), "postdoc out of default master's results").toBeFalsy();
  expect(defaultBody.includes(DOC_ONLY), "doctorate-only role out of default results").toBeFalsy();

  await page.goto("/zh-CN/research-jobs/?applied=1&track=postdoc");
  await expect(page.locator("article.result-card").first()).toBeVisible();
  const postdocBody = await page.evaluate(() => document.body.innerHTML);
  expect(postdocBody.includes(POSTDOC), "postdoc visible in postdoc track").toBeTruthy();

  await page.goto(`/zh-CN/research-jobs/${MASTER_ENTRY}`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("血液肿瘤学");
  await expect(page.locator("main").getByRole("link", { name: /www\.osu\.cz/ }).first()).toBeVisible();
});

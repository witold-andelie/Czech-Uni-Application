import { expect, test } from "@playwright/test";
import { msg } from "./helpers";

// These OSU records were previously public, but the latest official-source
// check marked their evidence as changed. They may only return after a new
// human review, so the public site must not silently retain the old versions.
const REVIEW_INVALIDATED_IDS = ["job-17000-184", "job-17000-177", "job-17000-183"];

test("review-invalidated OSU records are removed from public results", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("/zh-CN/research-jobs/?applied=1&track=all");
  await expect(page.locator("article.result-card").first()).toBeVisible();
  const publicBody = await page.evaluate(() => document.body.innerHTML);
  for (const id of REVIEW_INVALIDATED_IDS) {
    expect(publicBody.includes(id), `${id} must not remain in public results`).toBeFalsy();
  }

  for (const id of REVIEW_INVALIDATED_IDS) {
    await page.goto(`/zh-CN/research-jobs/${id}`);
    await expect(page.getByRole("heading", { level: 1, name: msg("zh-CN", "error.notFound") })).toBeVisible();
  }
});

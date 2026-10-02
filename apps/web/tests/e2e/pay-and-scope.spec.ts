import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { LOCALES, msg } from "./helpers";
import type { ResearchJob } from "../../src/lib/types.ts";

// The 2026-09-26 owner decision changed two things the product used to promise:
// the default list no longer drops postdocs, and a vacancy whose announcement
// does not state compensation is published as it stands instead of being
// withheld. Both are claims about the built site, so both are checked here
// against the records the active snapshot actually published - the ids come
// from the published payload, never from a hardcoded example, so this spec
// fails honestly when the publication no longer contains such a position.
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const pointer = JSON.parse(readFileSync(resolve(root, "data/published/current.json"), "utf8")) as {
  snapshotDir: string;
};
const published = JSON.parse(
  readFileSync(resolve(root, "data/published", pointer.snapshotDir, "browse/nine-hei-jobs.json"), "utf8"),
) as { jobs: ResearchJob[]; windows: { ownerId: string; closesAt: string | null }[] };
// The default list hides a record whose window already closed, so the postdoc
// must still be open today (the first one in the file may have expired since
// publication; it did on 2026-10-03).
// In Prague time, as the site judges windows (UTC was still "yesterday" at
// 00:50 Prague on 2026-10-03 and picked a postdoc that had just closed).
const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Prague" }).format(new Date());
// The list walk finds a card through its live-window entityId, so the postdoc
// also needs a window (RoboProX postdocs have none and link straight out).
const ownWindows = (job: ResearchJob) => (published.windows ?? []).filter((window) => window.ownerId === job.id);
const stillOpen = (job: ResearchJob) =>
  ownWindows(job).length > 0 &&
  ownWindows(job).every((window) => !window.closesAt || window.closesAt.slice(0, 10) >= today);

const unstated = published.jobs.find(
  (job) =>
    job.paidStatus === "unconfirmed" &&
    job.lifecycleStatus !== "closed" &&
    job.lifecycleStatus !== "expired" &&
    job.salary.basisFte == null &&
    job.employmentFte == null &&
    job.employmentStartsAt == null,
);
const postdoc = published.jobs.find(
  (job) =>
    (job.isPostdoc || job.track === "postdoc") &&
    job.visibility === "public" &&
    job.lifecycleStatus !== "closed" &&
    job.lifecycleStatus !== "expired" &&
    stillOpen(job),
);
const PAGE_SIZE = 20;
// An upper bound only: the list also hides records whose window already closed,
// so the walk below stops at the first page without cards rather than trust this.
const MAX_PAGES = Math.ceil(published.jobs.length / PAGE_SIZE) + 1;

/**
 * Walk the paged job list and report whether a record id appears anywhere in it.
 *
 * The ids surface in the rendered markup through each card's live-window
 * `entityId`, which is how the other publication specs pin public lists too.
 */
async function listedOnSomePage(page: Page, urlFor: (pageNumber: number) => string, id: string): Promise<boolean> {
  for (let pageNumber = 1; pageNumber <= MAX_PAGES; pageNumber += 1) {
    await page.goto(urlFor(pageNumber));
    const cards = page.locator("article.result-card");
    if ((await cards.count()) === 0) break; // past the last page, or an empty result set
    if (await page.evaluate((needle) => document.body.innerHTML.includes(needle), id)) return true;
  }
  return false;
}

test.describe("pay state and default job scope (2026-09-26 owner decision)", () => {
  test("the publication still contains both cases this spec needs", () => {
    expect(unstated, "the active snapshot should publish a vacancy that states no compensation").toBeTruthy();
    expect(postdoc, "the active snapshot should publish a postdoc").toBeTruthy();
  });

  for (const locale of LOCALES) {
    test(`a vacancy that states no compensation says so, and shows no amount (${locale})`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(`/${locale}/research-jobs/${unstated!.id}`);

      // The salary panel carries the honest label and no number. The chosen
      // record has no FTE basis, no workload and no start date, so any digit in
      // this panel would be an invented pay figure.
      const panel = page.locator("section.summary-grid div.panel", {
        has: page.getByText(msg(locale, "jobs.salary"), { exact: false }),
      });
      await expect(panel.first()).toBeVisible();
      const body = (await panel.first().innerText()).trim();
      expect(body).toContain(msg(locale, "jobs.payUnstated"));
      expect(body).not.toMatch(/\d/);
      // The confirmed-pay tag must not appear on a record without confirmed pay.
      await expect(page.getByText(msg(locale, "jobs.paidConfirmed"), { exact: true })).toHaveCount(0);
    });

    test(`the default job list still shows a postdoc (${locale})`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      const found = await listedOnSomePage(
        page,
        (pageNumber) => `/${locale}/research-jobs?applied=1&page=${pageNumber}`,
        postdoc!.id,
      );
      expect(found, "a published postdoc must appear in the default list, not be hidden from it").toBe(true);
    });

    test(`the confirmed-pay switch still excludes a vacancy that states no compensation (${locale})`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(`/${locale}/research-jobs?applied=1&paid=1`);
      await expect(page.locator("article.result-card, .empty").first()).toBeVisible();
      const found = await listedOnSomePage(
        page,
        (pageNumber) => `/${locale}/research-jobs?applied=1&paid=1&page=${pageNumber}`,
        unstated!.id,
      );
      expect(found, "the confirmed-pay filter must keep its promise").toBe(false);
    });
  }
});

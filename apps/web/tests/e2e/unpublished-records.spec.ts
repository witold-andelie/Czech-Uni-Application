import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { LOCALES, msg } from "./helpers";

// Safety boundary: a record the active snapshot excludes (not approved) or
// withholds (approved, but no fresh live proof) must not appear in any public
// list, and its detail URL must resolve to the localized not-found page.
// The records come from the active snapshot itself: harvest, review and
// publication now run daily, so fixed example ids (the OSU and UHK specs this
// replaces) became public again after re-review and failed the build.
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const pointer = JSON.parse(readFileSync(resolve(root, "data/published/current.json"), "utf8")) as { snapshotDir: string };
const jobsPayload = JSON.parse(
  readFileSync(resolve(root, "data/published", pointer.snapshotDir, "browse/nine-hei-jobs.json"), "utf8"),
) as { jobs: { id: string }[]; publicationSelection?: { excludedIds?: string[]; withheldIds?: string[] } };
const published = new Set(jobsPayload.jobs.map((job) => job.id));
const selection = jobsPayload.publicationSelection ?? {};
const unpublished = [...(selection.withheldIds ?? []).slice(0, 2), ...(selection.excludedIds ?? []).slice(0, 2)].filter(
  (id) => !published.has(id),
);

for (const locale of LOCALES) {
  test(`excluded and withheld records are not public (${locale})`, async ({ page }) => {
    test.skip(unpublished.length === 0, "the active snapshot excludes and withholds nothing");
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const query of ["applied=1&track=all", "applied=1&funded=1"]) {
      await page.goto(`/${locale}/research-jobs?${query}`);
      await expect(page.locator("article.result-card").first()).toBeVisible();
      const body = await page.evaluate(() => document.body.innerHTML);
      for (const id of unpublished) {
        expect(body.includes(id), `${id} must not appear in public results`).toBeFalsy();
      }
    }
    for (const id of unpublished) {
      await page.goto(`/${locale}/research-jobs/${id}`);
      await expect(page.getByRole("heading", { level: 1, name: msg(locale, "error.notFound") })).toBeVisible();
    }
  });
}

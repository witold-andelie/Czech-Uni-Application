import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  defaultJobFilterQuery,
  filterJobs,
  isFundedDoctoral,
  isMasterEligible,
  jobFilterFromSearch,
  searchFromJobFilter,
} from "./catalog.ts";
import { institutionFromBaseline } from "./mergeBrowseCatalog.ts";
import type { CatalogSnapshot, Institution, ResearchJob } from "./types.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
// A90: exact regression sets run against a dated immutable fixture, never
// against the changing active publication. A new funded position elsewhere
// must not break CI, and an omitted school cannot pass silently either.
const fixture = JSON.parse(
  readFileSync(resolve(root, "data/fixtures/job-search-fixture.json"), "utf8"),
) as {
  institutions: Parameters<typeof institutionFromBaseline>[];
  jobs: ResearchJob[];
  windows: CatalogSnapshot["windows"];
};
const base = JSON.parse(
  readFileSync(resolve(root, "data/fixtures/catalog.json"), "utf8"),
) as CatalogSnapshot;
const now = new Date("2026-09-13T12:00:00Z");

const employers: Institution[] = fixture.institutions.map((item) =>
  institutionFromBaseline(item as never),
);

const catalog: CatalogSnapshot = {
  ...base,
  institutions: [...base.institutions, ...employers],
  jobs: fixture.jobs,
  windows: fixture.windows,
};

function publicIds(query: Partial<ReturnType<typeof defaultJobFilterQuery>>): string[] {
  const merged = defaultJobFilterQuery({ track: "all", masterEligible: false, ...query });
  const result = filterJobs(catalog, merged, now, "en");
  return result.page.map((view) => view.job.id).sort();
}

const CZU_IDS = ["fixture-czu-assistant-a2", "fixture-czu-transfer-t1"].sort();
const MUNI_IDS = [
  "fixture-muni-multidisciplinary-staff",
  "fixture-muni-phd-recetox",
  "fixture-muni-phd-translation",
].sort();
const FUNDED_IDS = ["fixture-muni-phd-recetox", "fixture-muni-phd-translation"].sort();

describe("job search invariants on the dated fixture (A90)", () => {
  it("resolves CZU acronym, diacritic and full names to the same exact set", () => {
    assert.deepEqual(publicIds({ search: "CZU" }), CZU_IDS);
    assert.deepEqual(publicIds({ search: "ČZU" }), CZU_IDS);
    assert.deepEqual(publicIds({ search: "Czech University of Life Sciences Prague" }), CZU_IDS);
    assert.deepEqual(publicIds({ search: "Česká zemědělská univerzita" }), CZU_IDS);
  });

  it("finds MUNI jobs by alias, city token and name", () => {
    assert.deepEqual(publicIds({ search: "MUNI" }), MUNI_IDS);
    assert.deepEqual(publicIds({ search: "Masaryk" }), MUNI_IDS);
    assert.deepEqual(publicIds({ search: "Masaryk University Brno" }), MUNI_IDS);
  });

  it("never lets short aliases substring-match", () => {
    // "MU" is MUNI's alias; "Multidisciplinary" must not become an MU hit.
    const mu = publicIds({ search: "MU" });
    assert.ok(mu.every((id) => id.startsWith("fixture-muni-")));
    // A term that only exists inside unrelated school names returns nothing.
    assert.equal(publicIds({ search: "AMBIS" }).length, 0);
  });

  it("derives funded-doctoral results strictly from structured facts", () => {
    assert.deepEqual(publicIds({ fundedDoctoral: true }), FUNDED_IDS);
    for (const id of FUNDED_IDS) {
      const job = catalog.jobs.find((item) => item.id === id);
      assert.ok(job);
      assert.equal(isFundedDoctoral(job), true);
    }
  });

  it("keeps postdocs and unpaid leads out of funded and default results", () => {
    const funded = publicIds({ fundedDoctoral: true });
    assert.ok(!funded.includes("fixture-cuni-postdoc"));
    assert.ok(!funded.includes("fixture-unpaid-lead"));
    assert.ok(!funded.includes("fixture-muni-multidisciplinary-staff"));
    const master = filterJobs(catalog, defaultJobFilterQuery(), now, "en");
    assert.ok(master.page.every((view) => isMasterEligible(view.job)));
    const masterIds = master.page.map((view) => view.job.id);
    assert.ok(masterIds.includes("fixture-muni-multidisciplinary-staff"));
    assert.ok(!masterIds.includes("fixture-cuni-postdoc"));
    assert.ok(!masterIds.includes("fixture-unpaid-lead"));
  });

  it("round-trips the funded control through the URL query", () => {
    const search = searchFromJobFilter(defaultJobFilterQuery({ fundedDoctoral: true }));
    assert.ok(search.includes("funded=1"));
    assert.equal(jobFilterFromSearch(search).fundedDoctoral, true);
    assert.equal(defaultJobFilterQuery().fundedDoctoral, false);
  });
});

describe("active publication stays consistent with search invariants", () => {
  // A90: live checks validate consistency, not forever-fixed example counts.
  it("CZU alias results only ever contain CZU employers", () => {
    const pointer = JSON.parse(
      readFileSync(resolve(root, "data/published/current.json"), "utf8"),
    ) as { snapshotDir: string };
    const snapshotDir = resolve(root, "data/published", pointer.snapshotDir);
    const jobsPayload = JSON.parse(
      readFileSync(resolve(snapshotDir, "browse/nine-hei-jobs.json"), "utf8"),
    ) as { jobs: ResearchJob[]; windows: CatalogSnapshot["windows"] };
    const baseline = JSON.parse(
      readFileSync(resolve(snapshotDir, "msmt-hei-baseline.json"), "utf8"),
    ) as { institutions: Parameters<typeof institutionFromBaseline>[0][] };
    const employersLive: Institution[] = [];
    for (const job of jobsPayload.jobs) {
      if (employersLive.some((item) => item.id === job.employerId)) continue;
      const item = baseline.institutions.find((row) => row.id === job.employerId);
      assert.ok(item, `baseline missing employer ${job.employerId}`);
      employersLive.push(institutionFromBaseline(item));
    }
    const live: CatalogSnapshot = {
      ...base,
      institutions: [...base.institutions, ...employersLive],
      jobs: jobsPayload.jobs,
      windows: jobsPayload.windows,
    };
    const merged = defaultJobFilterQuery({ track: "all", masterEligible: false, search: "CZU" });
    const result = filterJobs(live, merged, now, "en");
    assert.ok(result.page.length >= 1, "CZU alias must find the published CZU jobs");
    assert.ok(result.page.every((view) => view.job.employerId === "msmt-vs_41000"));
  });
});

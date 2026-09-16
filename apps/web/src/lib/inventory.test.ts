import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildBrowseCatalog } from "./buildBrowseCatalog.ts";
import {
  defaultFilterQuery,
  filterJobs,
  filterOfferings,
  findOffering,
  isMasterEligible,
  jobTrackOf,
  uniqueFieldOptions,
} from "./catalog.ts";
import { offeringFieldGroup } from "./iscedFields.ts";
import type { CompactInventory } from "./expandInventory.ts";
import type { AdmissionsTracerSnapshot } from "./loadAdmissionsTracer.ts";
import type { ApplyPortal } from "./loadApplyPortals.ts";
import type { BaselineInstitution } from "./loadBaseline.ts";
import type { HarvestedJobsSnapshot, ReviewedAdmissionsSnapshot } from "./buildBrowseCatalog.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const now = new Date("2026-09-06T12:00:00Z");

function loadBrowse() {
  const compact = JSON.parse(readFileSync(resolve(root, "data/sources/browse/nine-hei-inventory.json"), "utf8")) as CompactInventory;
  const baseline = JSON.parse(readFileSync(resolve(root, "data/sources/msmt-hei-baseline.json"), "utf8")) as { institutions: BaselineInstitution[] };
  const portals = JSON.parse(readFileSync(resolve(root, "data/sources/admissions/apply-portals.json"), "utf8")) as { institutions: ApplyPortal[] };
  const cuni = JSON.parse(readFileSync(resolve(root, "data/sources/admissions/cuni-mff-cs-tracer.json"), "utf8")) as AdmissionsTracerSnapshot;
  const muni = JSON.parse(readFileSync(resolve(root, "data/sources/admissions/muni-fi-tracer.json"), "utf8")) as AdmissionsTracerSnapshot;
  const jobs = JSON.parse(readFileSync(resolve(root, "data/sources/browse/nine-hei-jobs.json"), "utf8")) as HarvestedJobsSnapshot;
  const reviewedPath = resolve(root, "data/sources/admissions/reviewed-offerings.json");
  const reviewed = existsSync(reviewedPath)
    ? (JSON.parse(readFileSync(reviewedPath, "utf8")) as ReviewedAdmissionsSnapshot)
    : { generatedAt: "", offerings: [], windows: [], evidence: [] };
  return buildBrowseCatalog({
    compact,
    tracers: [cuni, muni],
    jobs,
    baseline: baseline.institutions,
    portals: portals.institutions,
    reviewed,
  });
}

describe("nine-HEI register inventory browse", () => {
  const browse = loadBrowse();

  it("replaces fixture programmes with register inventory and keeps tracers", () => {
    assert.equal(browse.catalogKind, "browse_with_inventory");
    assert.equal(browse.dataClass, "official_register_extract");
    assert.ok(browse.offerings.length > 2000);
    assert.equal(browse.offerings.some((item) => item.id === "off-law-cs-2026"), false);
    assert.equal(browse.offerings.some((item) => item.title["zh-CN"].includes("[样例]")), false);
    assert.ok(browse.offerings.some((item) => item.title.en === "Addiction: Specialization in Health Care"));
    assert.ok(findOffering(browse, "cuni-mff-cs-en-2026", now));
    assert.ok(findOffering(browse, "muni-fi-vi-en-2026", now));
    assert.equal(browse.offeringAliases?.["cuni-mff-cs-en-2026"]?.startsWith("inv-"), true);
    const pointer = JSON.parse(readFileSync(resolve(root, "data/published/current.json"), "utf8")) as {
      snapshotDir: string;
    };
    const currentManifest = resolve(root, "data/published", pointer.snapshotDir, "manifest.json");
    assert.equal(existsSync(currentManifest), true);
  });

  it("overlays matching register rows so Computer Science is the tracer, not a duplicate", () => {
    const matches = browse.offerings.filter(
      (item) =>
        item.institutionId === "msmt-vs_11000" &&
        item.degree === "bachelor" &&
        item.teachingLanguages[0] === "en" &&
        item.title.en === "Computer Science",
    );
    assert.equal(matches.length, 1);
    assert.match(matches[0].id, /^inv-/);
    assert.equal(browse.offeringAliases?.["cuni-mff-cs-en-2026"], matches[0].id);
    assert.equal(matches[0].dataClass, "official_admissions_extract");
    assert.equal(matches[0].tuition.published, true);
    assert.equal(findOffering(browse, "cuni-mff-cs-en-2026", now)?.offering.id, matches[0].id);
  });

  it("does not invent tuition or open windows on inventory rows", () => {
    const inventory = browse.offerings.filter((item) => item.dataClass === "official_register_extract");
    assert.ok(inventory.length > 1000);
    assert.ok(inventory.every((item) => item.tuition.published === false));
    assert.ok(inventory.every((item) => item.tuition.amount == null));
    assert.ok(inventory.every((item) => item.academicYear === "register"));
    const inventoryIds = new Set(inventory.map((item) => item.id));
    const inventoryWindows = browse.windows.filter((item) => item.ownerType === "offering" && inventoryIds.has(item.ownerId));
    assert.equal(inventoryWindows.length, 0);
    const evidenceIds = new Set(browse.evidence.map((item) => item.id));
    for (const window of browse.windows.filter((item) => item.ownerType === "offering")) {
      assert.ok(evidenceIds.has(window.sourceEvidenceId), window.sourceEvidenceId);
    }
    assert.ok(inventory.every((item) => item.verifiedAt == null));
  });

  it("overlays the reviewed CZU admissions slice on stable inventory ids", () => {
    const bachelor = findOffering(browse, "inv-898e810ed190", now);
    const master = findOffering(browse, "inv-ac1fecbdfc9c", now);
    const gis = findOffering(browse, "inv-c50825f0199c", now);
    const doctoral = findOffering(browse, "inv-330bf56297af", now);
    assert.ok(bachelor && master && gis && doctoral);
    assert.equal(bachelor.offering.dataClass, "official_admissions_extract");
    assert.equal(bachelor.offering.title["zh-CN"], "信息学");
    assert.equal(bachelor.offering.applicationTargetKind, "general_portal");
    assert.equal(bachelor.offering.applicationUrl, null);
    assert.equal(bachelor.offering.tuition.published, true);
    assert.deepEqual((bachelor.offering.tuition.variants ?? []).map((item) => item.amount).sort((a, b) => a - b), [500, 3200]);
    assert.equal(bachelor.windows.length, 1);
    assert.equal(bachelor.windows[0].opensAt, "2026-09-15");
    assert.equal(gis.offering.teachingLanguages[0], "cs");
    assert.equal(gis.offering.tuition.published, false);
    assert.equal(doctoral.offering.degree, "doctorate");
    assert.equal(doctoral.offering.academicYear, "2026/2027");
    assert.equal(doctoral.windows.length, 2);
    assert.ok(doctoral.windows.every((item) => item.status === "closed"));
    assert.equal(findOffering(browse, "czu-study-507", now)?.offering.id, "inv-898e810ed190");
  });

  it("covers all CSCSE-listed HEIs and maps Olomouc, Ostrava, Pilsen and Liberec", () => {
    const ids = new Set(browse.institutions.map((item) => item.id));
    for (const id of [
      "msmt-vs_11000",
      "msmt-vs_12000",
      "msmt-vs_14000",
      "msmt-vs_15000",
      "msmt-vs_17000",
      "msmt-vs_19000",
      "msmt-vs_21000",
      "msmt-vs_22000",
      "msmt-vs_23000",
      "msmt-vs_24000",
      "msmt-vs_25000",
      "msmt-vs_26000",
      "msmt-vs_27000",
      "msmt-vs_31000",
      "msmt-vs_41000",
      "msmt-vs_43000",
      "msmt-vs_51000",
      "msmt-vs_54000",
      "msmt-vs_61000",
      "msmt-vs_6d000",
      "msmt-vs_75000",
      "msmt-vs_7p000",
      "msmt-vs_7s000",
      "msmt-vs_7u000",
    ]) {
      assert.ok(ids.has(id), id);
    }
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_15000")?.city.en, "Olomouc");
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_17000")?.city.en, "Ostrava");
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_27000")?.city.en, "Ostrava");
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_23000")?.city.en, "Pilsen");
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_24000")?.city.en, "Liberec");
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_11000")?.displayName["zh-CN"], "查理大学");
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_43000")?.displayName["zh-CN"], "布尔诺孟德尔大学");
    assert.ok(browse.offerings.some((item) => item.institutionId === "msmt-vs_27000"));
    assert.ok(browse.offerings.some((item) => item.institutionId === "msmt-vs_43000"));
  });

  it("covers remaining register HEIs without treating them as CSCSE-listed", () => {
    for (const id of ["msmt-vs_18000", "msmt-vs_13000", "msmt-vs_28000", "msmt-vs_52000", "msmt-vs_16000", "msmt-vs_94000"]) {
      assert.ok(browse.institutions.some((item) => item.id === id), id);
      assert.ok(browse.offerings.some((item) => item.institutionId === id), id);
      const rec = browse.institutions.find((item) => item.id === id)?.cscseReference;
      assert.equal(rec?.lookupStatus, "unverified");
      assert.equal(rec?.operatorListStatus, "absent");
      assert.notEqual(rec?.lookupStatus, "listed");
    }
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_18000")?.city.en, "Hradec Králové");
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_13000")?.city.en, "Ústí nad Labem");
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_28000")?.city.en, "Zlín");
    assert.equal(browse.institutions.find((item) => item.id === "msmt-vs_52000")?.city.en, "Prague");
  });

  it("finds Czech titles when the query omits diacritics", () => {
    const marked = filterOfferings(browse, {
      teachingLanguage: "cs",
      includeJointRequired: false,
      search: "Přírodovědecká",
      degree: "all",
      city: "all",
      institutionId: "all",
      ownership: "all",
      listedOnly: false,
      status: "all",
      orientation: "all",
      sort: "default",
      page: 1,
      pageSize: 20,
    }, now, "cs");
    const folded = filterOfferings(browse, {
      teachingLanguage: "cs",
      includeJointRequired: false,
      search: "Prirodovedecka",
      degree: "all",
      city: "all",
      institutionId: "all",
      ownership: "all",
      listedOnly: false,
      status: "all",
      orientation: "all",
      sort: "default",
      page: 1,
      pageSize: 20,
    }, now, "cs");
    assert.ok(marked.total > 0);
    assert.equal(folded.total, marked.total);
  });

  it("lets Chinese, English and Czech search find real Charles and Masaryk programmes", () => {
    const english = filterOfferings(browse, {
      teachingLanguage: "en",
      includeJointRequired: false,
      search: "查理大学",
      degree: "all",
      city: "all",
      institutionId: "all",
      ownership: "all",
      listedOnly: false,
      status: "all",
      orientation: "all",
      sort: "default",
      page: 1,
      pageSize: 20,
    }, now, "zh-CN");
    assert.ok(english.total > 20);
    assert.ok(english.page.every((item) => item.institution.id === "msmt-vs_11000"));
    const czech = filterOfferings(browse, {
      teachingLanguage: "cs",
      includeJointRequired: false,
      search: "Informatika",
      degree: "bachelor",
      city: "all",
      institutionId: "msmt-vs_11000",
      ownership: "all",
      listedOnly: false,
      status: "all",
      orientation: "all",
      sort: "default",
      page: 1,
      pageSize: 20,
    }, now, "cs");
    assert.ok(czech.total > 0);
    assert.ok(czech.page.some((item) => item.offering.title.cs.includes("Informatika")));
    assert.ok(findOffering(browse, "cuni-mff-cs-cs-2026", now));
    const listSrc = readFileSync(resolve(root, "apps/web/src/components/ProgrammeResults.svelte"), "utf8");
    assert.equal(listSrc.includes('from "../lib/loadCatalog"'), false);
    assert.match(listSrc, /fetchInventoryCatalog/);
    assert.match(listSrc, /uniqueFieldOptions/);
    assert.match(listSrc, /pagination\.pageOf/);
    assert.equal(listSrc.includes('type="search"'), false);
    assert.equal(listSrc.includes('value="state"'), false);
    assert.match(listSrc, /officialOfferingHref/);
  });

  it("filters English programmes by ISCED-F broad field", () => {
    const fields = uniqueFieldOptions(browse, "zh-CN");
    assert.ok(fields.some((item) => item.value === "06" && item.label === "计算机与信息通信"));
    const ict = filterOfferings(
      browse,
      defaultFilterQuery({ teachingLanguage: "en", field: "06" }),
      now,
      "zh-CN",
    );
    assert.ok(ict.total > 0);
    assert.ok(ict.page.every((item) => offeringFieldGroup(item.offering) === "06"));
  });

  it("keeps doctoral research-study programmes in the inventory", () => {
    const doctorates = browse.offerings.filter((item) => item.degree === "doctorate");
    assert.ok(doctorates.length > 200);
    const result = filterOfferings(browse, {
      teachingLanguage: "all",
      includeJointRequired: false,
      search: "",
      degree: "doctorate",
      city: "all",
      institutionId: "msmt-vs_14000",
      ownership: "all",
      listedOnly: false,
      status: "all",
      orientation: "all",
      sort: "default",
      page: 1,
      pageSize: 20,
    }, now, "en");
    assert.ok(result.total > 0);
    assert.ok(result.page.every((item) => item.offering.degree === "doctorate"));
  });
});

describe("nine-HEI official career jobs", () => {
  const browse = loadBrowse();

  it("stores assistant, post-master and postdoc tracks without putting postdocs in the default master’s list", () => {
    assert.ok(browse.jobs.length > 0);
    const tracks = new Set(browse.jobs.map((job) => jobTrackOf(job)));
    assert.ok(tracks.has("assistant"));
    assert.ok(tracks.has("post_master"));
    assert.ok(tracks.has("postdoc"));
    const masters = filterJobs(browse, {
      masterEligible: true,
      track: "master_eligible",
      doctoralEnrollment: "all",
      workingLanguage: "all",
      fundedDoctoral: false,
      search: "",
      page: 1,
      pageSize: 20,
    }, now, "en");
    assert.ok(masters.page.every((item) => isMasterEligible(item.job)));
    assert.ok(masters.page.every((item) => item.job.isPostdoc === false));
    const postdocs = filterJobs(browse, {
      masterEligible: false,
      track: "postdoc",
      doctoralEnrollment: "all",
      workingLanguage: "all",
      fundedDoctoral: false,
      search: "",
      page: 1,
      pageSize: 20,
    }, now, "en");
    assert.ok(postdocs.total > 0);
    assert.ok(postdocs.page.every((item) => item.job.isPostdoc));
  });

  it("keeps a source-rechecked expired job closed even with an earlier fixture clock", () => {
    const mff = browse.jobs.find((item) => item.id === "job-cuni-mff-research-fellow-ucjf");
    if (!mff) return;
    const window = browse.windows.find((item) => item.ownerId === mff.id);
    assert.ok(window);
    assert.equal(window.opensAt, null);
    assert.ok(window.closesAt);
    assert.equal(window.datePrecision, "date");
    assert.equal(mff.lifecycleStatus, "expired");
    assert.equal(window.status, "closed");
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  evaluateWindow,
  filterJobs,
  filterOfferings,
  findJob,
  isMasterEligible,
  isPublicJob,
  matchesTeachingLanguage,
  summarizeWindows,
} from "./catalog.ts";
import type { ApplicationWindow, CatalogSnapshot, Offering } from "./types.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const catalog = JSON.parse(readFileSync(resolve(root, "data/fixtures/catalog.json"), "utf8")) as CatalogSnapshot;
const now = new Date("2026-09-06T12:00:00Z");

function offering(id: string): Offering {
  const found = catalog.offerings.find((item) => item.id === id);
  assert.ok(found);
  return found;
}

function windowsFor(ownerType: ApplicationWindow["ownerType"], ownerId: string): ApplicationWindow[] {
  return catalog.windows.filter((item) => item.ownerType === ownerType && item.ownerId === ownerId);
}

describe("teaching language filter", () => {
  it("does not run a language-limited query while unset", () => {
    const result = filterOfferings(catalog, {
      teachingLanguage: null,
      includeJointRequired: false,
      search: "",
      degree: "all",
      city: "all",
      ownership: "all",
      listedOnly: false,
      status: "all",
      orientation: "all",
      sort: "default",
      page: 1,
      pageSize: 20,
    }, now, "zh-CN");
    assert.equal(result.needsChoice, true);
    assert.equal(result.total, 0);
  });

  it("keeps English-only results free of joint-required programmes", () => {
    const english = catalog.offerings.filter((item) => matchesTeachingLanguage(item, "en", false));
    assert.ok(english.some((item) => item.id === "off-cs-en-2026"));
    assert.ok(english.some((item) => item.id === "off-med-en-clinical"));
    assert.ok(!english.some((item) => item.id === "off-joint-2026"));
    assert.ok(!english.some((item) => item.id === "off-law-cs-2026"));
  });

  it("adds joint-required programmes only when the checkbox is explicit", () => {
    const withJoint = catalog.offerings.filter((item) => matchesTeachingLanguage(item, "en", true));
    assert.ok(withJoint.some((item) => item.id === "off-joint-2026"));
  });

  it("keeps an English-taught programme that still requires Czech for clinics", () => {
    const med = offering("off-med-en-clinical");
    assert.equal(matchesTeachingLanguage(med, "en", false), true);
    assert.equal(med.additionalLanguageRequirements[0]?.language, "cs");
    assert.equal(med.additionalLanguageRequirements[0]?.context, "clinical");
  });
});

describe("application windows", () => {
  it("does not take a whole offering down when round 1 is closed and round 2 is open", () => {
    const summary = summarizeWindows(windowsFor("offering", "off-cs-en-2026"), now);
    assert.equal(summary.opportunityStatus, "open");
    assert.equal(summary.current[0]?.id, "win-cs-r2");
    assert.ok(summary.closed.some((item) => item.id === "win-cs-r1"));
  });

  it("does not treat a missing start date as open the way the guanfu snapshot did", () => {
    const rolling = catalog.windows.find((item) => item.id === "win-nursing-rolling");
    assert.ok(rolling);
    assert.equal(evaluateWindow(rolling, now), "unknown");
  });

  it("keeps a vacancy-conditional supplementary round from looking unconditionally open", () => {
    const supplementary = catalog.windows.find((item) => item.id === "win-biz-supp");
    assert.ok(supplementary);
    assert.equal(evaluateWindow(supplementary, now), "conditional");
  });

  it("labels a future confirmed round as not yet started and keeps the offering visible", () => {
    const summary = summarizeWindows(windowsFor("offering", "off-law-cs-upcoming"), now);
    assert.equal(summary.opportunityStatus, "upcoming");
  });

  it("lets a whole-job closure win over a future round", () => {
    const job = catalog.jobs.find((item) => item.id === "job-filled");
    assert.ok(job);
    const summary = summarizeWindows(windowsFor("research_job", job.id), now, job.wholeOpportunityClosed);
    assert.equal(summary.opportunityStatus, "closed");
    assert.equal(isPublicJob(job, summary), false);
  });
});

describe("research jobs", () => {
  it("excludes postdocs and closed jobs from default master’s results", () => {
    const result = filterJobs(catalog, {
      masterEligible: true,
      doctoralEnrollment: "all",
      workingLanguage: "all",
      search: "",
      page: 1,
      pageSize: 20,
    }, now, "en");
    const ids = result.page.map((item) => item.job.id);
    assert.ok(ids.includes("job-master-paid"));
    assert.ok(!ids.includes("job-postdoc"));
    assert.ok(!ids.includes("job-closed"));
    assert.ok(!ids.includes("job-filled"));
  });

  it("does not treat unspecified doctoral enrollment as not required", () => {
    const job = catalog.jobs.find((item) => item.id === "job-unspecified");
    assert.ok(job);
    assert.equal(job.doctoralEnrollment, "unspecified");
    assert.equal(isMasterEligible(job), true);
  });

  it("keeps a closed job retrievable for old shortlist views", () => {
    const view = findJob(catalog, "job-closed", now);
    assert.ok(view);
    assert.equal(view.summary.opportunityStatus, "closed");
  });
});

describe("recognition and tuition", () => {
  it("does not infer CSCSE listed from public ownership", () => {
    const pub = catalog.institutions.find((item) => item.id === "inst-public-prague");
    assert.ok(pub);
    assert.equal(pub.ownership, "public");
    assert.equal(pub.cscseReference.lookupStatus, "unverified");
  });

  it("keeps an official notice beside a listed fixture tag", () => {
    const listed = catalog.institutions.find((item) => item.id === "inst-listed-notice");
    assert.ok(listed);
    assert.equal(listed.cscseReference.lookupStatus, "listed");
    assert.equal(listed.cscseReference.notices[0]?.active, true);
  });

  it("does not store unpublished tuition as zero", () => {
    const unknown = offering("off-cs-en-2026").tuition;
    assert.equal(unknown.published, false);
    assert.equal(unknown.amount, null);
    const free = offering("off-law-cs-2026").tuition;
    assert.equal(free.published, true);
    assert.equal(free.amount, 0);
  });
});

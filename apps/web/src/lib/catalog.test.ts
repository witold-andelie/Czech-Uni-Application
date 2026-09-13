import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  canApply,
  evaluateWindow,
  filterJobs,
  filterOfferings,
  filterQueryFromSearch,
  findJob,
  isMasterEligible,
  isPublicJob,
  jobFilterFromSearch,
  matchesTeachingLanguage,
  officialJobHref,
  officialOfferingHref,
  primaryApplicationUrl,
  programmesBackHref,
  searchFromFilter,
  searchFromJobFilter,
  summarizeWindows,
  windowCanApply,
} from "./catalog.ts";
import type { ApplicationWindow, CatalogSnapshot, Offering } from "./types.ts";
import { institutionFromBaseline, mergeBrowseCatalog } from "./mergeBrowseCatalog.ts";


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

  it("never infers open from a missing start even if stored status is open", () => {
    const window = catalog.windows.find((item) => item.id === "win-nursing-rolling");
    assert.ok(window);
    assert.equal(evaluateWindow({ ...window, status: "open" }, now), "unknown");
  });

  it("keeps a vacancy-conditional supplementary round from looking unconditionally open", () => {
    const supplementary = catalog.windows.find((item) => item.id === "win-biz-supp");
    assert.ok(supplementary);
    assert.equal(evaluateWindow(supplementary, now), "conditional");
    const summary = summarizeWindows(windowsFor("offering", "off-biz-en-supp"), now);
    assert.equal(summary.opportunityStatus, "conditional");
  });

  it("uses the clock for datetime precision instead of the whole calendar day", () => {
    const window: ApplicationWindow = {
      id: "win-dt",
      ownerType: "offering",
      ownerId: "x",
      academicYear: "2026/2027",
      roundNumber: 1,
      roundLabelOriginal: null,
      roundType: "regular",
      applicantScope: null,
      opensAt: "2026-09-01T00:00:00+02:00",
      closesAt: "2026-09-06T10:00:00+02:00",
      timezone: "Europe/Prague",
      datePrecision: "datetime",
      status: "open",
      conditionalOnVacancies: false,
      applicationUrl: null,
      sourceEvidenceId: "ev",
    };
    assert.equal(evaluateWindow(window, now), "closed");
    assert.equal(evaluateWindow({ ...window, status: "closed" }, new Date("2026-09-05T12:00:00Z")), "closed");
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

  it("treats an explicit closed status as closed even without a start date", () => {
    const window: ApplicationWindow = {
      id: "win-closed-early",
      ownerType: "research_job",
      ownerId: "x",
      academicYear: null,
      roundNumber: null,
      roundLabelOriginal: null,
      roundType: "regular",
      applicantScope: null,
      opensAt: null,
      closesAt: "2026-09-30",
      timezone: "Europe/Prague",
      datePrecision: "date",
      status: "closed",
      conditionalOnVacancies: false,
      applicationUrl: "https://example.cz/apply",
      sourceEvidenceId: "ev",
    };
    assert.equal(evaluateWindow(window, now), "closed");
    const upcoming: ApplicationWindow = { ...window, id: "win-closed-future", opensAt: "2026-10-01" };
    assert.equal(evaluateWindow(upcoming, now), "closed");
    assert.equal(windowCanApply(window, now, false), false);
    assert.equal(windowCanApply({ ...window, status: "open", opensAt: "2026-09-01" }, now, true), false);
  });

  it("interprets offset-less datetimes in the record timezone, not the visitor zone", () => {
    const window: ApplicationWindow = {
      id: "win-prague-dt",
      ownerType: "research_job",
      ownerId: "x",
      academicYear: null,
      roundNumber: null,
      roundLabelOriginal: null,
      roundType: "regular",
      applicantScope: null,
      opensAt: "2026-09-01T00:00:00",
      closesAt: "2026-09-07T14:00:00",
      timezone: "Europe/Prague",
      datePrecision: "datetime",
      status: "open",
      conditionalOnVacancies: false,
      applicationUrl: null,
      sourceEvidenceId: "ev",
    };
    assert.equal(evaluateWindow(window, new Date("2026-09-07T13:00:00Z")), "closed");
  });
});

describe("research jobs", () => {
  it("excludes postdocs and closed jobs from default master’s results", () => {
    const result = filterJobs(catalog, {
      masterEligible: true,
      doctoralEnrollment: "all",
      workingLanguage: "all",
      fundedDoctoral: false,
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

  it("keeps a closed job retrievable through its tombstone detail page", () => {
    const view = findJob(catalog, "job-closed", now);
    assert.ok(view);
    assert.equal(view.summary.opportunityStatus, "closed");
  });

  it("pages public jobs instead of dropping everything after the first page", () => {
    const first = filterJobs(catalog, {
      masterEligible: true,
      doctoralEnrollment: "all",
      workingLanguage: "all",
      fundedDoctoral: false,
      search: "",
      page: 1,
      pageSize: 1,
    }, now, "en");
    const second = filterJobs(catalog, {
      masterEligible: true,
      doctoralEnrollment: "all",
      workingLanguage: "all",
      fundedDoctoral: false,
      search: "",
      page: 2,
      pageSize: 1,
    }, now, "en");
    assert.ok(first.total > 1);
    assert.equal(first.page.length, 1);
    assert.equal(second.page.length, 1);
    assert.notEqual(first.page[0].job.id, second.page[0].job.id);
    assert.equal(jobFilterFromSearch("?applied=1&page=2").page, 2);
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

  it("keeps baseline CSCSE notices when converting register identity", () => {
    const baseline = JSON.parse(readFileSync(resolve(root, "data/sources/msmt-hei-baseline.json"), "utf8")) as {
      institutions: Parameters<typeof mergeBrowseCatalog>[2];
    };
    const withNotice = structuredClone(baseline.institutions[0]);
    withNotice.cscseReference = {
      ...(withNotice.cscseReference ?? {
        lookupStatus: "listed",
        listedNameZh: null,
        listedNameEn: null,
        officialMatchedName: null,
        lookupUrl: "http://yxcx.cscse.edu.cn/rzyxmd",
        checkedAt: "2026-09-06",
        sourceVersion: "test",
        reviewer: "operator",
        matchConfidence: "exact",
      }),
      notices: [{ text: { "zh-CN": "风险公告", en: "risk notice", cs: "upozornění" }, active: true }],
    };
    const row = institutionFromBaseline(withNotice);
    assert.equal(row.cscseReference.notices.length, 1);
    assert.equal(row.cscseReference.notices[0]?.active, true);
    assert.equal(row.cscseReference.notices[0]?.text.en, "risk notice");
  });

  it("filters Czech offerings in Prague by the English city id", () => {
    const result = filterOfferings(catalog, {
      teachingLanguage: "cs",
      includeJointRequired: false,
      search: "",
      degree: "all",
      city: "Prague",
      ownership: "all",
      listedOnly: false,
      status: "all",
      orientation: "all",
      sort: "default",
      page: 1,
      pageSize: 20,
    }, now, "cs");
    assert.equal(result.total, 2);
    assert.ok(result.page.every((item) => item.institution.city.en === "Prague"));
  });

  it("round-trips programme and job filters through the query string", () => {
    const programme = filterQueryFromSearch("?teachingLanguage=en&degree=bachelor&listedOnly=1&page=2");
    assert.equal(searchFromFilter(programme), "?teachingLanguage=en&degree=bachelor&listedOnly=1&page=2");
    assert.equal(searchFromFilter(filterQueryFromSearch("?teachingLanguage=cs")), "?teachingLanguage=cs");
    const jobs = jobFilterFromSearch("?applied=1&masterEligible=1&phd=required&page=2");
    assert.equal(searchFromJobFilter(jobs), "?applied=1&masterEligible=1&phd=required&page=2");
    assert.equal(searchFromJobFilter(jobFilterFromSearch("?applied=1")), "?applied=1");
  });

  it("keeps the programme list page from inlining the catalogue as HTML props", () => {
    const src = readFileSync(resolve(root, "apps/web/src/pages/[locale]/programmes/index.astro"), "utf8");
    assert.match(src, /client:load/);
    assert.match(src, /ssr-teaching-chooser/);
    assert.equal(src.includes("catalog={catalog}"), false);
  });

  it("sends programme detail back to the matching teaching-language list", () => {
    assert.equal(programmesBackHref("zh-CN", offering("off-cs-en-2026")), "/zh-CN/programmes?teachingLanguage=en");
    assert.equal(programmesBackHref("cs", offering("off-law-cs-2026")), "/cs/programmes?teachingLanguage=cs");
    assert.equal(programmesBackHref("en", offering("off-joint-2026")), "/en/programmes?teachingLanguage=all&includeJoint=1");
  });

  it("keeps the 404 page on the site layout with a single heading", () => {
    const src = readFileSync(resolve(root, "apps/web/src/pages/404.astro"), "utf8");
    assert.match(src, /BaseLayout/);
    assert.match(src, /NotFoundView/);
    assert.equal((src.match(/<h1/g) ?? []).length, 0);
  });

  it("does not store unpublished tuition as zero", () => {
    const unknown = offering("off-cs-en-2026").tuition;
    assert.equal(unknown.published, false);
    assert.equal(unknown.amount, null);
    const free = offering("off-law-cs-2026").tuition;
    assert.equal(free.published, true);
    assert.equal(free.amount, 0);
  });

  it("keeps an official page link on listings that are not currently applyable", () => {
    const item = offering("off-cs-en-2026");
    const institution = catalog.institutions.find((row) => row.id === item.institutionId);
    assert.ok(institution);
    assert.equal(officialOfferingHref(item, institution), item.applicationUrl);
    assert.equal(
      officialOfferingHref({ ...item, applicationUrl: null }, institution, {
        admissionsUrl: "https://www.aauni.edu/admissions/",
        admissionsUrlEn: "https://www.aauni.edu/admissions/",
      }),
      "https://www.aauni.edu/admissions/",
    );
    const closed = findJob(catalog, "job-closed", now);
    assert.ok(closed);
    assert.equal(canApply(closed.summary), false);
    assert.equal(primaryApplicationUrl(closed.summary, closed.job.applicationUrl), null);
    assert.equal(officialJobHref(closed.job), closed.job.applicationUrl || closed.job.sourceUrl);
    const listSrc = readFileSync(resolve(root, "apps/web/src/components/ProgrammeResults.svelte"), "utf8");
    const jobSrc = readFileSync(resolve(root, "apps/web/src/components/JobResults.svelte"), "utf8");
    const linkSrc = readFileSync(resolve(root, "apps/web/src/components/OfficialLink.svelte"), "utf8");
    assert.match(listSrc, /officialOfferingHref/);
    assert.match(listSrc, /OfficialLink/);
    assert.match(jobSrc, /officialJobHref/);
    assert.match(jobSrc, /OfficialLink/);
    assert.match(linkSrc, /action\.officialLink/);
  });
});

describe("Charles University admissions tracer", () => {
  const tracer = JSON.parse(
    readFileSync(resolve(root, "data/sources/admissions/cuni-mff-cs-tracer.json"), "utf8"),
  ) as {
    catalogKind: string;
    dataClass: string;
    institutionId: string;
    offerings: Array<{
      id: string;
      teachingLanguages: string[];
      applicationUrl: string | null;
      tuition: { published: boolean; amount: number | null; variants: { amount: number }[] };
      applicationFee: { isNotTuition: boolean; amount: number | null };
      window: ApplicationWindow;
    }>;
  };
  assert.equal(tracer.institutionId, "msmt-vs_11000");

  it("is a limited admissions extract and stays off the fixture programme list", () => {
    assert.equal(tracer.catalogKind, "tracer_not_published");
    assert.equal(tracer.dataClass, "official_admissions_extract");
    const ids = new Set(catalog.offerings.map((item) => item.id));
    assert.equal(ids.has("cuni-mff-cs-en-2026"), false);
    assert.equal(ids.has("cuni-mff-cs-cs-2026"), false);
    const english = filterOfferings(catalog, {
      teachingLanguage: "en",
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
    }, now, "en");
    assert.equal(english.page.some((item) => item.offering.id.startsWith("cuni-mff")), false);
  });

  it("keeps one English and one Czech offering with real closes and no invented round 1", () => {
    const languages = tracer.offerings.map((item) => item.teachingLanguages[0]).sort();
    assert.deepEqual(languages, ["cs", "en"]);
    for (const item of tracer.offerings) {
      assert.equal(item.window.opensAt, null);
      assert.equal(item.window.roundNumber, null);
      assert.equal(item.window.roundType, "unspecified");
      assert.equal(item.window.datePrecision, "date");
      assert.equal(item.window.timezone, "Europe/Prague");
      assert.ok(item.window.closesAt);
      assert.match(item.window.closesAt, /^2026-/);
    }
  });

  it("does not auto-open a missing start, even before the English close date", () => {
    const en = tracer.offerings.find((item) => item.id === "cuni-mff-cs-en-2026");
    assert.ok(en);
    const window = en.window;
    const beforeClose = new Date("2026-04-01T12:00:00Z");
    assert.equal(evaluateWindow({ ...window, status: "open" }, beforeClose), "unknown");
    assert.equal(evaluateWindow(window, now), "closed");
    const summary = summarizeWindows([window], now);
    assert.equal(canApply(summary), false);
    assert.equal(primaryApplicationUrl(summary, en.applicationUrl), null);
  });

  it("stores dual English tuition as variants and leaves Czech tuition unpublished", () => {
    const en = tracer.offerings.find((item) => item.id === "cuni-mff-cs-en-2026");
    const cs = tracer.offerings.find((item) => item.id === "cuni-mff-cs-cs-2026");
    assert.ok(en);
    assert.ok(cs);
    assert.equal(en.tuition.published, true);
    assert.equal(en.tuition.amount, null);
    assert.deepEqual(en.tuition.variants.map((item) => item.amount).sort((a, b) => a - b), [4200, 7100]);
    assert.equal(cs.tuition.published, false);
    assert.equal(cs.tuition.amount, null);
    assert.equal(cs.applicationFee.isNotTuition, true);
    assert.notEqual(cs.applicationFee.amount, 0);
  });
});

describe("browse catalog with admissions tracers", () => {
  const baseline = JSON.parse(readFileSync(resolve(root, "data/sources/msmt-hei-baseline.json"), "utf8")) as {
    institutions: Parameters<typeof mergeBrowseCatalog>[2];
  };
  const cuni = JSON.parse(readFileSync(resolve(root, "data/sources/admissions/cuni-mff-cs-tracer.json"), "utf8"));
  const muni = JSON.parse(readFileSync(resolve(root, "data/sources/admissions/muni-fi-tracer.json"), "utf8"));
  const browse = mergeBrowseCatalog(catalog, [cuni, muni], baseline.institutions);

  it("adds four limited tracer overlays outside the fixture catalogue", () => {
    assert.equal(browse.catalogKind, "browse_with_tracer");
    assert.equal(browse.dataClass, "ui_fixture");
    const ids = browse.offerings.map((item) => item.id);
    assert.ok(ids.includes("cuni-mff-cs-en-2026"));
    assert.ok(ids.includes("cuni-mff-cs-cs-2026"));
    assert.ok(ids.includes("muni-fi-vi-en-2026"));
    assert.ok(ids.includes("muni-fi-inf-cs-2026"));
    const pointer = JSON.parse(readFileSync(resolve(root, "data/published/current.json"), "utf8")) as {
      snapshotDir: string;
    };
    const currentManifest = resolve(root, "data/published", pointer.snapshotDir, "manifest.json");
    assert.equal(existsSync(currentManifest), true);
    const fixtureIds = new Set(catalog.offerings.map((item) => item.id));
    assert.equal(fixtureIds.has("cuni-mff-cs-en-2026"), false);
    assert.equal(fixtureIds.has("muni-fi-vi-en-2026"), false);
  });

  it("keeps Charles and Masaryk register identity on the browse path", () => {
    const charles = browse.institutions.find((item) => item.id === "msmt-vs_11000");
    const masaryk = browse.institutions.find((item) => item.id === "msmt-vs_14000");
    assert.ok(charles);
    assert.ok(masaryk);
    assert.equal(charles.city.en, "Prague");
    assert.equal(masaryk.city.en, "Brno");
    assert.equal(charles.cscseReference.lookupStatus, "unverified");
    assert.equal(masaryk.cscseReference.lookupStatus, "unverified");
    assert.equal(charles.cscseReference.operatorListStatus, "listed");
    assert.equal(masaryk.cscseReference.operatorListStatus, "listed");
    assert.equal(charles.cscseReference.evidenceKind, "operator_supplied_list");
    assert.equal(charles.displayName["zh-CN"], "查理大学");
    assert.equal(masaryk.displayName["zh-CN"], "马萨里克大学");
    assert.equal(charles.displayName.en, "Charles University");
    assert.equal(masaryk.displayName.en, "Masaryk University");
    const en = browse.offerings.find((item) => item.id === "cuni-mff-cs-en-2026");
    assert.ok(en);
    assert.equal(en.tuition.published, true);
    assert.equal(en.tuition.amount, null);
    assert.deepEqual(en.tuition.variants?.map((item) => item.amount).sort((a, b) => a - b), [4200, 7100]);
    assert.equal(en.durationSemesters, 6);
  });

  it("lets English and Czech teaching-language search find the matching tracer tracks", () => {
    const english = filterOfferings(browse, {
      teachingLanguage: "en",
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
    const czech = filterOfferings(browse, {
      teachingLanguage: "cs",
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
    }, now, "cs");
    const enIds = english.page.map((item) => item.offering.id);
    const csIds = czech.page.map((item) => item.offering.id);
    assert.ok(enIds.includes("cuni-mff-cs-en-2026"));
    assert.ok(enIds.includes("muni-fi-vi-en-2026"));
    assert.ok(!enIds.includes("cuni-mff-cs-cs-2026"));
    assert.ok(csIds.includes("cuni-mff-cs-cs-2026"));
    assert.ok(csIds.includes("muni-fi-inf-cs-2026"));
    assert.ok(!csIds.includes("muni-fi-vi-en-2026"));
  });

  it("keeps Charles closed and Masaryk English February intake applyable", () => {
    const english = filterOfferings(browse, {
      teachingLanguage: "en",
      includeJointRequired: false,
      search: "",
      degree: "all",
      city: "all",
      ownership: "all",
      listedOnly: false,
      status: "open",
      orientation: "all",
      sort: "default",
      page: 1,
      pageSize: 20,
    }, now, "en");
    const openIds = english.page.map((item) => item.offering.id);
    assert.ok(openIds.includes("muni-fi-vi-en-2026"));
    assert.ok(!openIds.includes("cuni-mff-cs-en-2026"));
    const muni = english.page.find((item) => item.offering.id === "muni-fi-vi-en-2026");
    assert.ok(muni);
    assert.equal(canApply(muni.summary), true);
    assert.ok(primaryApplicationUrl(muni.summary, muni.offering.applicationUrl)?.includes("is.muni.cz"));
  });
});

describe("verified apply portals", () => {
  const portals = JSON.parse(
    readFileSync(resolve(root, "data/sources/admissions/apply-portals.json"), "utf8"),
  ) as {
    catalogKind: string;
    institutions: Array<{ institutionId: string; kind: string; applyUrl: string | null; admissionsUrl: string | null }>;
  };

  it("covers every register HEI and never stores a CSS or 404 asset as an apply URL", () => {
    assert.equal(portals.catalogKind, "tracer_not_published");
    assert.equal(portals.institutions.length, 54);
    for (const row of portals.institutions) {
      for (const url of [row.applyUrl, row.admissionsUrl]) {
        if (!url) continue;
        assert.equal(url.includes(".css"), false);
        assert.match(url, /^https?:\/\//);
      }
      if (row.kind === "e_application") assert.ok(row.applyUrl);
      if (row.kind === "missing") assert.equal(row.applyUrl, null);
    }
  });
});

describe("Masaryk University admissions tracer", () => {
  const tracer = JSON.parse(
    readFileSync(resolve(root, "data/sources/admissions/muni-fi-tracer.json"), "utf8"),
  ) as {
    catalogKind: string;
    dataClass: string;
    institutionId: string;
    offerings: Array<{
      id: string;
      degree: string;
      teachingLanguages: string[];
      applicationUrl: string | null;
      tuition: { published: boolean; amount: number | null };
      applicationFee: { isNotTuition: boolean; amount: number | null };
      windows: ApplicationWindow[];
    }>;
  };
  assert.equal(tracer.institutionId, "msmt-vs_14000");

  it("is a limited admissions extract and does not invent an English-taught FI bachelor", () => {
    assert.equal(tracer.catalogKind, "tracer_not_published");
    const en = tracer.offerings.find((item) => item.teachingLanguages[0] === "en");
    const cs = tracer.offerings.find((item) => item.teachingLanguages[0] === "cs");
    assert.ok(en);
    assert.ok(cs);
    assert.equal(en.degree, "master");
    assert.equal(cs.degree, "bachelor");
    const ids = new Set(catalog.offerings.map((item) => item.id));
    assert.equal(ids.has("muni-fi-vi-en-2026"), false);
    assert.equal(ids.has("muni-fi-inf-cs-2026"), false);
  });

  it("keeps the February English intake open after the September intake closed", () => {
    const en = tracer.offerings.find((item) => item.id === "muni-fi-vi-en-2026");
    assert.ok(en);
    const summary = summarizeWindows(en.windows, now);
    assert.equal(summary.opportunityStatus, "open");
    assert.equal(summary.current[0]?.id, "win-muni-fi-vi-en-feb-2027");
    assert.ok(summary.closed.some((item) => item.id === "win-muni-fi-vi-en-sep-2026"));
    assert.equal(canApply(summary), true);
    assert.ok(primaryApplicationUrl(summary, en.applicationUrl));
    for (const window of en.windows) {
      assert.equal(window.roundNumber, null);
      assert.ok(window.opensAt);
      assert.ok(window.closesAt);
    }
  });

  it("closes the Czech bachelor window and does not collapse conflicting application fees", () => {
    const cs = tracer.offerings.find((item) => item.id === "muni-fi-inf-cs-2026");
    const en = tracer.offerings.find((item) => item.id === "muni-fi-vi-en-2026");
    assert.ok(cs);
    assert.ok(en);
    assert.equal(evaluateWindow(cs.windows[0], now), "closed");
    assert.equal(canApply(summarizeWindows(cs.windows, now)), false);
    assert.equal(cs.tuition.published, true);
    assert.equal(cs.tuition.amount, 0);
    assert.equal(en.tuition.amount, 4500);
    assert.equal(cs.applicationFee.amount, null);
    assert.equal(en.applicationFee.amount, null);
    assert.equal(cs.applicationFee.isNotTuition, true);
  });
});

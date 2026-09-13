import { withBase } from "./base.ts";
import { foldText, institutionAliases } from "./institutions.ts";
import { ISCED_BROAD_ORDER, fieldGroupLabel, offeringFieldGroup } from "./iscedFields.ts";
import type {
  ApplicationWindow,
  CatalogSnapshot,
  FilterQuery,
  Institution,
  JobFilterQuery,
  JobTrack,
  JobView,
  Offering,
  OfferingView,
  ResearchJob,
  TeachingLanguageChoice,
  UiLocale,
  WindowStatus,
  WindowSummary,
} from "./types";

export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;
export const CSCSE_LOOKUP_URL = "http://yxcx.cscse.edu.cn/rzyxmd";

const DEFAULT_TZ = "Europe/Prague";

export function isLocale(value: string): value is UiLocale {
  return value === "zh-CN" || value === "en" || value === "cs";
}

export function calendarDateInZone(now: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

function isoDatePart(value: string): string {
  return value.slice(0, 10);
}

/**
 * Guanfu reference compared MM-DD without a year, and treated a missing start
 * date as open whenever an end date existed. This project keeps full ISO dates
 * (or null) and does not infer an opening from a closing date alone.
 * Datetimes without an offset are interpreted in the record timezone, never
 * the visitor's local zone.
 */
export function parseInstant(value: string, timeZone = DEFAULT_TZ): number {
  if (/[zZ]$|[+-]\d{2}:\d{2}$/.test(value)) {
    const ms = Date.parse(value);
    return Number.isNaN(ms) ? Number.NaN : ms;
  }
  const iso = value.includes("T") ? value : `${value}T00:00:00`;
  const utcGuess = Date.parse(`${iso}Z`);
  if (Number.isNaN(utcGuess)) return Date.parse(value);
  try {
    const formatter = new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    });
    const parts = Object.fromEntries(formatter.formatToParts(new Date(utcGuess)).map((part) => [part.type, part.value]));
    const asUtc = Date.UTC(
      Number(parts.year),
      Number(parts.month) - 1,
      Number(parts.day),
      Number(parts.hour),
      Number(parts.minute),
      Number(parts.second),
    );
    return utcGuess - (asUtc - utcGuess);
  } catch {
    return utcGuess;
  }
}

function isPastClose(window: ApplicationWindow, now: Date, today: string, timeZone: string): boolean {
  if (!window.closesAt) return false;
  if (window.datePrecision === "datetime") return now.getTime() > parseInstant(window.closesAt, timeZone);
  if (window.datePrecision === "date") return today > isoDatePart(window.closesAt);
  return false;
}

function isBeforeOpen(window: ApplicationWindow, now: Date, today: string, timeZone: string): boolean {
  if (!window.opensAt) return false;
  if (window.datePrecision === "datetime") return now.getTime() < parseInstant(window.opensAt, timeZone);
  if (window.datePrecision === "date") return today < isoDatePart(window.opensAt);
  return false;
}

export function evaluateWindow(window: ApplicationWindow, now: Date): WindowStatus {
  const timeZone = window.timezone || DEFAULT_TZ;
  let today = "";
  try {
    today = calendarDateInZone(now, timeZone);
  } catch {
    today = calendarDateInZone(now, DEFAULT_TZ);
  }

  if (window.status === "closed") return "closed";

  if (window.conditionalOnVacancies && window.status === "conditional") {
    if (isPastClose(window, now, today, timeZone)) return "closed";
    return "conditional";
  }

  if (window.datePrecision === "month" || window.datePrecision === "unknown") {
    return window.status;
  }

  if (isPastClose(window, now, today, timeZone)) return "closed";
  if (!window.opensAt) {
    if (window.status === "conditional") return "conditional";
    return "unknown";
  }
  if (isBeforeOpen(window, now, today, timeZone)) return "upcoming";
  if (window.status === "conditional") return "conditional";
  return "open";
}

export function summarizeWindows(
  windows: ApplicationWindow[],
  now: Date,
  wholeOpportunityClosed = false,
): WindowSummary {
  const sorted = [...windows].sort((a, b) => {
    const aKey = a.opensAt || a.closesAt || "";
    const bKey = b.opensAt || b.closesAt || "";
    return aKey.localeCompare(bKey);
  });

  if (wholeOpportunityClosed) {
    return {
      opportunityStatus: "closed",
      current: [],
      upcoming: [],
      closed: sorted,
      all: sorted,
    };
  }

  const evaluated = sorted.map((window) => ({ window, state: evaluateWindow(window, now) }));
  const open = evaluated.filter((item) => item.state === "open").map((item) => item.window);
  const conditional = evaluated.filter((item) => item.state === "conditional").map((item) => item.window);
  const upcoming = evaluated.filter((item) => item.state === "upcoming").map((item) => item.window);
  const closed = evaluated.filter((item) => item.state === "closed").map((item) => item.window);

  if (open.length) {
    return { opportunityStatus: "open", current: open, upcoming, closed, all: sorted };
  }
  if (conditional.length) {
    return { opportunityStatus: "conditional", current: conditional, upcoming, closed, all: sorted };
  }
  if (upcoming.length) {
    return { opportunityStatus: "upcoming", current: upcoming, upcoming, closed, all: sorted };
  }
  const unknown = evaluated.filter((item) => item.state === "unknown").map((item) => item.window);
  if (unknown.length) {
    return { opportunityStatus: "unknown", current: unknown, upcoming, closed, all: sorted };
  }
  if (sorted.length) {
    return { opportunityStatus: "closed", current: [], upcoming, closed, all: sorted };
  }
  return { opportunityStatus: "unknown", current: [], upcoming, closed, all: sorted };
}

export function canApply(summary: WindowSummary): boolean {
  return summary.opportunityStatus === "open";
}

export function windowCanApply(window: ApplicationWindow, now: Date, wholeClosed = false): boolean {
  return !wholeClosed && evaluateWindow(window, now) === "open";
}

export function jobOpportunityClosed(job: ResearchJob): boolean {
  return job.wholeOpportunityClosed || job.lifecycleStatus === "closed" || job.lifecycleStatus === "expired";
}

export function canonicalOfferingId(catalog: CatalogSnapshot, id: string): string {
  return catalog.offeringAliases?.[id] ?? id;
}

export function primaryApplicationUrl(summary: WindowSummary, fallback: string | null): string | null {
  if (!canApply(summary)) return null;
  const current = summary.current[0];
  if (current?.applicationUrl) return current.applicationUrl;
  return fallback;
}

/** Official page to show on a card. A reachable portal is not an open window. */
export function officialOfferingHref(
  offering: Offering,
  institution: Institution,
  portal?: { admissionsUrl: string | null; admissionsUrlEn: string | null } | null,
): string | null {
  const programmePage = safeHttpUrl(offering.officialProgrammeUrl);
  if (programmePage) return programmePage;
  const apply = offering.applicationTargetKind === "general_portal" ? null : safeHttpUrl(offering.applicationUrl);
  if (apply) return apply;
  if (portal) {
    const language = offering.teachingLanguages[0];
    const admissions =
      language === "en" ? portal.admissionsUrlEn || portal.admissionsUrl : portal.admissionsUrl || portal.admissionsUrlEn;
    const href = safeHttpUrl(admissions);
    if (href) return href;
  }
  return safeHttpUrl(institution.officialUrl);
}

export function officialJobHref(job: ResearchJob): string | null {
  return safeHttpUrl(job.applicationUrl) || safeHttpUrl(job.sourceUrl);
}

export function windowIsOpen(window: ApplicationWindow, now: Date): boolean {
  return evaluateWindow(window, now) === "open";
}

export function matchesTeachingLanguage(
  offering: Offering,
  choice: TeachingLanguageChoice,
  includeJointRequired: boolean,
): boolean {
  if (choice == null) return false;
  if (choice === "all") return true;
  if (offering.languageMode === "joint_required") {
    const hasBoth = offering.teachingLanguages.includes("en") && offering.teachingLanguages.includes("cs");
    return includeJointRequired && hasBoth;
  }
  return offering.languageMode === "single" && offering.teachingLanguages.length === 1 && offering.teachingLanguages[0] === choice;
}

function textBlob(_locale: UiLocale, offering: Offering, institution: Institution): string {
  return foldText(
    [
      offering.title["zh-CN"],
      offering.title.en,
      offering.title.cs,
      offering.field["zh-CN"],
      offering.field.en,
      offering.field.cs,
      institution.displayName["zh-CN"],
      institution.displayName.en,
      institution.displayName.cs,
      institution.officialName,
      institution.city["zh-CN"],
      institution.city.en,
      institution.city.cs,
    ].join(" "),
  );
}

export function defaultFilterQuery(overrides: Partial<FilterQuery> = {}): FilterQuery {
  return {
    teachingLanguage: null,
    includeJointRequired: false,
    search: "",
    degree: "all",
    field: "all",
    city: "all",
    institutionId: "all",
    ownership: "all",
    listedOnly: false,
    status: "all",
    orientation: "all",
    sort: "default",
    page: 1,
    pageSize: DEFAULT_PAGE_SIZE,
    ...overrides,
  };
}

export function buildOfferingViews(catalog: CatalogSnapshot, now: Date): OfferingView[] {
  const programmes = new Map(catalog.programmes.map((item) => [item.id, item]));
  const institutions = new Map(catalog.institutions.map((item) => [item.id, item]));
  return catalog.offerings.map((offering) => {
    const programme = programmes.get(offering.programmeId);
    const institution = institutions.get(offering.institutionId);
    if (!programme || !institution) {
      throw new Error(`Offering ${offering.id} is missing programme or institution`);
    }
    const windows = catalog.windows.filter((window) => window.ownerType === "offering" && window.ownerId === offering.id);
    const summary = summarizeWindows(windows, now, offering.lifecycleOverride === "closed");
    return { offering, programme, institution, windows, summary };
  });
}

export function filterOfferings(
  catalog: CatalogSnapshot,
  query: FilterQuery,
  now: Date,
  locale: UiLocale,
): { needsChoice: boolean; total: number; page: OfferingView[] } {
  if (query.teachingLanguage == null) {
    return { needsChoice: true, total: 0, page: [] };
  }

  let views = buildOfferingViews(catalog, now).filter((view) =>
    matchesTeachingLanguage(view.offering, query.teachingLanguage, query.includeJointRequired),
  );

  if (query.search.trim()) {
    const needle = foldText(query.search.trim());
    views = views.filter((view) => textBlob(locale, view.offering, view.institution).includes(needle));
  }
  if (query.degree !== "all") views = views.filter((view) => view.offering.degree === query.degree);
  if (query.field && query.field !== "all") {
    views = views.filter((view) => offeringFieldGroup(view.offering) === query.field);
  }
  if (query.city !== "all") views = views.filter((view) => view.institution.city.en === query.city);
  if (query.institutionId && query.institutionId !== "all") {
    views = views.filter((view) => view.offering.institutionId === query.institutionId);
  }
  if (query.ownership !== "all") views = views.filter((view) => view.institution.ownership === query.ownership);
  if (query.listedOnly) views = views.filter((view) => view.institution.cscseReference.lookupStatus === "listed");
  if (query.orientation !== "all") views = views.filter((view) => view.programme.orientation === query.orientation);
  if (query.status !== "all") views = views.filter((view) => view.summary.opportunityStatus === query.status);

  views.sort((a, b) => {
    if (query.sort === "deadline") {
      const aClose = a.summary.current[0]?.closesAt || "9999-99-99";
      const bClose = b.summary.current[0]?.closesAt || "9999-99-99";
      return aClose.localeCompare(bClose);
    }
    const rank = { open: 0, conditional: 1, upcoming: 2, unknown: 3, closed: 4 } as const;
    const delta = rank[a.summary.opportunityStatus] - rank[b.summary.opportunityStatus];
    if (delta !== 0) return delta;
    return a.offering.title[locale].localeCompare(b.offering.title[locale], locale);
  });

  const total = views.length;
  const pageSize = clampPageSize(query.pageSize);
  const start = pageStart(query.page, pageSize, total);
  if (start == null) return { needsChoice: false, total, page: [] };
  return { needsChoice: false, total, page: views.slice(start, start + pageSize) };
}

function clampPageSize(pageSize: number): number {
  if (!Number.isFinite(pageSize) || pageSize < 1) return DEFAULT_PAGE_SIZE;
  return Math.min(Math.floor(pageSize), MAX_PAGE_SIZE);
}

function pageStart(page: number, pageSize: number, total: number): number | null {
  const safePage = Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1;
  const start = (safePage - 1) * pageSize;
  if (start < 0 || start >= total) return null;
  return start;
}

export function isMasterEligible(job: ResearchJob): boolean {
  if (job.isPostdoc) return false;
  if (job.minimumDegree === "doctorate") return false;
  if (job.doctorateRequired === true) return false;
  if (job.doctorateRequired === null) return false;
  if (job.paidStatus !== "confirmed") return false;
  return job.minimumDegree === "bachelor" || job.minimumDegree === "master";
}

export function jobTrackOf(job: ResearchJob): JobTrack {
  if (job.track) return job.track;
  if (job.isPostdoc) return "postdoc";
  if (job.minimumDegree === "bachelor") return "assistant";
  return "post_master";
}

export function isPublicJob(job: ResearchJob, summary: WindowSummary): boolean {
  if (jobOpportunityClosed(job)) return false;
  if (job.visibility !== "public") return false;
  if (summary.opportunityStatus === "closed") return false;
  return true;
}

export function buildJobViews(catalog: CatalogSnapshot, now: Date): JobView[] {
  const institutions = new Map(catalog.institutions.map((item) => [item.id, item]));
  return catalog.jobs.map((job) => {
    const employer = institutions.get(job.employerId);
    if (!employer) throw new Error(`Job ${job.id} is missing employer`);
    const windows = catalog.windows.filter((window) => window.ownerType === "research_job" && window.ownerId === job.id);
    const summary = summarizeWindows(windows, now, jobOpportunityClosed(job));
    return { job, employer, windows, summary };
  });
}

export function defaultJobFilterQuery(overrides: Partial<JobFilterQuery> = {}): JobFilterQuery {
  return {
    masterEligible: true,
    track: "master_eligible",
    doctoralEnrollment: "all",
    workingLanguage: "all",
    fundedDoctoral: false,
    search: "",
    page: 1,
    pageSize: DEFAULT_PAGE_SIZE,
    ...overrides,
  };
}

/**
 * A71: a funded doctoral opportunity for incoming PhD applicants. Derived from
 * structured facts only — confirmed pay, required doctoral enrollment, a
 * master or bachelor entry threshold, and never a postdoc — so no R1 tag or
 * job title can place a post into this result set.
 */
export function isFundedDoctoral(job: ResearchJob): boolean {
  if (job.isPostdoc) return false;
  if (job.paidStatus !== "confirmed") return false;
  if (job.doctoralEnrollment !== "required") return false;
  return job.minimumDegree === "master" || job.minimumDegree === "bachelor";
}

function jobSearchBlob(view: JobView): string {
  const job = view.job;
  const employer = view.employer;
  return foldText(
    [
      job.title["zh-CN"],
      job.title.en,
      job.title.cs,
      job.originalText ?? "",
      job.laboratory?.["zh-CN"] ?? "",
      job.laboratory?.en ?? "",
      job.laboratory?.cs ?? "",
      employer.displayName["zh-CN"],
      employer.displayName.en,
      employer.displayName.cs,
      employer.officialName,
      employer.city["zh-CN"],
      employer.city.en,
      employer.city.cs,
    ].join(" "),
  );
}

function jobEmployerAliasBlob(view: JobView): string {
  return institutionAliases(view.employer.id).join("\n");
}

/** A71: multiword queries are tokenized; terms never need one contiguous blob. */
export function jobMatchesSearch(view: JobView, search: string): boolean {
  const needle = search.trim();
  if (!needle) return true;
  const blob = jobSearchBlob(view);
  const aliases = jobEmployerAliasBlob(view)
    .split("\n")
    .filter((alias) => alias.length > 0);
  const terms = foldText(needle)
    .split(/\s+/)
    .filter((term) => term.length > 0);
  if (!terms.length) return true;
  // Whole-phrase alias equality resolves short or ambiguous institution codes
  // ("CZU", "MU") that must never become arbitrary substring matches.
  const foldedQuery = foldText(needle);
  if (aliases.some((alias) => alias === foldedQuery)) return true;
  const blobTokens = new Set(blob.split(/[^a-z0-9]+/).filter(Boolean));
  return terms.every((term) => {
    if (aliases.some((alias) => alias === term)) return true;
    // Short latin terms ("mu", "uk") only match whole words or aliases; longer
    // terms and CJK queries may substring-match the folded blob.
    if (term.length <= 3 && !/[\u3400-\u9fff]/.test(term)) {
      return blobTokens.has(term);
    }
    return blob.includes(term);
  });
}

export function filterJobs(
  catalog: CatalogSnapshot,
  query: JobFilterQuery,
  now: Date,
  _locale: UiLocale,
): { total: number; page: JobView[] } {
  let views = buildJobViews(catalog, now).filter((view) => isPublicJob(view.job, view.summary));
  const track = query.track ?? (query.masterEligible ? "master_eligible" : "all");
  if (track === "master_eligible") views = views.filter((view) => isMasterEligible(view.job));
  else if (track === "assistant") views = views.filter((view) => jobTrackOf(view.job) === "assistant");
  else if (track === "post_master") views = views.filter((view) => jobTrackOf(view.job) === "post_master");
  else if (track === "postdoc") views = views.filter((view) => view.job.isPostdoc || jobTrackOf(view.job) === "postdoc");
  if (query.fundedDoctoral) views = views.filter((view) => isFundedDoctoral(view.job));
  if (query.doctoralEnrollment !== "all") {
    views = views.filter((view) => view.job.doctoralEnrollment === query.doctoralEnrollment);
  }
  if (query.workingLanguage !== "all") {
    views = views.filter((view) => view.job.workingLanguages.includes(query.workingLanguage));
  }
  if (query.search.trim()) {
    views = views.filter((view) => jobMatchesSearch(view, query.search));
  }
  const total = views.length;
  const pageSize = clampPageSize(query.pageSize);
  const start = pageStart(query.page, pageSize, total);
  if (start == null) return { total, page: [] };
  return { total, page: views.slice(start, start + pageSize) };
}

export function filterQueryFromSearch(search: string): FilterQuery {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const teaching = params.get("teachingLanguage");
  return defaultFilterQuery({
    teachingLanguage: teaching === "en" || teaching === "cs" || teaching === "all" ? teaching : null,
    includeJointRequired: params.get("includeJoint") === "1",
    search: params.get("q") ?? "",
    degree: (params.get("degree") as FilterQuery["degree"]) || "all",
    field: params.get("field") || "all",
    city: params.get("city") || "all",
    institutionId: params.get("institution") || "all",
    ownership: (params.get("ownership") as FilterQuery["ownership"]) || "all",
    listedOnly: params.get("listedOnly") === "1",
    status: (params.get("status") as FilterQuery["status"]) || "all",
    orientation: (params.get("orientation") as FilterQuery["orientation"]) || "all",
    sort: params.get("sort") === "deadline" ? "deadline" : "default",
    page: Number(params.get("page") || "1") || 1,
  });
}

export function searchFromFilter(query: FilterQuery): string {
  const params = new URLSearchParams();
  if (query.teachingLanguage) params.set("teachingLanguage", query.teachingLanguage);
  if (query.includeJointRequired) params.set("includeJoint", "1");
  if (query.search.trim()) params.set("q", query.search.trim());
  if (query.degree !== "all") params.set("degree", query.degree);
  if (query.field && query.field !== "all") params.set("field", query.field);
  if (query.city !== "all") params.set("city", query.city);
  if (query.institutionId && query.institutionId !== "all") params.set("institution", query.institutionId);
  if (query.orientation !== "all") params.set("orientation", query.orientation);
  if (query.ownership !== "all") params.set("ownership", query.ownership);
  if (query.listedOnly) params.set("listedOnly", "1");
  if (query.status !== "all") params.set("status", query.status);
  if (query.sort === "deadline") params.set("sort", "deadline");
  if (query.page > 1) params.set("page", String(query.page));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function programmesBackHref(locale: UiLocale, offering: Offering): string {
  const params = new URLSearchParams();
  if (offering.languageMode === "single" && offering.teachingLanguages.length === 1) {
    const language = offering.teachingLanguages[0];
    params.set("teachingLanguage", language === "en" || language === "cs" ? language : "all");
  } else {
    params.set("teachingLanguage", "all");
    if (offering.languageMode === "joint_required") params.set("includeJoint", "1");
  }
  return withBase(`/${locale}/programmes?${params.toString()}`);
}

export function jobFilterFromSearch(search: string): JobFilterQuery {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const applied = params.get("applied") === "1";
  const trackParam = params.get("track");
  const track =
    trackParam === "assistant" ||
    trackParam === "post_master" ||
    trackParam === "postdoc" ||
    trackParam === "all" ||
    trackParam === "master_eligible"
      ? trackParam
      : applied
        ? params.get("masterEligible") === "1"
          ? "master_eligible"
          : "all"
        : "master_eligible";
  return defaultJobFilterQuery({
    masterEligible: track === "master_eligible",
    track,
    doctoralEnrollment: (params.get("phd") as JobFilterQuery["doctoralEnrollment"]) || "all",
    workingLanguage: params.get("lang") || "all",
    fundedDoctoral: params.get("funded") === "1",
    search: params.get("q") ?? "",
    page: Number(params.get("page") || "1") || 1,
  });
}

export function searchFromJobFilter(query: JobFilterQuery): string {
  const params = new URLSearchParams();
  params.set("applied", "1");
  const track = query.track ?? (query.masterEligible ? "master_eligible" : "all");
  if (track === "master_eligible") params.set("masterEligible", "1");
  else if (track !== "all") params.set("track", track);
  if (query.fundedDoctoral) params.set("funded", "1");
  if (query.doctoralEnrollment !== "all") params.set("phd", query.doctoralEnrollment);
  if (query.workingLanguage !== "all") params.set("lang", query.workingLanguage);
  if (query.search.trim()) params.set("q", query.search.trim());
  if (query.page > 1) params.set("page", String(query.page));
  return `?${params.toString()}`;
}

export function uniqueCityOptions(catalog: CatalogSnapshot, locale: UiLocale): { value: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const item of catalog.institutions) {
    if (!seen.has(item.city.en)) seen.set(item.city.en, item.city[locale]);
  }
  return [...seen.entries()].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, locale));
}

export function uniqueFieldOptions(catalog: CatalogSnapshot, locale: UiLocale): { value: string; label: string }[] {
  const present = new Set(catalog.offerings.map((item) => offeringFieldGroup(item)));
  const ordered: string[] = ISCED_BROAD_ORDER.filter((code) => present.has(code));
  if (present.has("unknown")) ordered.push("unknown");
  return ordered.map((value) => ({ value, label: fieldGroupLabel(value, locale) }));
}

export function uniqueInstitutionOptions(
  catalog: CatalogSnapshot,
  locale: UiLocale,
  city = "all",
): { value: string; label: string }[] {
  return catalog.institutions
    .filter((item) => city === "all" || item.city.en === city)
    .map((item) => ({ value: item.id, label: item.displayName[locale] || item.officialName }))
    .sort((a, b) => a.label.localeCompare(b.label, locale));
}

export function safeHttpUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
  } catch {
    return null;
  }
  return null;
}

export function findOffering(catalog: CatalogSnapshot, id: string, now: Date): OfferingView | null {
  const canonical = canonicalOfferingId(catalog, id);
  return buildOfferingViews(catalog, now).find((view) => view.offering.id === canonical) ?? null;
}

export function findJob(catalog: CatalogSnapshot, id: string, now: Date): JobView | null {
  return buildJobViews(catalog, now).find((view) => view.job.id === id) ?? null;
}

export function findInstitution(catalog: CatalogSnapshot, id: string): Institution | null {
  return catalog.institutions.find((item) => item.id === id) ?? null;
}

export function uniqueCities(catalog: CatalogSnapshot, locale: UiLocale): string[] {
  return uniqueCityOptions(catalog, locale).map((item) => item.label);
}

export function ownershipIsNotCscse(institution: Institution): boolean {
  return institution.ownership !== "unknown" && institution.cscseReference.lookupStatus === "unverified";
}

import type {
  ApplicationWindow,
  CatalogSnapshot,
  FilterQuery,
  Institution,
  JobFilterQuery,
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
 */
export function evaluateWindow(window: ApplicationWindow, now: Date): WindowStatus {
  if (window.conditionalOnVacancies && window.status === "conditional") {
    return "conditional";
  }

  const timeZone = window.timezone || DEFAULT_TZ;
  const today = calendarDateInZone(now, timeZone);

  if (window.datePrecision === "month" || window.datePrecision === "unknown") {
    return window.status;
  }

  if (window.datePrecision === "datetime") {
    if (window.closesAt && now.getTime() > Date.parse(window.closesAt)) return "closed";
    if (window.opensAt && now.getTime() < Date.parse(window.opensAt)) return "upcoming";
    if (window.opensAt && (!window.closesAt || now.getTime() <= Date.parse(window.closesAt))) {
      return window.status === "unknown" ? "open" : window.status === "closed" ? "open" : window.status;
    }
    return window.status;
  }

  if (window.closesAt && today > isoDatePart(window.closesAt)) return "closed";
  if (window.opensAt && today < isoDatePart(window.opensAt)) return "upcoming";
  if (window.opensAt && (!window.closesAt || today <= isoDatePart(window.closesAt))) return "open";

  if (!window.opensAt && window.closesAt) {
    if (today > isoDatePart(window.closesAt)) return "closed";
    if (window.status === "open") return "open";
    if (window.status === "conditional") return "conditional";
    return "unknown";
  }

  return window.status;
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
  const current = evaluated
    .filter((item) => item.state === "open" || item.state === "conditional")
    .map((item) => item.window);
  const upcoming = evaluated.filter((item) => item.state === "upcoming").map((item) => item.window);
  const closed = evaluated.filter((item) => item.state === "closed").map((item) => item.window);

  if (current.length) {
    return { opportunityStatus: "open", current, upcoming, closed, all: sorted };
  }
  if (upcoming.length) {
    return { opportunityStatus: "upcoming", current: upcoming, upcoming, closed, all: sorted };
  }
  if (closed.length && !sorted.length) {
    return { opportunityStatus: "closed", current: [], upcoming, closed, all: sorted };
  }
  if (sorted.length && current.length === 0 && upcoming.length === 0) {
    const unknown = evaluated.filter((item) => item.state === "unknown").map((item) => item.window);
    if (unknown.length) {
      return { opportunityStatus: "unknown", current: unknown, upcoming, closed, all: sorted };
    }
    return { opportunityStatus: "closed", current: [], upcoming, closed, all: sorted };
  }
  return { opportunityStatus: "unknown", current: [], upcoming, closed, all: sorted };
}

export function primaryApplicationUrl(summary: WindowSummary, fallback: string | null): string | null {
  const current = summary.current[0];
  if (summary.opportunityStatus === "closed") return null;
  if (current?.applicationUrl) return current.applicationUrl;
  return fallback;
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

function textBlob(locale: UiLocale, offering: Offering, institution: Institution): string {
  return [
    offering.title[locale],
    offering.title.en,
    offering.field[locale],
    institution.displayName[locale],
    institution.officialName,
    institution.city[locale],
  ]
    .join(" ")
    .toLowerCase();
}

export function defaultFilterQuery(overrides: Partial<FilterQuery> = {}): FilterQuery {
  return {
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
    const needle = query.search.trim().toLowerCase();
    views = views.filter((view) => textBlob(locale, view.offering, view.institution).includes(needle));
  }
  if (query.degree !== "all") views = views.filter((view) => view.offering.degree === query.degree);
  if (query.city !== "all") views = views.filter((view) => view.institution.city.en === query.city || view.institution.city[locale] === query.city);
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
    const rank = { open: 0, upcoming: 1, unknown: 2, closed: 3 } as const;
    const delta = rank[a.summary.opportunityStatus] - rank[b.summary.opportunityStatus];
    if (delta !== 0) return delta;
    return a.offering.title[locale].localeCompare(b.offering.title[locale], locale);
  });

  const total = views.length;
  const start = Math.max(0, (query.page - 1) * query.pageSize);
  return { needsChoice: false, total, page: views.slice(start, start + query.pageSize) };
}

export function isMasterEligible(job: ResearchJob): boolean {
  if (job.isPostdoc) return false;
  if (job.minimumDegree === "doctorate") return false;
  if (job.doctorateRequired === true) return false;
  if (job.doctorateRequired === null) return false;
  if (job.paidStatus !== "confirmed") return false;
  return job.minimumDegree === "bachelor" || job.minimumDegree === "master";
}

export function isPublicJob(job: ResearchJob, summary: WindowSummary): boolean {
  if (job.wholeOpportunityClosed) return false;
  if (job.visibility !== "public") return false;
  if (job.lifecycleStatus === "closed" || job.lifecycleStatus === "expired") return false;
  if (summary.opportunityStatus === "closed") return false;
  return true;
}

export function buildJobViews(catalog: CatalogSnapshot, now: Date): JobView[] {
  const institutions = new Map(catalog.institutions.map((item) => [item.id, item]));
  return catalog.jobs.map((job) => {
    const employer = institutions.get(job.employerId);
    if (!employer) throw new Error(`Job ${job.id} is missing employer`);
    const windows = catalog.windows.filter((window) => window.ownerType === "research_job" && window.ownerId === job.id);
    const summary = summarizeWindows(windows, now, job.wholeOpportunityClosed);
    return { job, employer, windows, summary };
  });
}

export function defaultJobFilterQuery(overrides: Partial<JobFilterQuery> = {}): JobFilterQuery {
  return {
    masterEligible: true,
    doctoralEnrollment: "all",
    workingLanguage: "all",
    search: "",
    page: 1,
    pageSize: DEFAULT_PAGE_SIZE,
    ...overrides,
  };
}

export function filterJobs(
  catalog: CatalogSnapshot,
  query: JobFilterQuery,
  now: Date,
  locale: UiLocale,
): { total: number; page: JobView[] } {
  let views = buildJobViews(catalog, now).filter((view) => isPublicJob(view.job, view.summary));
  if (query.masterEligible) views = views.filter((view) => isMasterEligible(view.job));
  if (query.doctoralEnrollment !== "all") {
    views = views.filter((view) => view.job.doctoralEnrollment === query.doctoralEnrollment);
  }
  if (query.workingLanguage !== "all") {
    views = views.filter((view) => view.job.workingLanguages.includes(query.workingLanguage));
  }
  if (query.search.trim()) {
    const needle = query.search.trim().toLowerCase();
    views = views.filter((view) =>
      [view.job.title[locale], view.job.title.en, view.employer.displayName[locale], view.employer.officialName]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }
  const total = views.length;
  const start = Math.max(0, (query.page - 1) * query.pageSize);
  return { total, page: views.slice(start, start + query.pageSize) };
}

export function findOffering(catalog: CatalogSnapshot, id: string, now: Date): OfferingView | null {
  return buildOfferingViews(catalog, now).find((view) => view.offering.id === id) ?? null;
}

export function findJob(catalog: CatalogSnapshot, id: string, now: Date): JobView | null {
  return buildJobViews(catalog, now).find((view) => view.job.id === id) ?? null;
}

export function findInstitution(catalog: CatalogSnapshot, id: string): Institution | null {
  return catalog.institutions.find((item) => item.id === id) ?? null;
}

export function uniqueCities(catalog: CatalogSnapshot, locale: UiLocale): string[] {
  return [...new Set(catalog.institutions.map((item) => item.city[locale]))].sort();
}

export function ownershipIsNotCscse(institution: Institution): boolean {
  return institution.ownership !== "unknown" && institution.cscseReference.lookupStatus === "unverified";
}

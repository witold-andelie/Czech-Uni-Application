export const UI_LOCALES = ["zh-CN", "en", "cs"] as const;
export type UiLocale = (typeof UI_LOCALES)[number];

export type TeachingLanguageChoice = "en" | "cs" | "all" | null;
export type Ownership = "public" | "private" | "state" | "unknown";
export type CscseLookup = "listed" | "not_found" | "unverified";
export type LanguageMode = "single" | "joint_required";
export type RoundType = "regular" | "supplementary" | "rolling" | "unspecified";
export type WindowStatus = "upcoming" | "open" | "closed" | "conditional" | "unknown";
export type DatePrecision = "datetime" | "date" | "month" | "unknown";
export type DegreeLevel = "bachelor" | "master" | "doctorate" | "other" | "unknown";
export type DataClass =
  | "ui_fixture"
  | "published"
  | "official_admissions_extract"
  | "official_register_extract"
  | "official_career_extract";
export type CatalogKind =
  | "ui_fixture"
  | "published"
  | "tracer_not_published"
  | "browse_with_tracer"
  | "browse_with_inventory"
  | "jobs_not_published";
export type JobTrack = "assistant" | "post_master" | "postdoc";
export type JobTrackFilter = "master_eligible" | JobTrack | "all";

export interface LocalizedText {
  "zh-CN": string;
  en: string;
  cs: string;
}

export interface CscseNotice {
  id: string;
  text: LocalizedText;
  scope: string | null;
  effectiveFrom: string | null;
  effectiveTo: string | null;
  active: boolean;
}

export interface CscseReference {
  lookupStatus: CscseLookup;
  operatorListStatus?: "listed" | "absent" | null;
  evidenceKind?: "official_lookup" | "operator_supplied_list" | "none" | null;
  officialMatchedName: string | null;
  matchedAwardingInstitutionId: string | null;
  lookupUrl: string;
  checkedAt: string | null;
  operatorListDated?: string | null;
  sourceVersion: string | null;
  evidenceId: string | null;
  reviewer: string | null;
  matchConfidence: "exact" | "needs_review" | null;
  notices: CscseNotice[];
}

export interface Institution {
  id: string;
  officialName: string;
  displayName: LocalizedText;
  country: "CZ";
  city: LocalizedText;
  ownership: Ownership;
  ownershipEvidenceId: string | null;
  legalType: "university" | "non_university" | "research_institute" | "unknown";
  orientation: "research" | "applied" | "unknown";
  officialUrl: string;
  cscseReference: CscseReference;
  dataClass: DataClass;
}

export interface ApplicationWindow {
  id: string;
  ownerType: "offering" | "research_job";
  ownerId: string;
  academicYear: string | null;
  roundNumber: number | null;
  roundLabelOriginal: string | null;
  roundType: RoundType;
  applicantScope: LocalizedText | null;
  opensAt: string | null;
  closesAt: string | null;
  timezone: string | null;
  datePrecision: DatePrecision;
  status: WindowStatus;
  conditionalOnVacancies: boolean;
  applicationUrl: string | null;
  sourceEvidenceId: string;
}

export interface AdditionalLanguageRequirement {
  language: string;
  context: "admission" | "placement" | "clinical" | "other";
  requirement: "required" | "optional" | "unknown";
  evidenceUrl: string;
  note: LocalizedText | null;
}

export interface Tuition {
  amount: number | null;
  currency: string | null;
  cycle: "year" | "semester" | "programme" | null;
  published: boolean;
  evidenceUrl: string | null;
  noteOriginal?: string | null;
  variants?: {
    amount: number;
    currency: string;
    cycle: "year" | "semester" | "programme" | null;
    applicantScopeOriginal: string | null;
  }[];
}

export interface Programme {
  id: string;
  institutionId: string;
  officialCode: string | null;
  degree: DegreeLevel;
  field: LocalizedText;
  orientation: "research" | "applied" | "unknown";
}

export interface Offering {
  id: string;
  programmeId: string;
  institutionId: string;
  academicYear: string;
  teachingLanguages: string[];
  languageMode: LanguageMode;
  languageEvidenceUrl: string;
  additionalLanguageRequirements: AdditionalLanguageRequirement[];
  title: LocalizedText;
  degree: DegreeLevel;
  durationSemesters: number | null;
  field: LocalizedText;
  iscedF?: string | null;
  tuition: Tuition;
  applicationUrl: string | null;
  applicationTargetKind?: "programme_page" | "general_portal" | "unknown";
  generalApplyPortalUrl?: string | null;
  officialProgrammeUrl?: string | null;
  sourceLanguage?: string | null;
  titleOriginal?: string | null;
  fetchedAt?: string | null;
  factsReviewedAt?: string | null;
  verifiedAt: string | null;
  dataClass: DataClass;
  lifecycleOverride: "open" | "closed" | "upcoming" | "unknown" | null;
}

export interface Salary {
  amount: number | null;
  currency: string | null;
  cycle: string | null;
  tax: "gross" | "net" | "unknown";
  basisFte: number | null;
}

export interface ResearchJob {
  id: string;
  employerId: string;
  title: LocalizedText;
  laboratory: LocalizedText | null;
  minimumDegree: DegreeLevel;
  doctorateRequired: boolean | null;
  doctoralEnrollment: "required" | "optional" | "not_required" | "unspecified";
  paidStatus: "confirmed" | "unconfirmed" | "unpaid";
  salary: Salary;
  employmentFte: number | null;
  employmentStartsAt: string | null;
  workingLanguages: string[];
  sourceUrl: string;
  applicationUrl: string | null;
  applicationMethod: "web_form" | "official_instructions";
  applicationHostVerified: boolean;
  lifecycleStatus: "open" | "closed" | "expired" | "unavailable" | "unknown";
  visibility: "public" | "archived";
  isPostdoc: boolean;
  track?: JobTrack;
  city: LocalizedText;
  sourceLanguage?: string | null;
  originalText?: string | null;
  roleSummary?: LocalizedText | null;
  qualificationEvidence?: LocalizedText | null;
  applicationMaterials?: LocalizedText | null;
  verifiedAt: string | null;
  factsReviewedAt?: string | null;
  dataClass: DataClass;
  wholeOpportunityClosed: boolean;
  lastAttemptAt?: string | null;
  lastAttemptReason?: string | null;
}

export interface SourceEvidence {
  id: string;
  url: string;
  note: LocalizedText;
}

export interface CatalogSnapshot {
  generatedAt: string;
  dataClass: DataClass;
  catalogKind: CatalogKind;
  institutions: Institution[];
  programmes: Programme[];
  offerings: Offering[];
  windows: ApplicationWindow[];
  jobs: ResearchJob[];
  evidence: SourceEvidence[];
  offeringAliases?: Record<string, string>;
}

export interface FilterQuery {
  teachingLanguage: TeachingLanguageChoice;
  includeJointRequired: boolean;
  search: string;
  degree: DegreeLevel | "all";
  field?: string | "all";
  city: string | "all";
  institutionId?: string | "all";
  ownership: Ownership | "all";
  listedOnly: boolean;
  status: "open" | "upcoming" | "closed" | "conditional" | "all";
  orientation: "research" | "applied" | "all";
  sort: "default" | "deadline";
  page: number;
  pageSize: number;
}

export interface JobFilterQuery {
  masterEligible: boolean;
  track?: JobTrackFilter;
  doctoralEnrollment: "required" | "optional" | "not_required" | "unspecified" | "all";
  workingLanguage: string | "all";
  /** A71: derived funded-doctoral discovery control based on structured facts. */
  fundedDoctoral: boolean;
  search: string;
  page: number;
  pageSize: number;
}

export interface WindowSummary {
  opportunityStatus: "open" | "upcoming" | "closed" | "unknown" | "conditional";
  current: ApplicationWindow[];
  upcoming: ApplicationWindow[];
  closed: ApplicationWindow[];
  all: ApplicationWindow[];
}

export interface OfferingView {
  offering: Offering;
  programme: Programme;
  institution: Institution;
  windows: ApplicationWindow[];
  summary: WindowSummary;
}

export interface JobView {
  job: ResearchJob;
  employer: Institution;
  windows: ApplicationWindow[];
  summary: WindowSummary;
}

import baseline from "@published/msmt-hei-baseline.json";

export interface BaselineInstitution {
  id: string;
  msmtCode: string;
  officialName: string;
  officialNameEn?: string | null;
  legalType: "university" | "non_university" | "unknown";
  ownership: "public" | "private" | "state" | "unknown";
  region: string;
  seat?: string | null;
  ico?: string | null;
  officialUrl: string | null;
  officialUrlSource?: string;
  officialUrlNote?: string;
  cscseLookupStatus: "listed" | "not_found" | "unverified";
  cscseReference?: {
    lookupStatus: "listed" | "not_found" | "unverified";
    operatorListStatus?: "listed" | "absent" | null;
    evidenceKind?: "official_lookup" | "operator_supplied_list" | "none" | null;
    listedNameZh: string | null;
    listedNameEn: string | null;
    officialMatchedName: string | null;
    matchedAwardingInstitutionId?: string | null;
    lookupUrl: string;
    checkedAt: string | null;
    operatorListDated?: string | null;
    sourceVersion: string | null;
    evidenceId?: string | null;
    reviewer: string | null;
    matchConfidence: "exact" | "needs_review" | null;
    notices: { text?: { "zh-CN": string; en: string; cs: string }; active?: boolean }[];
  };
  programmeInventory?: {
    total: number;
    sourceUrl: string;
    languages?: Record<string, number>;
    note?: string;
  };
}

export interface BaselineSnapshot {
  generatedAt: string;
  sourceUrl: string;
  sourceTitle: string;
  note: string;
  counts: {
    total: number;
    public: number;
    private: number;
    state: number;
    university: number;
    nonUniversity: number;
  };
  websiteMerge?: {
    matchedPublicWebsites: number;
    sourceUrl: string;
  };
  cscseApply?: {
    matchedListed: number;
    registerNotOnList: number;
    unmatchedOperatorNames: number;
    sourceVersion: string;
    lookupUrl: string;
    note: string;
  };
  cscseUnmatched?: {
    n: number;
    zh: string;
    en: string;
    reason: string;
    reasonZh?: string;
  }[];
  institutions: BaselineInstitution[];
}

export function loadBaseline(): BaselineSnapshot {
  return baseline as BaselineSnapshot;
}

export function findBaseline(id: string): BaselineInstitution | null {
  return loadBaseline().institutions.find((item) => item.id === id) ?? null;
}

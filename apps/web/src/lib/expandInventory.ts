import type { ApplyPortal } from "./loadApplyPortals.ts";
import type { DegreeLevel, LocalizedText, Offering, Programme } from "./types.ts";

export const NINE_HEI_IDS = [
  "msmt-vs_11000",
  "msmt-vs_21000",
  "msmt-vs_41000",
  "msmt-vs_31000",
  "msmt-vs_22000",
  "msmt-vs_26000",
  "msmt-vs_14000",
  "msmt-vs_17000",
  "msmt-vs_15000",
] as const;

export const LISTED_HEI_IDS = [
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
] as const;

export const REGISTER_URL = "https://regvssp.msmt.cz/registrvssp/csplist.aspx";

export interface CompactSchool {
  id: string;
  rows: CompactRow[];
}

export type CompactRow = [string, string, string, string, number | null, string, string];

export interface CompactInventory {
  generatedAt: string;
  dataClass: "official_register_extract";
  catalogKind: "browse_with_inventory";
  sourceUrl: string;
  academicYear: string;
  note: string;
  counts?: { schools: number; programmes: number };
  schools: CompactSchool[];
}

const DEGREE: Record<string, DegreeLevel> = {
  b: "bachelor",
  m: "master",
  d: "doctorate",
  o: "other",
  u: "unknown",
};

export const EMPTY_COMPACT: CompactInventory = {
  generatedAt: "2026-09-06T00:00:00Z",
  dataClass: "official_register_extract",
  catalogKind: "browse_with_inventory",
  sourceUrl: REGISTER_URL,
  academicYear: "register",
  note: "",
  counts: { schools: 0, programmes: 0 },
  schools: [],
};

export function localizedOriginal(value: string): LocalizedText {
  return { "zh-CN": value, en: value, cs: value };
}

export function portalApplicationUrl(portal: ApplyPortal | undefined, language: string): string | null {
  if (!portal) return null;
  if (language === "en") return portal.applyUrlEn || portal.applyUrl;
  return portal.applyUrl || portal.applyUrlEn;
}

export function expandInventory(
  compact: CompactInventory,
  portals: ApplyPortal[],
): { programmes: Programme[]; offerings: Offering[] } {
  const portalById = new Map(portals.map((item) => [item.institutionId, item]));
  const programmes: Programme[] = [];
  const offerings: Offering[] = [];
  const verifiedAt = null;

  for (const school of compact.schools) {
    const portal = portalById.get(school.id);
    for (const row of school.rows) {
      const [id, title, degreeCode, faculty, years, language, isced] = row;
      const degree = DEGREE[degreeCode] ?? "unknown";
      const names = localizedOriginal(title);
      const field = localizedOriginal(faculty || title);
      programmes.push({
        id: `prog-${id}`,
        institutionId: school.id,
        officialCode: isced || null,
        degree,
        field,
        orientation: "unknown",
      });
      offerings.push({
        id,
        programmeId: `prog-${id}`,
        institutionId: school.id,
        academicYear: compact.academicYear || "register",
        teachingLanguages: [language],
        languageMode: "single",
        languageEvidenceUrl: compact.sourceUrl || REGISTER_URL,
        additionalLanguageRequirements: [],
        title: names,
        degree,
        durationSemesters: years == null ? null : Math.round(Number(years) * 2),
        field,
        iscedF: isced || null,
        tuition: {
          amount: null,
          currency: null,
          cycle: null,
          published: false,
          evidenceUrl: compact.sourceUrl || REGISTER_URL,
          noteOriginal: null,
          variants: [],
        },
        applicationUrl: portalApplicationUrl(portal, language),
        verifiedAt,
        dataClass: "official_register_extract",
        lifecycleOverride: null,
      });
    }
  }

  return { programmes, offerings };
}

export function overlayKey(institutionId: string, degree: string, language: string, title: string, faculty: string): string {
  return [institutionId, degree, language, foldKey(title), foldKey(faculty)].join("|");
}

export function foldKey(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

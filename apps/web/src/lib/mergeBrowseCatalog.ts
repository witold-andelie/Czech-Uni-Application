import type { BaselineInstitution } from "./loadBaseline.ts";
import type {
  AdditionalLanguageRequirement,
  ApplicationWindow,
  CatalogSnapshot,
  Institution,
  LocalizedText,
  Offering,
  Programme,
  SourceEvidence,
} from "./types.ts";

export interface BrowseTracerOffering {
  id: string;
  institutionId: string;
  academicYear: string;
  teachingLanguages: string[];
  languageMode: "single" | "joint_required";
  languageEvidenceUrl: string;
  additionalLanguageRequirements: AdditionalLanguageRequirement[];
  title: LocalizedText;
  degree: Offering["degree"];
  durationOriginal: string | null;
  sisIdObor?: string | null;
  applicationUrl: string | null;
  tuition: Offering["tuition"];
  window: ApplicationWindow;
  windows?: ApplicationWindow[];
}

export interface BrowseTracerSnapshot {
  generatedAt: string;
  institutionId: string;
  note: string;
  sources: Record<string, string>;
  offerings: BrowseTracerOffering[];
}

export function cityFromBaseline(item: BaselineInstitution): LocalizedText {
  const seat = (item.seat ?? "").toLowerCase();
  if (item.region === "Praha" || seat.includes("praha")) {
    return { "zh-CN": "布拉格", en: "Prague", cs: "Praha" };
  }
  if (seat.includes("brno") || item.region === "Jihomoravský") {
    return { "zh-CN": "布尔诺", en: "Brno", cs: "Brno" };
  }
  if (seat.includes("olomouc")) {
    return { "zh-CN": "奥洛穆茨", en: "Olomouc", cs: "Olomouc" };
  }
  if (seat.includes("ostrava")) {
    return { "zh-CN": "俄斯特拉发", en: "Ostrava", cs: "Ostrava" };
  }
  if (seat.includes("plzeň") || seat.includes("plzen")) {
    return { "zh-CN": "比尔森", en: "Pilsen", cs: "Plzeň" };
  }
  if (seat.includes("liberec")) {
    return { "zh-CN": "利贝雷茨", en: "Liberec", cs: "Liberec" };
  }
  if (seat.includes("pardubice")) {
    return { "zh-CN": "帕尔杜比采", en: "Pardubice", cs: "Pardubice" };
  }
  if (seat.includes("opava")) {
    return { "zh-CN": "奥帕瓦", en: "Opava", cs: "Opava" };
  }
  if (seat.includes("budějovice") || seat.includes("budejovice")) {
    return { "zh-CN": "捷克布杰约维采", en: "České Budějovice", cs: "České Budějovice" };
  }
  if (seat.includes("mladá boleslav") || seat.includes("mlada boleslav")) {
    return { "zh-CN": "姆拉达-博莱斯拉夫", en: "Mladá Boleslav", cs: "Mladá Boleslav" };
  }
  if (seat.includes("hradec")) {
    return { "zh-CN": "赫拉德茨-克拉洛韦", en: "Hradec Králové", cs: "Hradec Králové" };
  }
  if (seat.includes("ústí") || seat.includes("usti nad labem")) {
    return { "zh-CN": "拉贝河畔乌斯季", en: "Ústí nad Labem", cs: "Ústí nad Labem" };
  }
  if (seat.includes("zlín") || seat.includes("zlin")) {
    return { "zh-CN": "兹林", en: "Zlín", cs: "Zlín" };
  }
  if (seat.includes("jihlava")) {
    return { "zh-CN": "伊赫拉瓦", en: "Jihlava", cs: "Jihlava" };
  }
  if (seat.includes("písek") || seat.includes("pisek")) {
    return { "zh-CN": "皮塞克", en: "Písek", cs: "Písek" };
  }
  if (seat.includes("havířov") || seat.includes("havirov")) {
    return { "zh-CN": "哈维若夫", en: "Havířov", cs: "Havířov" };
  }
  if (seat.includes("přerov") || seat.includes("prerov")) {
    return { "zh-CN": "普热罗夫", en: "Přerov", cs: "Přerov" };
  }
  return { "zh-CN": item.region, en: item.region, cs: item.region };
}

function durationSemesters(value: string | null): number | null {
  if (!value) return null;
  const match = value.replace(",", ".").match(/(\d+(?:\.\d+)?)/);
  if (!match) return null;
  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) return null;
  if (/year|rok|let/i.test(value)) return Math.round(amount * 2);
  return Math.round(amount);
}

export function institutionFromBaseline(item: BaselineInstitution): Institution {
  const rec = item.cscseReference;
  return {
    id: item.id,
    officialName: item.officialName,
    displayName: {
      "zh-CN": rec?.listedNameZh || item.officialName,
      en: item.officialNameEn || rec?.listedNameEn || item.officialName,
      cs: item.officialName,
    },
    country: "CZ",
    city: cityFromBaseline(item),
    ownership: item.ownership,
    ownershipEvidenceId: "msmt-register",
    legalType: item.legalType === "non_university" ? "non_university" : item.legalType === "university" ? "university" : "unknown",
    orientation: "unknown",
    officialUrl: item.officialUrl || "",
    cscseReference: {
      lookupStatus: rec?.lookupStatus ?? item.cscseLookupStatus,
      operatorListStatus: rec?.operatorListStatus ?? null,
      evidenceKind: rec?.evidenceKind ?? null,
      officialMatchedName: rec?.officialMatchedName ?? null,
      matchedAwardingInstitutionId: rec?.matchedAwardingInstitutionId ?? null,
      lookupUrl: rec?.lookupUrl || "http://yxcx.cscse.edu.cn/rzyxmd",
      checkedAt: rec?.checkedAt ?? null,
      operatorListDated: rec?.operatorListDated ?? null,
      sourceVersion: rec?.sourceVersion ?? null,
      evidenceId: rec?.evidenceId ?? null,
      reviewer: rec?.reviewer ?? null,
      matchConfidence: rec?.matchConfidence ?? null,
      notices: (rec?.notices ?? []).map((notice, index) => ({
        id: `${item.id}-notice-${index}`,
        text: notice.text ?? { "zh-CN": "", en: "", cs: "" },
        scope: null,
        effectiveFrom: null,
        effectiveTo: null,
        active: notice.active ?? false,
      })),
    },
    dataClass: "official_register_extract",
  };
}

function windowsOf(item: BrowseTracerOffering): ApplicationWindow[] {
  const rows = item.windows?.length ? item.windows : [item.window];
  return rows.map((window) => ({
    id: window.id,
    ownerType: window.ownerType,
    ownerId: window.ownerId,
    academicYear: window.academicYear,
    roundNumber: window.roundNumber,
    roundLabelOriginal: window.roundLabelOriginal,
    roundType: window.roundType,
    applicantScope: window.applicantScope,
    opensAt: window.opensAt,
    closesAt: window.closesAt,
    timezone: window.timezone,
    datePrecision: window.datePrecision,
    status: window.status,
    conditionalOnVacancies: window.conditionalOnVacancies,
    applicationUrl: window.applicationUrl,
    sourceEvidenceId: window.sourceEvidenceId,
  }));
}

export function mergeBrowseCatalog(
  base: CatalogSnapshot,
  tracers: BrowseTracerSnapshot[],
  baseline: BaselineInstitution[],
): CatalogSnapshot {
  const byId = new Map(baseline.map((item) => [item.id, item]));
  const institutions = [...base.institutions];
  const institutionIndex = new Map(institutions.map((item, index) => [item.id, index]));
  const extraProgrammes: Programme[] = [];
  const extraOfferings: Offering[] = [];
  const extraWindows: ApplicationWindow[] = [];
  const extraEvidence: SourceEvidence[] = [];
  const knownOfferingIds = new Set(base.offerings.map((item) => item.id));
  const knownWindowIds = new Set(base.windows.map((item) => item.id));

  for (const snapshot of tracers) {
    const school = byId.get(snapshot.institutionId);
    if (!school) throw new Error(`Missing baseline for tracer ${snapshot.institutionId}`);
    const institution = institutionFromBaseline(school);
    const existing = institutionIndex.get(institution.id);
    if (existing != null) institutions[existing] = institution;
    else {
      institutionIndex.set(institution.id, institutions.length);
      institutions.push(institution);
    }
    const verifiedAt = snapshot.generatedAt.slice(0, 10);
    for (const item of snapshot.offerings) {
      if (knownOfferingIds.has(item.id)) continue;
      knownOfferingIds.add(item.id);
      const programmeId = `prog-${item.id}`;
      extraProgrammes.push({
        id: programmeId,
        institutionId: item.institutionId,
        officialCode: item.sisIdObor ?? null,
        degree: item.degree,
        field: item.title,
        orientation: "unknown",
      });
      extraOfferings.push({
        id: item.id,
        programmeId,
        institutionId: item.institutionId,
        academicYear: item.academicYear,
        teachingLanguages: item.teachingLanguages,
        languageMode: item.languageMode,
        languageEvidenceUrl: item.languageEvidenceUrl,
        additionalLanguageRequirements: item.additionalLanguageRequirements,
        title: item.title,
        degree: item.degree,
        durationSemesters: durationSemesters(item.durationOriginal),
        field: item.title,
        iscedF: null,
        tuition: {
          amount: item.tuition.amount,
          currency: item.tuition.currency,
          cycle: item.tuition.cycle,
          published: item.tuition.published,
          evidenceUrl: item.tuition.evidenceUrl,
          noteOriginal: item.tuition.noteOriginal ?? null,
          variants: item.tuition.variants ?? [],
        },
        applicationUrl: item.applicationUrl,
        verifiedAt,
        dataClass: "official_admissions_extract",
        lifecycleOverride: null,
      });
      for (const window of windowsOf(item)) {
        if (knownWindowIds.has(window.id)) continue;
        knownWindowIds.add(window.id);
        extraWindows.push(window);
      }
    }
    for (const item of snapshot.offerings) {
      for (const window of windowsOf(item)) {
        const url = window.applicationUrl || item.languageEvidenceUrl;
        if (!window.sourceEvidenceId || !url) continue;
        extraEvidence.push({
          id: window.sourceEvidenceId,
          url,
          note: { "zh-CN": snapshot.note, en: snapshot.note, cs: snapshot.note },
        });
      }
    }
    for (const [key, url] of Object.entries(snapshot.sources)) {
      extraEvidence.push({
        id: `${snapshot.institutionId}-${key}`,
        url,
        note: { "zh-CN": snapshot.note, en: snapshot.note, cs: snapshot.note },
      });
    }
  }

  return {
    generatedAt: tracers[0]?.generatedAt ?? base.generatedAt,
    dataClass: "ui_fixture",
    catalogKind: "browse_with_tracer",
    institutions,
    programmes: [...base.programmes, ...extraProgrammes],
    offerings: [...base.offerings, ...extraOfferings],
    windows: [...base.windows, ...extraWindows],
    jobs: base.jobs,
    evidence: [...base.evidence, ...extraEvidence],
  };
}

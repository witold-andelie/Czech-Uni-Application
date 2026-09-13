import type { ApplyPortal } from "./loadApplyPortals.ts";
import type { BaselineInstitution } from "./loadBaseline.ts";
import type { AdmissionsTracerSnapshot } from "./loadAdmissionsTracer.ts";
import { expandInventory, LISTED_HEI_IDS, overlayKey, type CompactInventory } from "./expandInventory.ts";
import { institutionFromBaseline } from "./mergeBrowseCatalog.ts";
import type { ApplicationWindow, CatalogSnapshot, Institution, Offering, Programme, ResearchJob, SourceEvidence } from "./types.ts";

export interface HarvestedJobsSnapshot {
  generatedAt: string;
  dataClass: "official_career_extract";
  jobs: ResearchJob[];
  windows: ApplicationWindow[];
  evidence?: SourceEvidence[];
}

export interface ReviewedAdmissionsSnapshot {
  generatedAt: string;
  offerings: Array<Offering & {
    candidateIds?: string[];
    applicationTargetKind?: Offering["applicationTargetKind"];
    generalApplyPortalUrl?: string | null;
    officialProgrammeUrl?: string | null;
    publicationStatus?: string;
    translationStatus?: string;
    fetchedAt?: string | null;
    factsReviewedAt?: string | null;
    titleOriginal?: string | null;
    sourceLanguage?: string | null;
  }>;
  windows: ApplicationWindow[];
  evidence: SourceEvidence[];
}

function isApprovedAdmissions(item: { publicationStatus?: string | null; translationStatus?: string | null } | null | undefined): boolean {
  return item?.publicationStatus === "approved" && item?.translationStatus === "verified";
}

function tracerOverlayKey(item: AdmissionsTracerSnapshot["offerings"][number], institutionId: string): string {
  const match = (item as { registerMatch?: { titleOriginal?: string; facultyName?: string; degree?: string; teachingLanguage?: string } }).registerMatch;
  const title = match?.titleOriginal || item.titleOriginal || item.title.en;
  const faculty = match?.facultyName || item.facultyOriginal || "";
  const degree = match?.degree || item.degree;
  const language = match?.teachingLanguage || item.teachingLanguages[0] || "";
  return overlayKey(institutionId, degree, language, title, faculty);
}

function offeringOverlayKey(offering: Offering, faculty: string): string {
  return overlayKey(offering.institutionId, offering.degree, offering.teachingLanguages[0] || "", offering.title.en, faculty);
}

export function buildBrowseCatalog(input: {
  compact: CompactInventory;
  tracers: AdmissionsTracerSnapshot[];
  jobs: HarvestedJobsSnapshot;
  baseline: BaselineInstitution[];
  portals: ApplyPortal[];
  reviewed?: ReviewedAdmissionsSnapshot | null;
}): CatalogSnapshot {
  const byId = new Map(input.baseline.map((item) => [item.id, item]));
  const employerIds = new Set(input.jobs.jobs.map((item) => item.employerId));
  const fromCompact = input.compact.schools.map((school) => school.id);
  const institutionIds = [...new Set([...LISTED_HEI_IDS, ...fromCompact, ...employerIds])];
  const institutions: Institution[] = [];
  for (const id of institutionIds) {
    const school = byId.get(id);
    if (!school) throw new Error(`Missing baseline for ${id}`);
    institutions.push(institutionFromBaseline(school));
  }

  const expanded = expandInventory(input.compact, input.portals);
  const tracerByKey = new Map<string, { snapshot: (typeof input.tracers)[number]; item: (typeof input.tracers)[number]["offerings"][number] }>();
  for (const snapshot of input.tracers) {
    for (const item of snapshot.offerings) {
      if (!isApprovedAdmissions(item)) continue;
      tracerByKey.set(tracerOverlayKey(item, snapshot.institutionId), { snapshot, item });
    }
  }
  const reviewedById = new Map((input.reviewed?.offerings ?? []).filter(isApprovedAdmissions).map((item) => [item.id, item]));
  const reviewedWindows = (input.reviewed?.windows ?? []).filter((item) => reviewedById.has(item.ownerId));
  const reviewedEvidence = input.reviewed?.evidence ?? [];

  const programmes: Programme[] = [];
  const offerings: Offering[] = [];
  const extraWindows: ApplicationWindow[] = [];
  const extraEvidence: SourceEvidence[] = [];
  const offeringAliases: Record<string, string> = {};
  const overlaidTracerIds = new Set<string>();

  for (let index = 0; index < expanded.offerings.length; index += 1) {
    const offering = expanded.offerings[index];
    const programme = expanded.programmes[index];
    const reviewed = reviewedById.get(offering.id);
    if (reviewed) {
      offeringAliases[reviewed.id] = offering.id;
      for (const candidateId of reviewed.candidateIds ?? []) offeringAliases[candidateId] = offering.id;
      programmes.push({
        ...programme,
        field: reviewed.field ?? reviewed.title,
      });
      offerings.push({
        ...offering,
        academicYear: reviewed.academicYear,
        languageEvidenceUrl: reviewed.languageEvidenceUrl,
        additionalLanguageRequirements: reviewed.additionalLanguageRequirements ?? [],
        title: reviewed.title,
        durationSemesters: reviewed.durationSemesters ?? offering.durationSemesters,
        field: reviewed.field ?? reviewed.title,
        iscedF: reviewed.iscedF ?? offering.iscedF,
        tuition: reviewed.tuition,
        applicationUrl: reviewed.applicationUrl,
        applicationTargetKind: reviewed.applicationTargetKind,
        generalApplyPortalUrl: reviewed.generalApplyPortalUrl,
        officialProgrammeUrl: reviewed.officialProgrammeUrl,
        sourceLanguage: reviewed.sourceLanguage,
        titleOriginal: reviewed.titleOriginal,
        fetchedAt: reviewed.fetchedAt,
        factsReviewedAt: reviewed.factsReviewedAt,
        verifiedAt: reviewed.factsReviewedAt ? reviewed.factsReviewedAt.slice(0, 10) : null,
        dataClass: "official_admissions_extract",
        lifecycleOverride: reviewed.lifecycleOverride ?? null,
      });
      extraWindows.push(...reviewedWindows.filter((item) => item.ownerId === offering.id));
      continue;
    }
    const hit = tracerByKey.get(offeringOverlayKey(offering, offering.field.en));
    if (hit) {
      const verifiedAt = (hit.item as { factsReviewedAt?: string | null }).factsReviewedAt?.slice(0, 10) || null;
      offeringAliases[hit.item.id] = offering.id;
      overlaidTracerIds.add(hit.item.id);
      programmes.push({
        ...programme,
        officialCode: hit.item.sisIdObor ?? programme.officialCode,
        field: hit.item.title,
      });
      offerings.push({
        ...offering,
        academicYear: hit.item.academicYear,
        languageEvidenceUrl: hit.item.languageEvidenceUrl,
        additionalLanguageRequirements: hit.item.additionalLanguageRequirements,
        title: hit.item.title,
        durationSemesters: durationFromOriginal(hit.item.durationOriginal) ?? offering.durationSemesters,
        field: hit.item.title,
        iscedF: offering.iscedF ?? (hit.item as { registerMatch?: { iscedF?: string } }).registerMatch?.iscedF ?? null,
        tuition: {
          amount: hit.item.tuition.amount,
          currency: hit.item.tuition.currency,
          cycle: hit.item.tuition.cycle,
          published: hit.item.tuition.published,
          evidenceUrl: hit.item.tuition.evidenceUrl,
          noteOriginal: hit.item.tuition.noteOriginal ?? null,
          variants: hit.item.tuition.variants ?? [],
        },
        applicationUrl: hit.item.applicationUrl,
        verifiedAt,
        dataClass: "official_admissions_extract",
        lifecycleOverride: null,
      });
      extraWindows.push(...tracerWindows(hit.item, offering.id));
      extraEvidence.push(...tracerEvidence(hit.snapshot, hit.item));
      continue;
    }
    programmes.push(programme);
    offerings.push(offering);
  }

  extraEvidence.push(...reviewedEvidence);
  for (const snapshot of input.tracers) {
    for (const item of snapshot.offerings) {
      if (!isApprovedAdmissions(item) || overlaidTracerIds.has(item.id)) continue;
      const programmeId = `prog-${item.id}`;
      programmes.push({
        id: programmeId,
        institutionId: item.institutionId,
        officialCode: item.sisIdObor ?? null,
        degree: item.degree,
        field: item.title,
        orientation: "unknown",
      });
      offerings.push({
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
        durationSemesters: durationFromOriginal(item.durationOriginal),
        field: item.title,
        iscedF: (item as { registerMatch?: { iscedF?: string } }).registerMatch?.iscedF ?? null,
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
        officialProgrammeUrl: item.languageEvidenceUrl,
        fetchedAt: snapshot.generatedAt,
        factsReviewedAt: (item as { factsReviewedAt?: string | null }).factsReviewedAt ?? null,
        verifiedAt: (item as { factsReviewedAt?: string | null }).factsReviewedAt?.slice(0, 10) || null,
        dataClass: "official_admissions_extract",
        lifecycleOverride: null,
      });
      extraWindows.push(...tracerWindows(item, item.id));
      extraEvidence.push(...tracerEvidence(snapshot, item));
    }
    for (const [key, url] of Object.entries(snapshot.sources)) {
      extraEvidence.push({
        id: `${snapshot.institutionId}-${key}`,
        url,
        note: { "zh-CN": snapshot.note, en: snapshot.note, cs: snapshot.note },
      });
    }
  }

  extraEvidence.push({
    id: "msmt-csplist-nine-hei",
    url: input.compact.sourceUrl,
    note: {
      "zh-CN": input.compact.note,
      en: input.compact.note,
      cs: input.compact.note,
    },
  });
  if (input.jobs.evidence) extraEvidence.push(...input.jobs.evidence);

  return {
    generatedAt: input.compact.generatedAt || input.jobs.generatedAt || input.tracers[0]?.generatedAt || "",
    dataClass: "official_register_extract",
    catalogKind: "browse_with_inventory",
    institutions,
    programmes,
    offerings,
    windows: [...extraWindows, ...input.jobs.windows],
    jobs: input.jobs.jobs,
    evidence: uniqueEvidence(extraEvidence),
    offeringAliases,
  };
}

function uniqueEvidence(rows: SourceEvidence[]): SourceEvidence[] {
  const map = new Map<string, SourceEvidence>();
  for (const row of rows) map.set(row.id, row);
  return [...map.values()];
}

function tracerWindows(
  item: AdmissionsTracerSnapshot["offerings"][number],
  ownerId: string,
): ApplicationWindow[] {
  const rows = item.windows?.length ? item.windows : item.window ? [item.window] : [];
  return rows.map((window) => ({
    id: window.id,
    ownerType: window.ownerType,
    ownerId,
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

function tracerEvidence(
  snapshot: AdmissionsTracerSnapshot,
  item: AdmissionsTracerSnapshot["offerings"][number],
): SourceEvidence[] {
  const note = { "zh-CN": snapshot.note, en: snapshot.note, cs: snapshot.note };
  const rows: SourceEvidence[] = [];
  const seen = new Set<string>();
  const add = (id: string, url: string | null | undefined) => {
    if (!id || !url || seen.has(id)) return;
    seen.add(id);
    rows.push({ id, url, note });
  };
  add(item.window?.sourceEvidenceId, item.languageEvidenceUrl || item.applicationUrl);
  for (const window of item.windows ?? []) {
    add(window.sourceEvidenceId, window.applicationUrl || item.languageEvidenceUrl);
  }
  for (const variant of item.tuition.variants ?? []) {
    add(variant.sourceEvidenceId, item.tuition.evidenceUrl || item.languageEvidenceUrl);
  }
  if (item.tuition.evidenceUrl) add(`${item.id}-tuition`, item.tuition.evidenceUrl);
  return rows;
}

function durationFromOriginal(value: string | null): number | null {
  if (!value) return null;
  const match = value.replace(",", ".").match(/(\d+(?:\.\d+)?)/);
  if (!match) return null;
  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) return null;
  if (/year|rok|let/i.test(value)) return Math.round(amount * 2);
  return Math.round(amount);
}

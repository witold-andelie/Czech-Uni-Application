import cuniTracerJson from "@published/admissions/cuni-mff-cs-tracer.json";
import muniTracerJson from "@published/admissions/muni-fi-tracer.json";
import type { AdditionalLanguageRequirement, ApplicationWindow, LocalizedText } from "./types.ts";

export interface TuitionVariant {
  amount: number;
  currency: string;
  cycle: "year" | "semester" | "programme" | null;
  applicantScopeOriginal: string | null;
  sourceEvidenceId: string;
}

export interface TracerTuition {
  amount: number | null;
  currency: string | null;
  cycle: "year" | "semester" | "programme" | null;
  published: boolean;
  evidenceUrl: string | null;
  unpublishedReason: string | null;
  noteOriginal?: string | null;
  variants: TuitionVariant[];
  doNotCollapseDualRates: boolean;
}

export interface TracerWindow extends ApplicationWindow {
  opensAtNotInferredFrom: string | null;
  opensAtFacultyNotePrecision: "month" | "date" | "datetime" | "unknown" | null;
  sisCannotApplyNow: boolean | null;
}

export interface TracerOffering {
  id: string;
  institutionId: string;
  facultyOriginal: string;
  facultySisOriginal: string | null;
  academicYear: string;
  teachingLanguages: string[];
  languageMode: "single" | "joint_required";
  languageEvidenceUrl: string;
  titleOriginal: string;
  title: LocalizedText;
  degree: "bachelor" | "master" | "doctorate" | "other" | "unknown";
  durationOriginal: string | null;
  formOriginal: string | null;
  sisIdObor?: string | null;
  additionalLanguageRequirements: AdditionalLanguageRequirement[];
  applicationUrl: string | null;
  applicationUrlNote: string | null;
  tuition: TracerTuition;
  applicationFee: {
    onlineOriginal: string | null;
    paperOriginal: string | null;
    amount: number | null;
    currency: string | null;
    isNotTuition: boolean;
    evidenceUrl: string | null;
    candidates?: { amount: number; currency: string; sourceEvidenceId: string }[];
  };
  window: TracerWindow;
  windows?: TracerWindow[];
  dataClass: "official_admissions_extract";
  catalogKind: "tracer_not_published";
  publicationStatus?: string;
  translationStatus?: string;
  factsReviewedAt?: string | null;
  fetchedAt?: string | null;
  sourceLanguage?: string | null;
}

export interface AdmissionsTracerSnapshot {
  generatedAt: string;
  dataClass: "official_admissions_extract";
  catalogKind: "tracer_not_published";
  institutionId: string;
  institutionOfficialName: string;
  msmtCode: string;
  facultyOriginal: string;
  note: string;
  sources: Record<string, string>;
  offerings: TracerOffering[];
}

const tracers: AdmissionsTracerSnapshot[] = [
  cuniTracerJson as AdmissionsTracerSnapshot,
  muniTracerJson as AdmissionsTracerSnapshot,
];

export function loadAllAdmissionsTracers(): AdmissionsTracerSnapshot[] {
  return tracers;
}

export function loadAdmissionsTracer(institutionId: string): AdmissionsTracerSnapshot | null {
  return tracers.find((item) => item.institutionId === institutionId) ?? null;
}

export function tracerWindowsForUi(offering: TracerOffering): ApplicationWindow[] {
  const rows = offering.windows?.length ? offering.windows : offering.window ? [offering.window] : [];
  return rows.map(tracerWindowForUi);
}

export function tracerWindowForUi(window: TracerWindow): ApplicationWindow {
  return {
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
  };
}

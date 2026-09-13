import type { ApplicationWindow, DataClass, DegreeLevel, LocalizedText, Ownership, Salary, Tuition, UiLocale, WindowStatus } from "./types";
import { t } from "./i18n.ts";

export function text(value: LocalizedText, locale: UiLocale): string {
  return value[locale];
}

export function formatDate(value: string | null, locale: UiLocale, precision: ApplicationWindow["datePrecision"]): string {
  if (!value) return t(locale, "status.unknown");
  const datePart = value.slice(0, 10);
  if (precision === "datetime") {
    return new Intl.DateTimeFormat(locale === "zh-CN" ? "zh-CN" : locale, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Europe/Prague",
    }).format(new Date(value));
  }
  return datePart;
}

function formatMoney(amount: number, currency: string, locale: UiLocale): string {
  return new Intl.NumberFormat(locale === "zh-CN" ? "zh-CN" : locale, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatTuition(tuition: Tuition, locale: UiLocale): string {
  if (!tuition.published || tuition.amount == null || !tuition.currency) {
    return t(locale, "status.unknown");
  }
  const amount = formatMoney(tuition.amount, tuition.currency, locale);
  if (!tuition.cycle) return amount;
  return `${amount} / ${t(locale, `tuition.cycle.${tuition.cycle}`)}`;
}

export function formatTracerTuition(
  tuition: Tuition & {
    variants?: { amount: number; currency: string; cycle: Tuition["cycle"]; applicantScopeOriginal: string | null }[];
  },
  locale: UiLocale,
): string[] {
  if (!tuition.published) return [t(locale, "tuition.unpublishedNotFree")];
  const variants = tuition.variants ?? [];
  if (variants.length) {
    return variants.map((item) => {
      const money = formatMoney(item.amount, item.currency, locale);
      const cycle = item.cycle ? ` / ${t(locale, `tuition.cycle.${item.cycle}`)}` : "";
      const scope = item.applicantScopeOriginal ? ` — ${item.applicantScopeOriginal}` : "";
      return `${money}${cycle}${scope}`;
    });
  }
  return [formatTuition(tuition, locale)];
}

export function salaryTaxKey(tax: Salary["tax"] | string | null | undefined): string {
  if (tax === "net") return "salary.tax.net";
  if (tax === "unknown" || tax === "unspecified") return "salary.tax.unknown";
  return "salary.tax.gross";
}

export function salaryCycleKey(cycle: string | null | undefined): string | null {
  if (!cycle) return null;
  if (cycle === "month" || cycle === "year" || cycle === "hour" || cycle === "day" || cycle === "week") return `salary.cycle.${cycle}`;
  if (cycle === "semester" || cycle === "programme") return `tuition.cycle.${cycle}`;
  return null;
}

export function formatSalary(salary: Salary, locale: UiLocale): string {
  if (salary.amount == null || !salary.currency) return t(locale, "status.unknown");
  const amount = formatMoney(salary.amount, salary.currency, locale);
  const cycleKey = salaryCycleKey(salary.cycle);
  const period = cycleKey ? ` / ${t(locale, cycleKey)}` : "";
  const tax = ` (${t(locale, salaryTaxKey(salary.tax))})`;
  return `${amount}${period}${tax}`;
}

export function jobSourceTitle(job: { originalText?: string | null; sourceLanguage?: string | null; title: LocalizedText }): string {
  if (job.originalText && job.originalText.trim()) return job.originalText;
  const lang = job.sourceLanguage;
  if (lang === "cs" && job.title.cs) return job.title.cs;
  if (lang === "en" && job.title.en) return job.title.en;
  if (lang === "zh-CN" && job.title["zh-CN"]) return job.title["zh-CN"];
  return job.title.cs || job.title.en || job.title["zh-CN"];
}

export function fieldSep(locale: UiLocale): string {
  return locale === "zh-CN" ? "：" : ": ";
}

export function degreeKey(degree: DegreeLevel): string {
  if (degree === "bachelor" || degree === "master" || degree === "doctorate") return `degree.${degree}`;
  if (degree === "other") return "degree.other";
  return "degree.unknown";
}

export function languageName(code: string, locale: UiLocale): string {
  if (code === "und") return t(locale, "lang.und");
  if (code === "en") return t(locale, "lang.en");
  if (code === "cs") return t(locale, "lang.cs");
  if (code === "de") return t(locale, "lang.de");
  if (code === "fr") return t(locale, "lang.fr");
  if (code === "ru") return t(locale, "lang.ru");
  if (code === "it") return t(locale, "lang.it");
  if (code === "pl") return t(locale, "lang.pl");
  return code;
}

export function extraContextKey(context: "admission" | "placement" | "clinical" | "other"): string {
  return `context.${context}`;
}

export function ownershipLabel(ownership: Ownership, locale: UiLocale): string {
  if (ownership === "public") return t(locale, "institution.public");
  if (ownership === "private") return t(locale, "institution.private");
  if (ownership === "state") return t(locale, "institution.state");
  return t(locale, "institution.unknown");
}

export function legalTypeLabel(legalType: "university" | "non_university" | "research_institute" | "unknown", locale: UiLocale): string {
  if (legalType === "university") return t(locale, "legalType.university");
  if (legalType === "non_university") return t(locale, "legalType.nonUniversity");
  if (legalType === "research_institute") return t(locale, "institution.researchOrg");
  return t(locale, "status.unknown");
}

export function dataClassKey(dataClass: DataClass): string {
  if (dataClass === "official_admissions_extract") return "tracer.card";
  if (dataClass === "official_register_extract") return "inventory.card";
  if (dataClass === "official_career_extract") return "jobs.card";
  if (dataClass === "published") return "source.verified";
  return "fixture.card";
}

export function recognitionKey(status: "listed" | "not_found" | "unverified"): string {
  if (status === "listed") return "recognition.listed";
  if (status === "not_found") return "recognition.notFound";
  return "recognition.unverified";
}

export function operatorListKey(status: "listed" | "absent" | null | undefined): string {
  return status === "listed" ? "recognition.operatorListed" : "recognition.operatorAbsent";
}

export function windowStatusLabel(status: WindowStatus | WindowSummaryStatus, locale: UiLocale): string {
  if (status === "open") return t(locale, "status.open");
  if (status === "upcoming") return t(locale, "status.upcoming");
  if (status === "closed") return t(locale, "status.closed");
  if (status === "conditional") return t(locale, "status.conditional");
  return t(locale, "status.unknown");
}

type WindowSummaryStatus = "open" | "upcoming" | "closed" | "unknown" | "conditional";

export function roundLabel(window: ApplicationWindow, locale: UiLocale): string {
  if (window.roundType === "rolling") return t(locale, "application.rolling");
  if (window.roundType === "supplementary") {
    const base = t(locale, "application.supplementary");
    return window.roundNumber ? `${t(locale, "application.roundN", { n: window.roundNumber })} · ${base}` : base;
  }
  if (window.roundNumber) return t(locale, "application.roundN", { n: window.roundNumber });
  if (window.roundLabelOriginal) return window.roundLabelOriginal;
  return t(locale, "application.roundUnknown");
}

export function windowRange(window: ApplicationWindow, locale: UiLocale): string {
  const opens = window.opensAt ? formatDate(window.opensAt, locale, window.datePrecision) : t(locale, "application.opensUnknown");
  const closes = window.closesAt ? formatDate(window.closesAt, locale, window.datePrecision) : t(locale, "status.unknown");
  return `${opens} — ${closes}`;
}

export function hostOf(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

export function teachingLanguageLabel(codes: string[], mode: "single" | "joint_required", locale: UiLocale): string {
  if (mode === "joint_required") return t(locale, "lang.joint");
  if (codes.length === 1 && codes[0] === "en") return t(locale, "teaching.en");
  if (codes.length === 1 && codes[0] === "cs") return t(locale, "teaching.cs");
  if (codes.length === 1) return languageName(codes[0], locale);
  return codes.map((code) => languageName(code, locale)).join(", ");
}

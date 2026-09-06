import type { ApplicationWindow, LocalizedText, Ownership, Tuition, UiLocale, WindowStatus } from "./types";
import { t } from "./i18n";

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

export function formatTuition(tuition: Tuition, locale: UiLocale): string {
  if (!tuition.published || tuition.amount == null || !tuition.currency) {
    return t(locale, "status.unknown");
  }
  const amount = new Intl.NumberFormat(locale === "zh-CN" ? "zh-CN" : locale, {
    style: "currency",
    currency: tuition.currency,
    maximumFractionDigits: 0,
  }).format(tuition.amount);
  if (!tuition.cycle) return amount;
  const cycle = { year: locale === "cs" ? "rok" : locale === "en" ? "year" : "年", semester: locale === "cs" ? "semestr" : locale === "en" ? "semester" : "学期", programme: locale === "cs" ? "program" : locale === "en" ? "programme" : "全程" }[tuition.cycle];
  return `${amount} / ${cycle}`;
}

export function ownershipLabel(ownership: Ownership, locale: UiLocale): string {
  if (ownership === "public") return t(locale, "institution.public");
  if (ownership === "private") return t(locale, "institution.private");
  if (ownership === "state") return t(locale, "institution.state");
  return t(locale, "institution.unknown");
}

export function recognitionKey(status: "listed" | "not_found" | "unverified"): string {
  if (status === "listed") return "recognition.listed";
  if (status === "not_found") return "recognition.notFound";
  return "recognition.unverified";
}

export function windowStatusLabel(status: WindowStatus, locale: UiLocale): string {
  if (status === "open") return t(locale, "status.open");
  if (status === "upcoming") return t(locale, "status.upcoming");
  if (status === "closed") return t(locale, "status.closed");
  if (status === "conditional") return t(locale, "status.conditional");
  return t(locale, "status.unknown");
}

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
  return codes.join(", ");
}

import cs from "../../../../locales/cs.json";
import en from "../../../../locales/en.json";
import zh from "../../../../locales/zh-CN.json";
import type { UiLocale } from "./types";
import { isLocale } from "./catalog";

const bundles: Record<UiLocale, Record<string, string>> = {
  "zh-CN": zh,
  en,
  cs,
};

export const LOCALES: UiLocale[] = ["zh-CN", "en", "cs"];

export function t(locale: UiLocale, key: string, vars: Record<string, string | number> = {}): string {
  const table = bundles[locale];
  const template = table[key];
  if (!template) {
    throw new Error(`Missing translation key ${key} for ${locale}`);
  }
  return Object.entries(vars).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), template);
}

export function localeFromParam(value: string | undefined): UiLocale {
  if (value && isLocale(value)) return value;
  return "zh-CN";
}

export function htmlLang(locale: UiLocale): string {
  if (locale === "zh-CN") return "zh-CN";
  return locale;
}

export function switchLocalePath(pathname: string, search: string, next: UiLocale): string {
  const parts = pathname.split("/");
  if (parts[1] && isLocale(parts[1])) parts[1] = next;
  else parts.splice(1, 0, next);
  return `${parts.join("/")}${search}`;
}

export function parseTeachingLanguage(value: string | null): "en" | "cs" | "all" | null {
  if (value === "en" || value === "cs" || value === "all") return value;
  return null;
}

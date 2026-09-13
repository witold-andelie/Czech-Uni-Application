// A80: public shortlist/comparison storage was removed by owner decision.
// The site is an anonymous browse experience; only browsing utilities
// (teaching-language choice, UI locale) persist.
const TEACHING_KEY = "czech-uni-apply:teachingLanguage";
const LOCALE_KEY = "czech-uni-apply:uiLocale";

export function saveTeachingLanguage(value: string): void {
  if (value !== "en" && value !== "cs" && value !== "all") return;
  localStorage.setItem(TEACHING_KEY, value);
}

export function readTeachingLanguage(): "en" | "cs" | "all" | null {
  if (typeof localStorage === "undefined") return null;
  const value = localStorage.getItem(TEACHING_KEY);
  if (value === "en" || value === "cs" || value === "all") return value;
  return null;
}

export function saveUiLocale(value: string): void {
  localStorage.setItem(LOCALE_KEY, value);
}

export function readUiLocale(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(LOCALE_KEY);
}

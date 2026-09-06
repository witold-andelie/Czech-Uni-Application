const SAVED_KEY = "czech-uni-apply:saved";
const COMPARE_KEY = "czech-uni-apply:compare";
const TEACHING_KEY = "czech-uni-apply:teachingLanguage";
const LOCALE_KEY = "czech-uni-apply:uiLocale";
const COMPARE_LIMIT = 4;

function readList(key: string): string[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function writeList(key: string, ids: string[]): void {
  localStorage.setItem(key, JSON.stringify([...new Set(ids)]));
}

export function loadSavedIds(): string[] {
  return readList(SAVED_KEY);
}

export function toggleSaved(id: string): string[] {
  const current = loadSavedIds();
  const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id];
  writeList(SAVED_KEY, next);
  return next;
}

export function loadCompareIds(): string[] {
  return readList(COMPARE_KEY);
}

export function toggleCompare(id: string): { ids: string[]; limited: boolean } {
  const current = loadCompareIds();
  if (current.includes(id)) {
    const ids = current.filter((item) => item !== id);
    writeList(COMPARE_KEY, ids);
    return { ids, limited: false };
  }
  if (current.length >= COMPARE_LIMIT) return { ids: current, limited: true };
  const ids = [...current, id];
  writeList(COMPARE_KEY, ids);
  return { ids, limited: false };
}

export function saveTeachingLanguage(value: string): void {
  localStorage.setItem(TEACHING_KEY, value);
}

export function saveUiLocale(value: string): void {
  localStorage.setItem(LOCALE_KEY, value);
}

export function readUiLocale(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(LOCALE_KEY);
}

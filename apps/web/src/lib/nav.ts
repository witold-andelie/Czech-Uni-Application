import { withBase } from "./base.ts";
import type { UiLocale } from "./types.ts";

export const NAV_ITEMS = [
  { path: "programmes", key: "nav.programmes", match: "/programmes" },
  { path: "institutions", key: "nav.institutions", match: "/institutions" },
  { path: "map", key: "nav.map", match: "/map" },
  { path: "research-jobs", key: "nav.research", match: "/research-jobs" },
  { path: "guides", key: "nav.guides", match: "/guides" },
] as const;

export function navHref(locale: UiLocale, path: string): string {
  return withBase(`/${locale}/${path}`);
}

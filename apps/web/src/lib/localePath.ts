import { isLocale } from "./catalog.ts";
import { pathnameWithoutBase, withBase } from "./base.ts";
import type { UiLocale } from "./types";

export function switchLocalePath(pathname: string, search: string, next: UiLocale): string {
  const parts = pathnameWithoutBase(pathname).split("/").filter(Boolean);
  if (parts.length === 0 || parts[0] === "404" || parts[1] === "404") {
    return withBase(`/${next}/${search}`);
  }
  if (isLocale(parts[0])) parts[0] = next;
  else parts.unshift(next);
  return withBase(`/${parts.join("/")}${search}`);
}

export function localeFromPathname(pathname: string): UiLocale {
  const segment = pathnameWithoutBase(pathname).split("/").filter(Boolean)[0];
  if (segment && isLocale(segment)) return segment;
  return "zh-CN";
}

/** Plain clicks replace the current history entry; modified clicks keep the native link. */
export function isModifiedLocaleClick(event: {
  button?: number;
  metaKey?: boolean;
  ctrlKey?: boolean;
  shiftKey?: boolean;
  altKey?: boolean;
}): boolean {
  return Boolean(
    (event.button != null && event.button !== 0) || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey,
  );
}

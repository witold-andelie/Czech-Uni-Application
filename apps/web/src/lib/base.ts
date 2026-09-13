/** B2: single base-aware URL helper for the GitHub Pages project site.
 * The literal `import.meta.env.BASE_URL` access below is required so Vite
 * statically replaces it in client bundles (optional chaining defeats the
 * replacement); plain-node contexts throw and fall back to root. */
function rawBase(): string {
  try {
    return import.meta.env.BASE_URL || "/";
  } catch {
    return "/";
  }
}

export const BASE_URL: string = rawBase().replace(/\/$/, "");

export function withBase(path: string): string {
  if (/^[a-z]+:\/\//i.test(path) || path.startsWith("//")) return path;
  if (BASE_URL && (path === BASE_URL || path.startsWith(BASE_URL + "/"))) return path;
  return `${BASE_URL}${path}`;
}

/** Strip the base prefix from a runtime pathname before parsing segments. */
export function pathnameWithoutBase(pathname: string): string {
  if (BASE_URL && pathname.startsWith(BASE_URL + "/")) return pathname.slice(BASE_URL.length);
  if (BASE_URL && pathname === BASE_URL) return "/";
  return pathname;
}

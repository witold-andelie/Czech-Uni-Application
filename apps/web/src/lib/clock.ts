import { parseInstant } from "./catalog";
import type { ApplicationWindow } from "./types";

function nextCalendarDayIso(dateStr: string): string {
  const parts = dateStr.slice(0, 10).split("-").map(Number);
  if (parts.length === 3 && !parts.some(Number.isNaN)) {
    const d = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] + 1));
    return d.toISOString().slice(0, 10);
  }
  return dateStr;
}

export function nextBoundaryMs(windows: ApplicationWindow[], now: Date): number | null {
  let soonest: number | null = null;
  const current = now.getTime();
  for (const window of windows) {
    const tz = window.timezone || "Europe/Prague";
    if (window.opensAt) {
      const stamp = window.opensAt;
      const ms = window.datePrecision === "date"
        ? parseInstant(`${stamp.slice(0, 10)}T00:00:00`, tz)
        : parseInstant(stamp, tz);
      if (Number.isFinite(ms) && ms > current && (soonest == null || ms < soonest)) {
        soonest = ms;
      }
    }
    if (window.closesAt) {
      const stamp = window.closesAt;
      const ms = window.datePrecision === "date"
        ? parseInstant(`${nextCalendarDayIso(stamp)}T00:00:00`, tz)
        : parseInstant(stamp, tz);
      if (Number.isFinite(ms) && ms > current && (soonest == null || ms < soonest)) {
        soonest = ms;
      }
    }
  }
  return soonest;
}

/** Recalculate window status on focus/visibility and with max 60s active refresh. */
export function subscribeNow(
  onTick: (now: Date) => void,
  windows: () => ApplicationWindow[] = () => [],
): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const fire = () => {
    const now = new Date();
    onTick(now);
    if (timer) clearTimeout(timer);
    const next = nextBoundaryMs(windows(), now);
    const wait = next == null ? 60_000 : Math.max(1_000, Math.min(next - now.getTime(), 60_000));
    timer = setTimeout(fire, wait);
  };
  const onVisible = () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
    fire();
  };
  fire();
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", onVisible);
  }
  if (typeof window !== "undefined") {
    window.addEventListener("focus", onVisible);
  }
  return () => {
    if (timer) clearTimeout(timer);
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisible);
    }
    if (typeof window !== "undefined") {
      window.removeEventListener("focus", onVisible);
    }
  };
}

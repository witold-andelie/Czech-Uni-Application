import { withBase } from "./base.ts";
import { jobOpportunityClosed } from "./catalog.ts";
import type { ApplicationWindow, CatalogSnapshot, ResearchJob } from "./types.ts";

export const SAFETY_STATUS_PATH = "/data/safety-status.json";
export const SAFETY_POLL_MS = 60_000;
/**
 * A76: when a NEW status generation is published with a timestamp older than
 * this, the status pipeline itself is publishing stale state and the client
 * reports it. The build-published baseline is exempt: with static hosting the
 * file legitimately ages with the immutable publication, and its vintage is
 * shown through the publication version on the page. Deliberately above the
 * five-minute propagation target.
 */
export const SAFETY_MAX_STATUS_AGE_MS = 30 * 60_000;

export type SafetyEntityStatus = "open" | "unknown" | "closed" | "expired" | "unavailable";
export type SafetyScope = "whole_opportunity" | "window";

export interface SafetyEntity {
  entityType: "research_job";
  entityId: string;
  status: SafetyEntityStatus;
  scope: SafetyScope;
  windowId?: string | null;
  observedSourceHash?: string | null;
  observedAt?: string | null;
  closedAt?: string | null;
  datePrecision?: string | null;
  reason?: string | null;
  evidenceUrl?: string | null;
  generation?: number;
  reopenEvidenceId?: string | null;
}

export interface SafetyOverlay {
  schemaVersion: number;
  generationId: string;
  publishedAt: string;
  sourceCheckedAt: string | null;
  statusPublishedAt: string;
  cacheMaxAgeSeconds: number;
  propagationTargetSeconds?: number;
  entities: SafetyEntity[];
}

export function emptySafetyOverlay(): SafetyOverlay {
  return {
    schemaVersion: 1,
    generationId: "s2026-09-12.0",
    publishedAt: "2026-09-12T00:00:00Z",
    sourceCheckedAt: null,
    statusPublishedAt: "2026-09-12T00:00:00Z",
    cacheMaxAgeSeconds: 60,
    propagationTargetSeconds: 300,
    entities: [],
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/**
 * A76: a generation id orders safety states. Comparison is numeric per date
 * and ordinal, never a lexical suffix sort ("s2026-09-12.10" is newer than
 * "s2026-09-12.9").
 */
export function safetyGenerationKey(generationId: string): [string, number] | null {
  const match = /^s(\d{4}-\d{2}-\d{2})\.(\d+)$/.exec(generationId);
  if (!match) return null;
  const ordinal = Number(match[2]);
  if (!Number.isFinite(ordinal)) return null;
  return [match[1], ordinal];
}

export function isGenerationAtLeast(candidate: [string, number], accepted: [string, number]): boolean {
  if (candidate[0] !== accepted[0]) return candidate[0] > accepted[0];
  return candidate[1] >= accepted[1];
}

export function parseSafetyOverlay(value: unknown): SafetyOverlay | null {
  if (!isRecord(value)) return null;
  if (value.schemaVersion !== 1) return null;
  if (typeof value.generationId !== "string" || !/^s\d{4}-\d{2}-\d{2}\.\d+$/.test(value.generationId)) return null;
  if (typeof value.publishedAt !== "string" || !value.publishedAt) return null;
  if (typeof value.statusPublishedAt !== "string" || !value.statusPublishedAt) return null;
  // A76: entities are validated atomically. Silently dropping a malformed
  // record would turn a payload carrying closures into a "valid" empty
  // overlay and could erase a public closure on the next poll.
  if (!Array.isArray(value.entities)) return null;
  const parsed: SafetyEntity[] = [];
  for (const item of value.entities) {
    if (!isRecord(item) || item.entityType !== "research_job" || typeof item.entityId !== "string" || !item.entityId) {
      return null;
    }
    const status = item.status;
    if (status !== "open" && status !== "unknown" && status !== "closed" && status !== "expired" && status !== "unavailable") {
      return null;
    }
    if (item.scope !== "whole_opportunity" && item.scope !== "window") {
      return null;
    }
    const scope = item.scope === "window" ? "window" : "whole_opportunity";
    parsed.push({
      entityType: "research_job",
      entityId: item.entityId,
      status,
      scope,
      windowId: typeof item.windowId === "string" ? item.windowId : null,
      observedSourceHash: typeof item.observedSourceHash === "string" ? item.observedSourceHash : null,
      observedAt: typeof item.observedAt === "string" ? item.observedAt : null,
      closedAt: typeof item.closedAt === "string" ? item.closedAt : null,
      datePrecision: typeof item.datePrecision === "string" ? item.datePrecision : null,
      reason: typeof item.reason === "string" ? item.reason : null,
      evidenceUrl: typeof item.evidenceUrl === "string" ? item.evidenceUrl : null,
      generation: typeof item.generation === "number" ? item.generation : undefined,
      reopenEvidenceId: typeof item.reopenEvidenceId === "string" ? item.reopenEvidenceId : null,
    });
  }
  return {
    schemaVersion: 1,
    generationId: value.generationId,
    publishedAt: typeof value.publishedAt === "string" ? value.publishedAt : "",
    sourceCheckedAt: typeof value.sourceCheckedAt === "string" ? value.sourceCheckedAt : null,
    statusPublishedAt: typeof value.statusPublishedAt === "string" ? value.statusPublishedAt : "",
    cacheMaxAgeSeconds: typeof value.cacheMaxAgeSeconds === "number" ? value.cacheMaxAgeSeconds : 60,
    propagationTargetSeconds: typeof value.propagationTargetSeconds === "number" ? value.propagationTargetSeconds : 300,
    entities: parsed,
  };
}

const CLOSED = new Set<SafetyEntityStatus>(["closed", "expired"]);

export function overlayRecordsFor(overlay: SafetyOverlay | null | undefined, entityId: string): SafetyEntity[] {
  if (!overlay) return [];
  return overlay.entities.filter((item) => item.entityId === entityId);
}

export function overlayWholeClosed(overlay: SafetyOverlay | null | undefined, entityId: string): boolean {
  return overlayRecordsFor(overlay, entityId).some(
    (item) => item.scope === "whole_opportunity" && CLOSED.has(item.status),
  );
}

export function applySafetyToJob(job: ResearchJob, overlay: SafetyOverlay | null | undefined): ResearchJob {
  const records = overlayRecordsFor(overlay, job.id);
  if (!records.length) return job;
  let next = job;
  for (const record of records) {
    if (record.scope !== "whole_opportunity") continue;
    if (CLOSED.has(record.status)) {
      next = {
        ...next,
        wholeOpportunityClosed: true,
        lifecycleStatus: record.status === "expired" ? "expired" : "closed",
      };
    } else if (record.status === "unavailable") {
      next = { ...next, lifecycleStatus: "unavailable" };
    }
  }
  return next;
}

export function applySafetyToWindow(window: ApplicationWindow, overlay: SafetyOverlay | null | undefined): ApplicationWindow {
  const ownerId = window.ownerId;
  const records = overlayRecordsFor(overlay, ownerId);
  if (!records.length) return window;
  const whole = records.some((item) => item.scope === "whole_opportunity" && CLOSED.has(item.status));
  const thisWindow = records.some(
    (item) => item.scope === "window" && item.windowId === window.id && CLOSED.has(item.status),
  );
  if (!whole && !thisWindow) return window;
  return { ...window, status: "closed" };
}

export function applySafetyOverlay(catalog: CatalogSnapshot, overlay: SafetyOverlay | null | undefined): CatalogSnapshot {
  if (!overlay || overlay.entities.length === 0) return catalog;
  return {
    ...catalog,
    jobs: catalog.jobs.map((job) => applySafetyToJob(job, overlay)),
    windows: catalog.windows.map((window) => applySafetyToWindow(window, overlay)),
  };
}

export function jobApplyDisabled(job: ResearchJob, overlay: SafetyOverlay | null | undefined): boolean {
  return jobOpportunityClosed(applySafetyToJob(job, overlay));
}

export type SafetyListener = (
  overlay: SafetyOverlay | null,
  meta: { stale: boolean; error?: string },
) => void;

export interface SafetyPollOptions {
  now?: () => number;
  /** Heartbeat older than this (ms) is reported stale even when fetched OK. */
  maxStatusAgeMs?: number;
}

/** Stable content digest binding an overlay to its generation id (A87). */
export function overlayContentDigest(overlay: SafetyOverlay): string {
  const entities = [...overlay.entities]
    .map((entity) => JSON.stringify({
      entityId: entity.entityId,
      status: entity.status,
      scope: entity.scope,
      windowId: entity.windowId ?? null,
      observedAt: entity.observedAt ?? null,
      closedAt: entity.closedAt ?? null,
      reopenEvidenceId: entity.reopenEvidenceId ?? null,
    }))
    .sort();
  return JSON.stringify({
    generationId: overlay.generationId,
    sourceCheckedAt: overlay.sourceCheckedAt,
    statusPublishedAt: overlay.statusPublishedAt,
    entities,
  });
}

/**
 * A87: freshness comes from the source-check heartbeat (sourceCheckedAt) —
 * an independently advancing verification timestamp, not from transport
 * success. Null, unparseable, or future heartbeats are stale; a heartbeat
 * older than the threshold is stale. Static closure content may legitimately
 * persist for days; its age is reported honestly instead of being hidden.
 */
export function heartbeatStale(
  overlay: SafetyOverlay,
  nowMs: number,
  maxStatusAgeMs: number,
): boolean {
  const checked = overlay.sourceCheckedAt ? Date.parse(overlay.sourceCheckedAt) : Number.NaN;
  if (Number.isNaN(checked)) return true;
  // Future timestamps beyond a small clock-skew allowance are invalid.
  if (checked > nowMs + 5 * 60_000) return true;
  return nowMs - checked > maxStatusAgeMs;
}

/**
 * A87: polling keeps an immutable generation/content binding. Responses older
 * than the accepted generation never replace it. An equal generation with
 * conflicting content is an error: the accepted closures are preserved and
 * the conflict is signalled. An identical redelivery never clears a
 * stale-source condition. Fetch failures keep the last accepted closures with
 * stale=true.
 */
export function subscribeSafetyOverlay(
  onChange: SafetyListener,
  fetchImpl: typeof fetch = fetch,
  intervalMs = SAFETY_POLL_MS,
  options: SafetyPollOptions = {},
): () => void {
  const nowImpl = options.now ?? (() => Date.now());
  const maxStatusAgeMs = options.maxStatusAgeMs ?? SAFETY_MAX_STATUS_AGE_MS;
  let accepted: SafetyOverlay | null = null;
  let acceptedKey: [string, number] | null = null;
  let acceptedDigest: string | null = null;
  let lastStale = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let cancelled = false;

  const fire = (overlay: SafetyOverlay | null, stale: boolean, error?: string) => {
    if (cancelled) return;
    lastStale = stale;
    onChange(overlay, { stale, ...(error ? { error } : {}) });
  };

  const poll = () => {
    void (async () => {
      try {
        const response = await fetchImpl(withBase(SAFETY_STATUS_PATH), { cache: "no-store" });
        if (!response.ok) throw new Error(`safety ${response.status}`);
        const parsed = parseSafetyOverlay(await response.json());
        if (!parsed) throw new Error("safety payload invalid");
        const key = safetyGenerationKey(parsed.generationId);
        if (!key) throw new Error("safety generation invalid");
        if (acceptedKey !== null && !isGenerationAtLeast(key, acceptedKey)) {
          // Older than the accepted high-water mark: ignore the response.
          return;
        }
        const acceptedKeyNonNull = acceptedKey;
        const isSameGeneration =
          acceptedKeyNonNull !== null &&
          key[0] === acceptedKeyNonNull[0] &&
          key[1] === acceptedKeyNonNull[1];
        if (isSameGeneration) {
          const digest = overlayContentDigest(parsed);
          if (acceptedDigest !== null && digest !== acceptedDigest) {
            // A87: conflicting content under an already-accepted generation
            // must never silently drop closures from the accepted overlay.
            fire(accepted, true, "generation-content-conflict");
            return;
          }
          // A long session polling an unchanged body must still age into
          // staleness: the heartbeat is re-evaluated against the wall clock on
          // every identical redelivery. Staleness is monotonic within one
          // generation — a repeated body can turn stale but never clear it;
          // only a newer generation with an advanced heartbeat recovers.
          fire(
            accepted,
            lastStale || heartbeatStale(accepted!, nowImpl(), maxStatusAgeMs),
          );
          return;
        }
        accepted = parsed;
        acceptedKey = key;
        acceptedDigest = overlayContentDigest(parsed);
        fire(parsed, heartbeatStale(parsed, nowImpl(), maxStatusAgeMs));
      } catch {
        // Request failure is not an empty verified overlay. With no prior
        // accepted generation the status is unavailable (stale); afterwards
        // the last accepted closure is retained with stale=true.
        fire(accepted, true);
      } finally {
        if (!cancelled) timer = setTimeout(poll, intervalMs);
      }
    })();
  };

  const onVisible = () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
    if (timer) clearTimeout(timer);
    poll();
  };

  poll();
  if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVisible);
  if (typeof window !== "undefined") window.addEventListener("focus", onVisible);
  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVisible);
    if (typeof window !== "undefined") window.removeEventListener("focus", onVisible);
  };
}

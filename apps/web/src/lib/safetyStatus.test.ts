import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { canApply, defaultJobFilterQuery, filterJobs, findJob, isPublicJob, jobOpportunityClosed } from "./catalog.ts";
import {
  applySafetyOverlay,
  emptySafetyOverlay,
  isGenerationAtLeast,
  parseSafetyOverlay,
  safetyGenerationKey,
  subscribeSafetyOverlay,
  type SafetyOverlay,
} from "./safetyStatus.ts";
import type { CatalogSnapshot } from "./types.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const catalog = JSON.parse(readFileSync(resolve(root, "data/fixtures/catalog.json"), "utf8")) as CatalogSnapshot;
const now = new Date("2026-09-06T12:00:00Z");

function overlayFor(id: string, extra: Partial<SafetyOverlay["entities"][number]> = {}): SafetyOverlay {
  // A76: a freshly published status, so the age threshold never fires in tests
  // that do not exercise it.
  const fresh = new Date(Date.now() - 30_000).toISOString();
  return {
    schemaVersion: 1,
    generationId: "s2026-09-12.1",
    publishedAt: fresh,
    sourceCheckedAt: fresh,
    statusPublishedAt: fresh,
    cacheMaxAgeSeconds: 60,
    entities: [
      {
        entityType: "research_job",
        entityId: id,
        status: "closed",
        scope: "whole_opportunity",
        reason: "page_announced_closure",
        ...extra,
      },
    ],
  };
}

describe("safety overlay", () => {
  it("parses the checked-in empty overlay", () => {
    const raw = JSON.parse(readFileSync(resolve(root, "data/published/safety-status.json"), "utf8"));
    const parsed = parseSafetyOverlay(raw);
    assert.ok(parsed);
    assert.equal(parsed.generationId, emptySafetyOverlay().generationId);
    assert.equal(parsed.entities.length, 0);
  });

  it("hides a listed job from public results but keeps the saved/detail tombstone", () => {
    const open = catalog.jobs.find((item) => item.id === "job-master-paid");
    assert.ok(open);
    const closedCatalog = applySafetyOverlay(catalog, overlayFor(open.id));
    const listed = filterJobs(closedCatalog, defaultJobFilterQuery({ masterEligible: false, track: "all" }), now, "zh-CN");
    assert.equal(listed.page.some((item) => item.job.id === open.id), false);
    const detail = findJob(closedCatalog, open.id, now);
    assert.ok(detail);
    assert.equal(jobOpportunityClosed(detail.job), true);
    assert.equal(canApply(detail.summary), false);
    assert.equal(isPublicJob(detail.job, detail.summary), false);
  });

  it("closes one window without closing a later open round", () => {
    const job = catalog.jobs.find((item) => item.id === "job-master-paid");
    assert.ok(job);
    const windows = catalog.windows.filter((item) => item.ownerId === job.id);
    assert.ok(windows.length);
    const overlay: SafetyOverlay = {
      schemaVersion: 1,
      generationId: "s2026-09-12.2",
      publishedAt: "2026-09-12T15:00:00Z",
      sourceCheckedAt: "2026-09-12T15:00:00Z",
      statusPublishedAt: "2026-09-12T15:00:00Z",
      cacheMaxAgeSeconds: 60,
      entities: [
        {
          entityType: "research_job",
          entityId: job.id,
          status: "closed",
          scope: "window",
          windowId: windows[0].id,
        },
      ],
    };
    const next = applySafetyOverlay(catalog, overlay);
    const updated = next.windows.find((item) => item.id === windows[0].id);
    assert.equal(updated?.status, "closed");
    assert.equal(next.jobs.find((item) => item.id === job.id)?.wholeOpportunityClosed, false);
  });

  it("keeps last-known overlay when the status endpoint fails", async () => {
    const first: SafetyOverlay = overlayFor("job-master-paid");
    let calls = 0;
    const fetchImpl = async () => {
      calls += 1;
      if (calls === 1) {
        return new Response(JSON.stringify(first), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response("", { status: 503 });
    };
    const seen: Array<{ stale: boolean; generation: string | null }> = [];
    await new Promise<void>((resolve, reject) => {
      const stop = subscribeSafetyOverlay(
        (overlay, meta) => {
          seen.push({ stale: meta.stale, generation: overlay?.generationId ?? null });
          if (seen.length >= 2) {
            stop();
            resolve();
          }
        },
        fetchImpl as unknown as typeof fetch,
        10,
      );
      setTimeout(() => {
        stop();
        reject(new Error("safety poll timed out"));
      }, 1000);
    });
    assert.equal(seen[0]?.stale, false);
    assert.equal(seen[0]?.generation, "s2026-09-12.1");
    assert.equal(seen[1]?.stale, true);
    assert.equal(seen[1]?.generation, "s2026-09-12.1");
  });
});

// ---------------------------------------------------------------------------
// A76: ordered generations, atomic validation and honest failure semantics.
// ---------------------------------------------------------------------------

function overlayWithGeneration(
  generationId: string,
  entities: SafetyOverlay["entities"],
): SafetyOverlay {
  const fresh = new Date(Date.now() - 30_000).toISOString();
  return {
    schemaVersion: 1,
    generationId,
    publishedAt: fresh,
    sourceCheckedAt: fresh,
    statusPublishedAt: fresh,
    cacheMaxAgeSeconds: 60,
    entities,
  };
}

describe("safety overlay ordering (A76)", () => {
  it("orders generations numerically, not lexically", () => {
    assert.ok(isGenerationAtLeast(["2026-09-12", 10], ["2026-09-12", 9]));
    assert.ok(!isGenerationAtLeast(["2026-09-12", 9], ["2026-09-12", 10]));
    assert.ok(isGenerationAtLeast(["2026-09-13", 0], ["2026-09-12", 99]));
    assert.deepEqual(safetyGenerationKey("s2026-09-12.4"), ["2026-09-12", 4]);
  });

  it("ignores an older empty generation that arrives after a closure", async () => {
    const closure = overlayWithGeneration("s2026-09-12.2", [
      { entityType: "research_job", entityId: "job-master-paid", status: "closed", scope: "whole_opportunity" },
    ]);
    const olderEmpty = overlayWithGeneration("s2026-09-12.0", []);
    const responses = [closure, olderEmpty];
    let call = 0;
    const fetchImpl = async () => {
      const body = responses[Math.min(call, responses.length - 1)];
      call += 1;
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    const seen: Array<{ stale: boolean; entities: number }> = [];
    const stop = subscribeSafetyOverlay(
      (overlay, meta) => {
        seen.push({ stale: meta.stale, entities: overlay?.entities.length ?? -1 });
      },
      fetchImpl as unknown as typeof fetch,
      10,
    );
    await new Promise((resolveTimer) => setTimeout(resolveTimer, 200));
    stop();
    assert.ok(seen.length >= 1, "expected at least the first accepted generation to fire");
    assert.equal(seen[0].entities, 1);
    // Every later poll returns the older empty generation; it must be ignored
    // and must not erase or re-fire the accepted closure.
    assert.ok(seen.every((item) => item.entities === 1));
  });

  it("rejects a payload whose entity records are malformed instead of treating it as empty", () => {
    const broken = {
      schemaVersion: 1,
      generationId: "s2026-09-12.3",
      publishedAt: new Date().toISOString(),
      statusPublishedAt: new Date().toISOString(),
      cacheMaxAgeSeconds: 60,
      entities: [{ entityType: "research_job", entityId: "job-x", status: "shut" }],
    };
    assert.equal(parseSafetyOverlay(broken), null);
    assert.equal(parseSafetyOverlay({ ...broken, entities: "nope" }), null);
    assert.equal(parseSafetyOverlay({ ...broken, statusPublishedAt: "" }), null);
  });

  it("reports the first fetch failure as unavailable (stale), not as a valid empty overlay", async () => {
    const fetchImpl = async () => new Response("", { status: 503 });
    const seen: Array<{ overlay: SafetyOverlay | null; stale: boolean }> = [];
    await new Promise<void>((resolve) => {
      const stop = subscribeSafetyOverlay(
        (overlay, meta) => {
          seen.push({ overlay, stale: meta.stale });
          stop();
          resolve();
        },
        fetchImpl as unknown as typeof fetch,
        10,
      );
      setTimeout(() => {
        stop();
        resolve();
      }, 300);
    });
    assert.equal(seen[0]?.overlay, null);
    assert.equal(seen[0]?.stale, true);
  });

  it("reports a day-old initial heartbeat as stale, not as fresh", async () => {
    const dayOld = overlayWithGeneration("s2026-09-12.1", [
      { entityType: "research_job", entityId: "job-master-paid", status: "closed", scope: "whole_opportunity" },
    ]);
    dayOld.sourceCheckedAt = new Date(Date.now() - 24 * 60 * 60_000).toISOString();
    const fetchImpl = async () =>
      new Response(JSON.stringify(dayOld), { status: 200, headers: { "Content-Type": "application/json" } });
    const seen: Array<{ stale: boolean; closed: boolean }> = [];
    await new Promise<void>((resolve) => {
      const stop = subscribeSafetyOverlay(
        (overlay, meta) => {
          seen.push({
            stale: meta.stale,
            closed: overlay?.entities.some((item) => item.status === "closed") ?? false,
          });
          stop();
          resolve();
        },
        fetchImpl as unknown as typeof fetch,
        10,
      );
      setTimeout(() => {
        stop();
        resolve();
      }, 300);
    });
    assert.equal(seen[0]?.stale, true, "day-old source-check heartbeat is stale from the first reply");
    assert.equal(seen[0]?.closed, true, "closure content is still delivered");
  });

  it("never lets equal-generation conflicting content erase closures", async () => {
    const closure = overlayWithGeneration("s2026-09-12.2", [
      { entityType: "research_job", entityId: "job-master-paid", status: "closed", scope: "whole_opportunity" },
    ]);
    // Same generation id, conflicting content: the closed entity is gone.
    const conflicting = overlayWithGeneration("s2026-09-12.2", []);
    const responses = [closure, conflicting];
    let call = 0;
    const fetchImpl = async () => {
      const body = responses[Math.min(call, responses.length - 1)];
      call += 1;
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    const seen: Array<{ stale: boolean; closed: boolean; error?: string }> = [];
    await new Promise<void>((resolve) => {
      const stop = subscribeSafetyOverlay(
        (overlay, meta) => {
          seen.push({
            stale: meta.stale,
            closed: overlay?.entities.some((item) => item.entityId === "job-master-paid" && item.status === "closed") ?? false,
            error: meta.error,
          });
          if (seen.length >= 2) {
            stop();
            resolve();
          }
        },
        fetchImpl as unknown as typeof fetch,
        10,
      );
      setTimeout(() => {
        stop();
        resolve();
      }, 300);
    });
    assert.equal(seen[0]?.closed, true);
    assert.equal(seen[1]?.closed, true, "accepted closure must survive a conflicting same-generation reply");
    assert.equal(seen[1]?.stale, true);
    assert.equal(seen[1]?.error, "generation-content-conflict");
  });

  it("keeps a delayed higher generation stale on identical repeats", async () => {
    const closure = overlayWithGeneration("s2026-09-12.2", [
      { entityType: "research_job", entityId: "job-master-paid", status: "closed", scope: "whole_opportunity" },
    ]);
    closure.sourceCheckedAt = new Date(Date.now() - 6 * 60 * 60_000).toISOString();
    const responses = [closure, closure];
    let call = 0;
    const fetchImpl = async () => {
      const body = responses[Math.min(call, responses.length - 1)];
      call += 1;
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    const seen: Array<{ stale: boolean }> = [];
    await new Promise<void>((resolve) => {
      const stop = subscribeSafetyOverlay(
        (_overlay, meta) => {
          seen.push({ stale: meta.stale });
          if (seen.length >= 2) {
            stop();
            resolve();
          }
        },
        fetchImpl as unknown as typeof fetch,
        10,
      );
      setTimeout(() => {
        stop();
        resolve();
      }, 300);
    });
    assert.equal(seen[0]?.stale, true, "old heartbeat is stale");
    assert.equal(seen[1]?.stale, true, "an identical repeated body cannot clear the stale-source condition");
  });

  it("ages an identical repeated response into staleness after the threshold", async () => {
    // Pre-launch fix: the first delivery is fresh, but a session polling the
    // same body for over 30 minutes must still report a stale source recheck.
    let clock = 1_000_000;
    const fresh = overlayWithGeneration("s2026-09-12.2", [
      { entityType: "research_job", entityId: "job-master-paid", status: "closed", scope: "whole_opportunity" },
    ]);
    fresh.sourceCheckedAt = new Date(clock - 60_000).toISOString();
    const fetchImpl = async () =>
      new Response(JSON.stringify(fresh), { status: 200, headers: { "Content-Type": "application/json" } });
    const seen: Array<{ stale: boolean }> = [];
    await new Promise<void>((resolve) => {
      const stop = subscribeSafetyOverlay(
        (_overlay, meta) => {
          seen.push({ stale: meta.stale });
          clock += 31 * 60_000; // each poll arrives 31 minutes later
          if (seen.length >= 2) {
            stop();
            resolve();
          }
        },
        fetchImpl as unknown as typeof fetch,
        10,
        { now: () => clock },
      );
      setTimeout(() => {
        stop();
        resolve();
      }, 400);
    });
    assert.equal(seen[0]?.stale, false, "first delivery is fresh");
    assert.equal(seen[1]?.stale, true, "the unchanged body ages into staleness");
  });

  it("recovers staleness only when the heartbeat genuinely advances", async () => {
    const stale = overlayWithGeneration("s2026-09-12.2", []);
    stale.sourceCheckedAt = new Date(Date.now() - 6 * 60 * 60_000).toISOString();
    const fresh = overlayWithGeneration("s2026-09-12.3", []);
    const responses = [stale, fresh];
    let call = 0;
    const fetchImpl = async () => {
      const body = responses[Math.min(call, responses.length - 1)];
      call += 1;
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    const seen: Array<{ stale: boolean }> = [];
    await new Promise<void>((resolve) => {
      const stop = subscribeSafetyOverlay(
        (_overlay, meta) => {
          seen.push({ stale: meta.stale });
          if (seen.length >= 2) {
            stop();
            resolve();
          }
        },
        fetchImpl as unknown as typeof fetch,
        10,
      );
      setTimeout(() => {
        stop();
        resolve();
      }, 300);
    });
    assert.equal(seen[0]?.stale, true);
    assert.equal(seen[1]?.stale, false, "an advanced heartbeat with a new generation recovers");
  });

  it("accepts a newer reviewed generation that reopens the job", async () => {
    const closure = overlayWithGeneration("s2026-09-12.2", [
      { entityType: "research_job", entityId: "job-master-paid", status: "closed", scope: "whole_opportunity" },
    ]);
    const reopened = overlayWithGeneration("s2026-09-12.3", [
      {
        entityType: "research_job",
        entityId: "job-master-paid",
        status: "open",
        scope: "whole_opportunity",
        reopenEvidenceId: "ev-reopen-1",
      },
    ]);
    const responses = [closure, reopened];
    let call = 0;
    const fetchImpl = async () => {
      const body = responses[Math.min(call, responses.length - 1)];
      call += 1;
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    const seen: Array<{ status: string | null }> = [];
    await new Promise<void>((resolve) => {
      const stop = subscribeSafetyOverlay(
        (overlay) => {
          seen.push({ status: overlay?.entities[0]?.status ?? null });
          if (seen.length >= 2) {
            stop();
            resolve();
          }
        },
        fetchImpl as unknown as typeof fetch,
        10,
      );
      setTimeout(() => {
        stop();
        resolve();
      }, 300);
    });
    assert.equal(seen[0]?.status, "closed");
    assert.equal(seen[1]?.status, "open");
  });
});

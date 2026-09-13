import { withBase } from "./base.ts";
import { buildBrowseCatalog } from "./buildBrowseCatalog.ts";
import { EMPTY_COMPACT, type CompactInventory } from "./expandInventory.ts";
import { loadAllAdmissionsTracers } from "./loadAdmissionsTracer.ts";
import { loadApplyPortals } from "./loadApplyPortals.ts";
import { loadBaseline } from "./loadBaseline.ts";
import { loadNineHeiJobs } from "./loadNineHeiJobs.ts";
import { loadReviewedOfferings } from "./loadReviewedOfferings.ts";
import { loadPublishedManifest } from "./loadPublishedManifest.ts";
import type { CatalogSnapshot } from "./types.ts";

function inputs() {
  return {
    tracers: loadAllAdmissionsTracers(),
    jobs: loadNineHeiJobs(),
    baseline: loadBaseline().institutions,
    portals: loadApplyPortals().institutions,
    reviewed: loadReviewedOfferings(),
  };
}

export function loadCatalogShell(): CatalogSnapshot {
  return buildBrowseCatalog({ compact: EMPTY_COMPACT, ...inputs() });
}

export function catalogFromInventory(compact: CompactInventory): CatalogSnapshot {
  return buildBrowseCatalog({ compact, ...inputs() });
}

export async function fetchInventoryCatalog(): Promise<CatalogSnapshot> {
  const version = loadPublishedManifest().version;
  const response = await fetch(withBase(`/data/published/${encodeURIComponent(version)}/browse/nine-hei-inventory.json`));
  if (!response.ok) throw new Error(`inventory ${response.status}`);
  const compact = (await response.json()) as CompactInventory;
  return catalogFromInventory(compact);
}

import compactJson from "@published/browse/nine-hei-inventory.json";
import { buildBrowseCatalog } from "./buildBrowseCatalog.ts";
import type { CompactInventory } from "./expandInventory.ts";
import { loadAllAdmissionsTracers } from "./loadAdmissionsTracer.ts";
import { loadApplyPortals } from "./loadApplyPortals.ts";
import { loadBaseline } from "./loadBaseline.ts";
import { loadNineHeiJobs } from "./loadNineHeiJobs.ts";
import { loadReviewedOfferings } from "./loadReviewedOfferings.ts";
import catalog from "../../../../data/fixtures/catalog.json";
import type { CatalogSnapshot } from "./types.ts";

let cached: CatalogSnapshot | null = null;

export function loadFixtureCatalog(): CatalogSnapshot {
  return catalog as CatalogSnapshot;
}

export function loadCatalog(): CatalogSnapshot {
  if (cached) return cached;
  cached = buildBrowseCatalog({
    compact: compactJson as CompactInventory,
    tracers: loadAllAdmissionsTracers(),
    jobs: loadNineHeiJobs(),
    baseline: loadBaseline().institutions,
    portals: loadApplyPortals().institutions,
    reviewed: loadReviewedOfferings(),
  });
  return cached;
}

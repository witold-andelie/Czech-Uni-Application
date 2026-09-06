import catalog from "../../../../data/fixtures/catalog.json";
import type { CatalogSnapshot } from "./types";

export function loadCatalog(): CatalogSnapshot {
  return catalog as CatalogSnapshot;
}

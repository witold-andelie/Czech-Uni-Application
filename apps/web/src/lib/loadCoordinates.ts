import coordsJson from "@published/browse/hei-coordinates.json";
import outlineJson from "@published/browse/czechia-outline.json";
import basemapJson from "@published/browse/czechia-basemap.json";
import type { BaselineInstitution } from "./loadBaseline.ts";
import {
  attachCoordinates,
  geojsonToPath,
  type CoordinateMatch,
  type CoordinateRecord,
  type MapCity,
  type MapRegion,
  type MappedPoint,
} from "./mapProjection.ts";

export interface CoordinatesSnapshot {
  generatedAt: string;
  dataClass: string;
  catalogKind: string;
  sourceUrl: string;
  note: string;
  counts: {
    institutions: number;
    withCoordinates: number;
    withoutCoordinates: number;
    wikidataRows: number;
    wikidataMatched: number;
    nominatimMatched: number;
  };
  institutions: CoordinateRecord[];
}

export interface CzechOutline {
  generatedAt: string;
  sourceUrl: string;
  note: string;
  geojson: unknown;
}

export interface CzechBasemap {
  generatedAt: string;
  sourceUrl: string;
  note: string;
  counts: { regions: number; cities: number; neighbors?: number; rivers?: number; lakes?: number };
  regions: MapRegion[];
  cities: MapCity[];
  neighbors?: string[];
  rivers?: string[];
  lakes?: string[];
}

export type MappedInstitution = MappedPoint<BaselineInstitution>;

export function loadCoordinates(): CoordinatesSnapshot {
  const payload = coordsJson as CoordinatesSnapshot;
  return {
    ...payload,
    institutions: payload.institutions.map((row) => ({
      institutionId: row.institutionId,
      lat: row.lat,
      lon: row.lon,
      match: normalizeMatch(row.match),
      sourceUrl: row.sourceUrl,
      wikidataId: row.wikidataId,
    })),
  };
}

export function loadOutline(): CzechOutline {
  return outlineJson as CzechOutline;
}

export function loadBasemap(): CzechBasemap {
  return basemapJson as CzechBasemap;
}

export function loadMappedInstitutions(institutions: BaselineInstitution[]): {
  schools: MappedInstitution[];
  outlinePath: string;
  snapshot: CoordinatesSnapshot;
  basemap: CzechBasemap;
} {
  const snapshot = loadCoordinates();
  return {
    schools: attachCoordinates(institutions, snapshot.institutions),
    outlinePath: geojsonToPath(loadOutline().geojson),
    snapshot,
    basemap: loadBasemap(),
  };
}

function normalizeMatch(value: CoordinateRecord["match"] | string | null): CoordinateMatch | null {
  if (value === "ico" || value === "website" || value === "official_name" || value === "register_seat_nominatim") {
    return value;
  }
  return null;
}

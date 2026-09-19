export const CZ_BBOX = {
  minLon: 12.09,
  maxLon: 18.86,
  minLat: 48.55,
  maxLat: 51.12,
};

export const MAP_SIZE = { width: 800, height: 520 };
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 72;

export interface MapView {
  scale: number;
  tx: number;
  ty: number;
}

export interface MapRegion {
  id: string;
  name: { "zh-CN": string; en: string; cs: string };
  path: string;
}

export interface MapCity {
  id: string;
  lat: number;
  lon: number;
  rank: number;
  names: { "zh-CN": string; en: string; cs: string };
  wikidataId?: string;
  sourceUrl?: string;
}

export interface CzechBasemapLayers {
  regions: MapRegion[];
  cities: MapCity[];
  neighbors?: string[];
  rivers?: string[];
  lakes?: string[];
}

export type CoordFilter = "all" | "mapped" | "missing";
export type CoordinateMatch = "ico" | "website" | "official_name" | "register_seat_nominatim";

export interface CoordinateRecord {
  institutionId: string;
  lat: number | null;
  lon: number | null;
  match: CoordinateMatch | null;
  sourceUrl: string | null;
  wikidataId: string | null;
}

export interface MappedPoint<T> {
  institution: T;
  lat: number | null;
  lon: number | null;
  match: CoordinateMatch | null;
  sourceUrl: string | null;
  wikidataId: string | null;
}

export interface ProjectedPoint {
  x: number;
  y: number;
}

export interface ClusterableMapPoint<T> {
  id: string;
  lat: number;
  lon: number;
  value: T;
}

export interface MapPointCluster<T> {
  id: string;
  lat: number;
  lon: number;
  points: ClusterableMapPoint<T>[];
}

type LonLat = [number, number];

export function inCzechBBox(lon: number, lat: number): boolean {
  return lon >= 12.0 && lon <= 19.0 && lat >= 48.4 && lat <= 51.2;
}

export function hasCoordinates(lat: number | null, lon: number | null): boolean {
  return lat != null && lon != null;
}

export function matchesCoordFilter(lat: number | null, lon: number | null, filter: CoordFilter): boolean {
  if (filter === "all") return true;
  const mapped = hasCoordinates(lat, lon);
  return filter === "mapped" ? mapped : !mapped;
}

export function svgPathCentroid(d: string): ProjectedPoint | null {
  const ring = d.split(/M/i).find((part) => part.trim().length > 0);
  if (!ring) return null;
  const nums = [...ring.matchAll(/-?\d+(?:\.\d+)?/g)].map((match) => Number(match[0]));
  if (nums.length < 4) return null;
  let sumX = 0;
  let sumY = 0;
  let count = 0;
  for (let i = 0; i + 1 < nums.length; i += 2) {
    sumX += nums[i];
    sumY += nums[i + 1];
    count += 1;
  }
  if (count === 0) return null;
  return { x: sumX / count, y: sumY / count };
}

export function projectLonLat(
  lon: number,
  lat: number,
  size = MAP_SIZE,
  bbox = CZ_BBOX,
): ProjectedPoint {
  const padX = 0.05;
  const padY = 0.12;
  const lonSpan = bbox.maxLon - bbox.minLon;
  const latSpan = bbox.maxLat - bbox.minLat;
  const minLon = bbox.minLon - lonSpan * padX;
  const maxLon = bbox.maxLon + lonSpan * padX;
  const minLat = bbox.minLat - latSpan * padY;
  const maxLat = bbox.maxLat + latSpan * padY;
  return {
    x: ((lon - minLon) / (maxLon - minLon)) * size.width,
    y: ((maxLat - lat) / (maxLat - minLat)) * size.height,
  };
}

/**
 * Groups nearby points in Web Mercator screen space.  At street-level zoom
 * every point is returned separately so colocated institutions can use their
 * individual marker offsets and remain independently actionable.
 */
export function clusterMapPoints<T>(
  points: ClusterableMapPoint<T>[],
  zoom: number,
  radiusPx = 48,
  individualZoom = 11,
): MapPointCluster<T>[] {
  const ordered = [...points].sort((a, b) => a.id.localeCompare(b.id));
  if (zoom >= individualZoom || ordered.length < 2) {
    return ordered.map((point) => ({
      id: point.id,
      lat: point.lat,
      lon: point.lon,
      points: [point],
    }));
  }

  const parents = ordered.map((_, index) => index);
  const projected = ordered.map((point) => mercatorPixel(point.lon, point.lat, zoom));
  const find = (index: number): number => {
    let root = index;
    while (parents[root] !== root) root = parents[root];
    while (parents[index] !== index) {
      const next = parents[index];
      parents[index] = root;
      index = next;
    }
    return root;
  };
  const union = (a: number, b: number) => {
    const rootA = find(a);
    const rootB = find(b);
    if (rootA !== rootB) parents[rootB] = rootA;
  };

  for (let a = 0; a < ordered.length; a += 1) {
    for (let b = a + 1; b < ordered.length; b += 1) {
      if (Math.hypot(projected[a].x - projected[b].x, projected[a].y - projected[b].y) <= radiusPx) {
        union(a, b);
      }
    }
  }

  const grouped = new Map<number, ClusterableMapPoint<T>[]>();
  ordered.forEach((point, index) => {
    const root = find(index);
    grouped.set(root, [...(grouped.get(root) ?? []), point]);
  });

  return [...grouped.values()].map((members) => ({
    id: members.length === 1 ? members[0].id : `cluster:${members.map((point) => point.id).join("|")}`,
    lat: members.reduce((sum, point) => sum + point.lat, 0) / members.length,
    lon: members.reduce((sum, point) => sum + point.lon, 0) / members.length,
    points: members,
  }));
}

function mercatorPixel(lon: number, lat: number, zoom: number): ProjectedPoint {
  const worldSize = 256 * 2 ** zoom;
  const limitedLat = clampNumber(lat, -85.051129, 85.051129);
  const sin = Math.sin((limitedLat * Math.PI) / 180);
  return {
    x: ((lon + 180) / 360) * worldSize,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * worldSize,
  };
}

export function attachCoordinates<T extends { id: string }>(
  institutions: T[],
  coords: CoordinateRecord[],
): MappedPoint<T>[] {
  const byId = new Map(coords.map((row) => [row.institutionId, row]));
  return institutions.map((institution) => {
    const hit = byId.get(institution.id);
    return {
      institution,
      lat: hit?.lat ?? null,
      lon: hit?.lon ?? null,
      match: hit?.match ?? null,
      sourceUrl: hit?.sourceUrl ?? null,
      wikidataId: hit?.wikidataId ?? null,
    };
  });
}

export function geojsonToPath(geojson: unknown, size = MAP_SIZE, bbox = CZ_BBOX): string {
  return collectRings(geojson)
    .map((ring) => ringToPath(ring, size, bbox))
    .join(" ");
}

function ringToPath(ring: LonLat[], size: typeof MAP_SIZE, bbox: typeof CZ_BBOX): string {
  if (ring.length === 0) return "";
  const parts = ring.map((point, index) => {
    const { x, y } = projectLonLat(point[0], point[1], size, bbox);
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  return `${parts.join(" ")} Z`;
}

function collectRings(value: unknown): LonLat[][] {
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  if (record.type === "FeatureCollection" && Array.isArray(record.features)) {
    return record.features.flatMap(collectRings);
  }
  if (record.type === "Feature") return collectRings(record.geometry);
  if (record.type === "Polygon" && Array.isArray(record.coordinates)) {
    return record.coordinates.filter(isRing);
  }
  if (record.type === "MultiPolygon" && Array.isArray(record.coordinates)) {
    return record.coordinates.flat().filter(isRing);
  }
  return [];
}

function isRing(value: unknown): value is LonLat[] {
  return Array.isArray(value) && value.length > 0 && isLonLat(value[0]);
}

function isLonLat(value: unknown): value is LonLat {
  return Array.isArray(value) && value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number";
}

export function coordFilterFromSearch(search: string): CoordFilter {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const value = params.get("coords");
  return value === "mapped" || value === "missing" ? value : "all";
}

export function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function defaultMapView(): MapView {
  return { scale: 1, tx: 0, ty: 0 };
}

export function clampMapView(view: MapView, size = MAP_SIZE): MapView {
  const scale = clampNumber(view.scale, MIN_ZOOM, MAX_ZOOM);
  const minTx = size.width * (1 - scale);
  const minTy = size.height * (1 - scale);
  return {
    scale,
    tx: clampNumber(view.tx, minTx, 0),
    ty: clampNumber(view.ty, minTy, 0),
  };
}

export function zoomMapAt(view: MapView, factor: number, cx: number, cy: number, size = MAP_SIZE): MapView {
  const next = clampNumber(view.scale * factor, MIN_ZOOM, MAX_ZOOM);
  const wx = (cx - view.tx) / view.scale;
  const wy = (cy - view.ty) / view.scale;
  return clampMapView({ scale: next, tx: cx - wx * next, ty: cy - wy * next }, size);
}

export function panMapBy(view: MapView, dx: number, dy: number, size = MAP_SIZE): MapView {
  return clampMapView({ scale: view.scale, tx: view.tx + dx, ty: view.ty + dy }, size);
}

export function pinScreenTransform(scale: number): string {
  return `translate(-50%, -100%) scale(${1 / scale})`;
}

export function shouldClearMapSelection(dragMoved: boolean, target: EventTarget | null): boolean {
  if (dragMoved) return false;
  const node = target as { closest?: (selector: string) => unknown } | null;
  if (node && typeof node.closest === "function" && node.closest(".map-pin, .map-callout, .map-zoom")) {
    return false;
  }
  return true;
}

export function searchFromMapQuery(
  search: string,
  ownership: string,
  cscse: string,
  coords: CoordFilter,
  city = "all",
): string {
  const params = new URLSearchParams();
  if (search.trim()) params.set("q", search.trim());
  if (city && city !== "all") params.set("city", city);
  if (ownership !== "all") params.set("ownership", ownership);
  if (cscse !== "all") params.set("cscse", cscse);
  if (coords !== "all") params.set("coords", coords);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

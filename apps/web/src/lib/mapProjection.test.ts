import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  MAP_SIZE,
  attachCoordinates,
  clusterMapPoints,
  coordFilterFromSearch,
  defaultMapView,
  geojsonToPath,
  hasCoordinates,
  inCzechBBox,
  matchesCoordFilter,
  MAX_ZOOM,
  panMapBy,
  projectLonLat,
  searchFromMapQuery,
  zoomMapAt,
  pinScreenTransform,
  shouldClearMapSelection,
  type CoordinateRecord,
} from "./mapProjection.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");

describe("map projection", () => {
  it("places Prague inside the SVG and keeps Berlin outside the Czech bbox", () => {
    const prague = projectLonLat(14.42076, 50.08781);
    assert.ok(prague.x > 80 && prague.x < MAP_SIZE.width - 80);
    assert.ok(prague.y > 40 && prague.y < MAP_SIZE.height - 40);
    assert.equal(inCzechBBox(14.42076, 50.08781), true);
    assert.equal(inCzechBBox(13.4, 52.5), false);
  });

  it("turns the self-hosted Czech outline into an SVG path", () => {
    const outline = JSON.parse(readFileSync(resolve(root, "data/sources/browse/czechia-outline.json"), "utf8")) as {
      geojson: unknown;
    };
    const path = geojsonToPath(outline.geojson);
    assert.match(path, /^M/);
    assert.match(path, / Z$/);
    assert.equal(path.includes("http"), false);
  });

  it("attaches coordinates only to register HEIs and does not invent a missing CSCSE name", () => {
    const coords = JSON.parse(readFileSync(resolve(root, "data/sources/browse/hei-coordinates.json"), "utf8")) as {
      counts: { institutions: number; withCoordinates: number };
      institutions: CoordinateRecord[];
    };
    const baseline = JSON.parse(readFileSync(resolve(root, "data/sources/msmt-hei-baseline.json"), "utf8")) as {
      institutions: { id: string; officialName: string }[];
      cscseUnmatched?: { zh: string }[];
    };
    assert.equal(coords.counts.institutions, 54);
    assert.equal(coords.institutions.length, 54);
    assert.ok(coords.counts.withCoordinates >= 48);
    const mapped = attachCoordinates(baseline.institutions, coords.institutions);
    assert.equal(mapped.length, 54);
    const charles = mapped.find((row) => row.institution.id === "msmt-vs_11000");
    assert.ok(charles);
    assert.equal(hasCoordinates(charles.lat, charles.lon), true);
    assert.ok(inCzechBBox(charles.lon as number, charles.lat as number));
    assert.equal(
      mapped.some((row) => row.institution.officialName.includes("政治与社会科学学院")),
      false,
    );
    assert.ok((baseline.cscseUnmatched ?? []).some((row) => row.zh.includes("政治与社会科学学院")));
    const missing = mapped.filter((row) => !hasCoordinates(row.lat, row.lon));
    assert.equal(
      missing.length,
      coords.institutions.filter((row) => !hasCoordinates(row.lat, row.lon)).length,
    );
  });

  it("zooms toward a point and clamps pan at 1x", () => {
    const start = defaultMapView();
    const zoomed = zoomMapAt(start, 2, MAP_SIZE.width / 2, MAP_SIZE.height / 2);
    assert.equal(zoomed.scale, 2);
    const maxed = zoomMapAt(start, MAX_ZOOM, MAP_SIZE.width / 2, MAP_SIZE.height / 2);
    assert.equal(maxed.scale, MAX_ZOOM);
    assert.equal(MAX_ZOOM, 72);
    assert.equal(zoomMapAt(maxed, 3, MAP_SIZE.width / 2, MAP_SIZE.height / 2).scale, MAX_ZOOM);
    const panned = panMapBy(zoomed, -40, -20);
    assert.ok(panned.tx <= 0 && panned.ty <= 0);
    const reset = zoomMapAt(panned, 0.1, 10, 10);
    assert.equal(reset.scale, 1);
    assert.equal(reset.tx, 0);
    assert.equal(reset.ty, 0);
  });

  it("keeps pin screen size constant while the map scale grows", () => {
    assert.equal(pinScreenTransform(1), "translate(-50%, -100%) scale(1)");
    assert.equal(pinScreenTransform(4), "translate(-50%, -100%) scale(0.25)");
    assert.equal(pinScreenTransform(MAX_ZOOM), `translate(-50%, -100%) scale(${1 / MAX_ZOOM})`);
  });

  it("clusters nearby institutions at country zoom and separates them at street zoom", () => {
    const points = [
      { id: "prague-a", lat: 50.087, lon: 14.421, value: "a" },
      { id: "prague-b", lat: 50.09, lon: 14.43, value: "b" },
      { id: "brno", lat: 49.195, lon: 16.608, value: "c" },
    ];
    const country = clusterMapPoints(points, 7);
    assert.equal(country.length, 2);
    const prague = country.find((cluster) => cluster.points.length === 2);
    assert.ok(prague);
    assert.deepEqual(prague.points.map((point) => point.id), ["prague-a", "prague-b"]);
    assert.match(prague.id, /^cluster:/);

    const street = clusterMapPoints(points, 12);
    assert.equal(street.length, 3);
    assert.ok(street.every((cluster) => cluster.points.length === 1));
    assert.deepEqual(street.map((cluster) => cluster.id), ["brno", "prague-a", "prague-b"]);
  });

  it("returns stable cluster ids regardless of source order", () => {
    const points = [
      { id: "b", lat: 50.08, lon: 14.42, value: 2 },
      { id: "a", lat: 50.081, lon: 14.421, value: 1 },
    ];
    assert.equal(clusterMapPoints(points, 7)[0].id, clusterMapPoints(points.reverse(), 7)[0].id);
  });

  it("clears the school card when the empty map is clicked, not when dragging or hitting a pin", () => {
    assert.equal(shouldClearMapSelection(false, null), true);
    assert.equal(shouldClearMapSelection(true, null), false);
    const pin = { closest: (sel: string) => (sel.includes(".map-pin") ? {} : null) };
    assert.equal(shouldClearMapSelection(false, pin as unknown as EventTarget), false);
  });

  it("loads 14 Czech regions and labelled Prague, Brno, Olomouc and Ostrava", () => {
    const basemap = JSON.parse(readFileSync(resolve(root, "data/sources/browse/czechia-basemap.json"), "utf8")) as {
      counts: { regions: number; cities: number };
      regions: { id: string; path: string }[];
      cities: { id: string; lat: number; lon: number; names: { cs: string } }[];
      rivers?: string[];
      lakes?: string[];
      neighbors?: string[];
    };
    assert.equal(basemap.counts.regions, 14);
    assert.ok(basemap.counts.cities >= 12);
    assert.ok((basemap.rivers?.length ?? 0) > 0);
    assert.ok((basemap.lakes?.length ?? 0) > 0);
    assert.ok((basemap.neighbors?.length ?? 0) > 0);
    assert.ok(basemap.regions.every((row) => row.path.startsWith("M")));
    const ids = new Set(basemap.cities.map((row) => row.id));
    for (const id of ["praha", "brno", "olomouc", "ostrava"]) {
      assert.ok(ids.has(id), id);
    }
    const pisek = basemap.cities.find((row) => row.id === "pisek");
    assert.ok(pisek);
    assert.ok(pisek.lon < 15);
  });

  it("round-trips map filters and keeps unmapped rows out of the pin set", () => {
    assert.equal(coordFilterFromSearch("?q=Brno&cscse=listed&coords=mapped"), "mapped");
    assert.equal(searchFromMapQuery("Mendel", "public", "listed", "mapped"), "?q=Mendel&ownership=public&cscse=listed&coords=mapped");
    assert.equal(
      searchFromMapQuery("", "all", "all", "all", "Brno"),
      "?city=Brno",
    );
    assert.equal(matchesCoordFilter(50.1, 14.4, "mapped"), true);
    assert.equal(matchesCoordFilter(null, null, "mapped"), false);
    assert.equal(matchesCoordFilter(null, null, "missing"), true);
  });

  it("keeps UJEP on Ústecký land, not across the German border", () => {
    const coords = JSON.parse(readFileSync(resolve(root, "data/sources/browse/hei-coordinates.json"), "utf8")) as {
      institutions: CoordinateRecord[];
    };
    const basemap = JSON.parse(readFileSync(resolve(root, "data/sources/browse/czechia-basemap.json"), "utf8")) as {
      regions: { id: string; path: string }[];
    };
    const ujep = coords.institutions.find((row) => row.institutionId === "msmt-vs_13000");
    assert.ok(ujep);
    assert.equal(hasCoordinates(ujep.lat, ujep.lon), true);
    assert.ok(ujep.lat! > 50.64 && ujep.lat! < 50.68);
    assert.ok(ujep.lon! > 14.0 && ujep.lon! < 14.05);
    const point = projectLonLat(ujep.lon as number, ujep.lat as number);
    const ustecky = basemap.regions.find((row) => row.id === "CZ042");
    assert.ok(ustecky);
    assert.equal(svgPathContains(ustecky.path, point.x, point.y), true);
    const source = readFileSync(resolve(root, "apps/web/src/components/InstitutionMap.svelte"), "utf8");
    assert.match(source, /preserveAspectRatio="none"/);
  });

  it("lets a plain mouse wheel zoom the interactive map", () => {
    const source = readFileSync(resolve(root, "apps/web/src/components/InstitutionMap.svelte"), "utf8");
    assert.match(source, /scrollZoom:\s*true/);
    assert.match(source, /cooperativeGestures:\s*false/);
  });
});

function svgPathContains(path: string, x: number, y: number): boolean {
  return parseSvgRings(path).some((ring) => pointInRing(x, y, ring));
}

function parseSvgRings(path: string): { x: number; y: number }[][] {
  const rings: { x: number; y: number }[][] = [];
  let ring: { x: number; y: number }[] = [];
  const re = /([MLZ])([^MLZ]*)/gi;
  let match: RegExpExecArray | null;
  while ((match = re.exec(path))) {
    const cmd = match[1].toUpperCase();
    if (cmd === "Z") {
      if (ring.length) rings.push(ring);
      ring = [];
      continue;
    }
    const nums = match[2]
      .trim()
      .split(/[\s,]+/)
      .filter(Boolean)
      .map(Number);
    for (let i = 0; i + 1 < nums.length; i += 2) {
      ring.push({ x: nums[i], y: nums[i + 1] });
    }
  }
  if (ring.length) rings.push(ring);
  return rings;
}

function pointInRing(x: number, y: number, ring: { x: number; y: number }[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i];
    const b = ring[j];
    if (a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) {
      inside = !inside;
    }
  }
  return inside;
}

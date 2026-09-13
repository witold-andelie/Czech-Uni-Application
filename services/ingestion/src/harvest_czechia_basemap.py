"""Build a self-hosted Czech basemap: 14 kraje + labelled cities.

Regions come from the open TopoJSON in jlacko/powerbi-cesko (ČSÚ NUTS-3 keys).
City points prefer Wikidata P625. No Google tiles, no Leaflet CDN.
Does not write data/published/.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sources" / "browse" / "czechia-basemap.json"
PUBLIC = ROOT / "apps" / "web" / "public" / "data" / "czechia-basemap.json"
KRAJE_URL = "https://raw.githubusercontent.com/jlacko/powerbi-cesko/master/kraje.json"
NE_RIVERS_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_rivers_europe.geojson"
NE_LAKES_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_lakes_europe.geojson"
NE_COUNTRIES_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
SPARQL_URL = "https://query.wikidata.org/sparql"
UA = "CzechUniApplyHarvest/0.1 (offline ingestion; contact via local operator)"
NEIGHBOR_ISO = {"DEU", "AUT", "POL", "SVK", "HUN"}
CZ_BBOX = {"minLon": 12.09, "maxLon": 18.86, "minLat": 48.55, "maxLat": 51.12}
MAP_SIZE = {"width": 800, "height": 520}
VIEW_BBOX = {
    "minLon": CZ_BBOX["minLon"] - (CZ_BBOX["maxLon"] - CZ_BBOX["minLon"]) * 0.08,
    "maxLon": CZ_BBOX["maxLon"] + (CZ_BBOX["maxLon"] - CZ_BBOX["minLon"]) * 0.08,
    "minLat": CZ_BBOX["minLat"] - (CZ_BBOX["maxLat"] - CZ_BBOX["minLat"]) * 0.08,
    "maxLat": CZ_BBOX["maxLat"] + (CZ_BBOX["maxLat"] - CZ_BBOX["minLat"]) * 0.08,
}

REGION_NAMES = {
    "CZ010": {"zh-CN": "布拉格", "en": "Prague", "cs": "Hlavní město Praha"},
    "CZ020": {"zh-CN": "中波希米亚州", "en": "Central Bohemia", "cs": "Středočeský kraj"},
    "CZ031": {"zh-CN": "南波希米亚州", "en": "South Bohemia", "cs": "Jihočeský kraj"},
    "CZ032": {"zh-CN": "比尔森州", "en": "Plzeň Region", "cs": "Plzeňský kraj"},
    "CZ041": {"zh-CN": "卡罗维发利州", "en": "Karlovy Vary Region", "cs": "Karlovarský kraj"},
    "CZ042": {"zh-CN": "乌斯季州", "en": "Ústí nad Labem Region", "cs": "Ústecký kraj"},
    "CZ051": {"zh-CN": "利贝雷茨州", "en": "Liberec Region", "cs": "Liberecký kraj"},
    "CZ052": {"zh-CN": "赫拉德茨-克拉洛韦州", "en": "Hradec Králové Region", "cs": "Královéhradecký kraj"},
    "CZ053": {"zh-CN": "帕尔杜比采州", "en": "Pardubice Region", "cs": "Pardubický kraj"},
    "CZ063": {"zh-CN": "高地州", "en": "Vysočina", "cs": "Kraj Vysočina"},
    "CZ064": {"zh-CN": "南摩拉维亚州", "en": "South Moravia", "cs": "Jihomoravský kraj"},
    "CZ071": {"zh-CN": "奥洛穆茨州", "en": "Olomouc Region", "cs": "Olomoucký kraj"},
    "CZ072": {"zh-CN": "兹林州", "en": "Zlín Region", "cs": "Zlínský kraj"},
    "CZ080": {"zh-CN": "摩拉维亚-西里西亚州", "en": "Moravian-Silesian Region", "cs": "Moravskoslezský kraj"},
}

CITIES = [
    {"id": "praha", "qid": "Q1085", "rank": 1, "names": {"zh-CN": "布拉格", "en": "Prague", "cs": "Praha"}},
    {"id": "brno", "qid": "Q14960", "rank": 1, "names": {"zh-CN": "布尔诺", "en": "Brno", "cs": "Brno"}},
    {"id": "ostrava", "qid": "Q8385", "rank": 1, "names": {"zh-CN": "俄斯特拉发", "en": "Ostrava", "cs": "Ostrava"}},
    {"id": "plzen", "qid": "Q43453", "rank": 1, "names": {"zh-CN": "比尔森", "en": "Pilsen", "cs": "Plzeň"}},
    {"id": "olomouc", "qid": "Q81137", "rank": 1, "names": {"zh-CN": "奥洛穆茨", "en": "Olomouc", "cs": "Olomouc"}},
    {"id": "liberec", "qid": "Q146351", "rank": 2, "names": {"zh-CN": "利贝雷茨", "en": "Liberec", "cs": "Liberec"}},
    {"id": "ceske-budejovice", "qid": "Q16506", "rank": 2, "names": {"zh-CN": "捷克布杰约维采", "en": "České Budějovice", "cs": "České Budějovice"}},
    {"id": "hradec-kralove", "qid": "Q180139", "rank": 2, "names": {"zh-CN": "赫拉德茨-克拉洛韦", "en": "Hradec Králové", "cs": "Hradec Králové"}},
    {"id": "usti-nad-labem", "qid": "Q156974", "rank": 2, "names": {"zh-CN": "拉贝河畔乌斯季", "en": "Ústí nad Labem", "cs": "Ústí nad Labem"}},
    {"id": "zlin", "qid": "Q171018", "rank": 2, "names": {"zh-CN": "兹林", "en": "Zlín", "cs": "Zlín"}},
    {"id": "pardubice", "qid": "Q36989", "rank": 2, "names": {"zh-CN": "帕尔杜比采", "en": "Pardubice", "cs": "Pardubice"}},
    {"id": "jihlava", "qid": "Q56447", "rank": 2, "names": {"zh-CN": "伊赫拉瓦", "en": "Jihlava", "cs": "Jihlava"}},
    {"id": "opava", "qid": "Q166392", "rank": 3, "names": {"zh-CN": "奥帕瓦", "en": "Opava", "cs": "Opava"}},
    {"id": "mlada-boleslav", "qid": "Q191805", "rank": 3, "names": {"zh-CN": "姆拉达-博莱斯拉夫", "en": "Mladá Boleslav", "cs": "Mladá Boleslav"}},
    {"id": "pisek", "qid": "Q158239", "rank": 3, "names": {"zh-CN": "皮塞克", "en": "Písek", "cs": "Písek"}},
    {"id": "prerov", "qid": "Q470380", "rank": 3, "names": {"zh-CN": "普热罗夫", "en": "Přerov", "cs": "Přerov"}},
    {"id": "havirov", "qid": "Q192904", "rank": 3, "names": {"zh-CN": "哈维若夫", "en": "Havířov", "cs": "Havířov"}},
]


def project(lon: float, lat: float) -> tuple[float, float]:
    pad_x, pad_y = 0.05, 0.12
    lon_span = CZ_BBOX["maxLon"] - CZ_BBOX["minLon"]
    lat_span = CZ_BBOX["maxLat"] - CZ_BBOX["minLat"]
    min_lon = CZ_BBOX["minLon"] - lon_span * pad_x
    max_lon = CZ_BBOX["maxLon"] + lon_span * pad_x
    min_lat = CZ_BBOX["minLat"] - lat_span * pad_y
    max_lat = CZ_BBOX["maxLat"] + lat_span * pad_y
    x = (lon - min_lon) / (max_lon - min_lon) * MAP_SIZE["width"]
    y = (max_lat - lat) / (max_lat - min_lat) * MAP_SIZE["height"]
    return x, y


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def coords_touch_bbox(value: object) -> bool:
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            lon, lat = float(value[0]), float(value[1])
            return (
                VIEW_BBOX["minLon"] <= lon <= VIEW_BBOX["maxLon"]
                and VIEW_BBOX["minLat"] <= lat <= VIEW_BBOX["maxLat"]
            )
        return any(coords_touch_bbox(item) for item in value)
    return False


def line_path(line: list[list[float]]) -> str:
    parts = []
    for index, point in enumerate(line):
        x, y = project(point[0], point[1])
        parts.append(f"{'M' if index == 0 else 'L'}{x:.2f} {y:.2f}")
    return " ".join(parts)


def geometry_paths(geometry: dict, closed: bool) -> list[str]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    paths: list[str] = []
    if kind == "LineString":
        path = line_path(coords)
        if path:
            paths.append(path)
    elif kind == "MultiLineString":
        for line in coords:
            path = line_path(line)
            if path:
                paths.append(path)
    elif kind == "Polygon":
        path = " ".join(ring_path(ring) for ring in coords if ring)
        if path:
            paths.append(path)
    elif kind == "MultiPolygon":
        for polygon in coords:
            path = " ".join(ring_path(ring) for ring in polygon if ring)
            if path:
                paths.append(path)
    return paths if closed or kind in {"LineString", "MultiLineString", "Polygon", "MultiPolygon"} else paths


def ring_path(ring: list[list[float]]) -> str:
    parts = []
    for index, point in enumerate(ring):
        x, y = project(point[0], point[1])
        parts.append(f"{'M' if index == 0 else 'L'}{x:.2f} {y:.2f}")
    return " ".join(parts) + " Z"


def decode_arc(arcs: list, index: int) -> list[list[float]]:
    if index < 0:
        return list(reversed(arcs[~index]))
    return list(arcs[index])


def stitch(arcs: list, indexes: list[int]) -> list[list[float]]:
    coords: list[list[float]] = []
    for index in indexes:
        piece = decode_arc(arcs, index)
        if coords:
            piece = piece[1:]
        coords.extend(piece)
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def parse_point(value: str) -> tuple[float, float] | None:
    if not value.startswith("Point("):
        return None
    inner = value[len("Point(") :].rstrip(")")
    parts = inner.split()
    if len(parts) != 2:
        return None
    lon, lat = float(parts[0]), float(parts[1])
    if not (12.0 <= lon <= 19.0 and 48.4 <= lat <= 51.2):
        return None
    return lat, lon


def nominatim_city(name_cs: str) -> dict | None:
    query = urllib.parse.urlencode(
        {
            "q": f"{name_cs}, Česko",
            "format": "jsonv2",
            "limit": "1",
            "countrycodes": "cz",
            "addressdetails": "0",
        }
    )
    url = "https://nominatim.openstreetmap.org/search?" + query
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    if not rows:
        return None
    lat = float(rows[0]["lat"])
    lon = float(rows[0]["lon"])
    if not (12.0 <= lon <= 19.0 and 48.4 <= lat <= 51.2):
        return None
    return {"lat": lat, "lon": lon, "sourceUrl": url}


def fetch_city_coords() -> dict[str, dict]:
    values = " ".join(f"wd:{item['qid']}" for item in CITIES)
    query = (
        "SELECT ?item ?coord WHERE { "
        f"VALUES ?item {{ {values} }} "
        "?item wdt:P17 wd:Q213 . "
        "?item wdt:P625 ?coord. }"
    )
    url = SPARQL_URL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    hits: dict[str, dict] = {}
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        for binding in payload.get("results", {}).get("bindings", []):
            qid = binding.get("item", {}).get("value", "").rsplit("/", 1)[-1]
            coord = parse_point(binding.get("coord", {}).get("value", ""))
            if not qid or not coord:
                continue
            hits[qid] = {"lat": coord[0], "lon": coord[1], "sourceUrl": f"https://www.wikidata.org/wiki/{qid}"}
    except Exception:
        hits = {}
    # Písek has more than one Czech place; prefer the South Bohemian city via Nominatim.
    for index, city in enumerate(CITIES):
        if city["qid"] in hits and city["id"] != "pisek":
            continue
        if index:
            time.sleep(1.1)
        geo = nominatim_city(city["names"]["cs"])
        if geo:
            hits[city["qid"]] = geo
    return hits


def fetch_kraje() -> dict:
    return fetch_json(KRAJE_URL)


def iso_of(props: dict) -> str:
    return str(props.get("ADM0_A3") or props.get("ISO_A3") or props.get("adm0_a3") or "").upper()


def clip_features(url: str) -> list[dict]:
    payload = fetch_json(url)
    return [
        feature
        for feature in payload.get("features") or []
        if coords_touch_bbox((feature.get("geometry") or {}).get("coordinates"))
    ]


def neighbor_paths() -> list[str]:
    paths: list[str] = []
    for feature in clip_features(NE_COUNTRIES_URL):
        if iso_of(feature.get("properties") or {}) not in NEIGHBOR_ISO:
            continue
        paths.extend(geometry_paths(feature.get("geometry") or {}, True))
    return paths


def water_paths(url: str, closed: bool) -> list[str]:
    paths: list[str] = []
    for feature in clip_features(url):
        paths.extend(geometry_paths(feature.get("geometry") or {}, closed))
    return paths


def reuse_cities() -> list[dict]:
    if not OUT.is_file():
        return []
    payload = json.loads(OUT.read_text(encoding="utf-8"))
    cities = payload.get("cities") or []
    return cities if len(cities) >= 10 else []


def build() -> dict:
    topology = fetch_kraje()
    arcs = topology["arcs"]
    regions = []
    for geometry in topology["objects"]["kraje"]["geometries"]:
        props = geometry.get("properties") or {}
        region_id = str(props.get("id") or props.get("KOD_CZNUTS3") or "")
        rings = [stitch(arcs, ring) for ring in geometry.get("arcs") or []]
        path = " ".join(ring_path(ring) for ring in rings if ring)
        if not path:
            continue
        regions.append(
            {
                "id": region_id,
                "name": REGION_NAMES.get(region_id, {"zh-CN": region_id, "en": region_id, "cs": props.get("NAZ_CZNUTS3") or region_id}),
                "path": path,
            }
        )
    cities = reuse_cities()
    if not cities:
        coords = fetch_city_coords()
        for city in CITIES:
            hit = coords.get(city["qid"])
            if not hit:
                continue
            cities.append(
                {
                    "id": city["id"],
                    "lat": hit["lat"],
                    "lon": hit["lon"],
                    "rank": city["rank"],
                    "names": city["names"],
                    "wikidataId": city["qid"],
                    "sourceUrl": hit["sourceUrl"],
                }
            )
    neighbors = neighbor_paths()
    rivers = water_paths(NE_RIVERS_URL, False)
    lakes = water_paths(NE_LAKES_URL, True)
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "open_geodata_extract",
        "catalogKind": "basemap_not_published",
        "sourceUrl": KRAJE_URL,
        "naturalEarthUrl": "https://github.com/nvkelso/natural-earth-vector",
        "note": (
            "14 Czech regions from jlacko/powerbi-cesko (ČSÚ NUTS-3). "
            "Neighbors, rivers and lakes clipped from Natural Earth 50m "
            "(nvkelso/natural-earth-vector, public domain). City labels use "
            "Wikidata / Nominatim. Self-hosted SVG, not a live tile service. "
            "Not written to data/published/."
        ),
        "counts": {
            "regions": len(regions),
            "cities": len(cities),
            "neighbors": len(neighbors),
            "rivers": len(rivers),
            "lakes": len(lakes),
        },
        "regions": regions,
        "cities": cities,
        "neighbors": neighbors,
        "rivers": rivers,
        "lakes": lakes,
    }


def main() -> None:
    payload = build()
    if payload["counts"]["regions"] != 14:
        raise SystemExit(f"expected 14 regions, got {payload['counts']['regions']}")
    if payload["counts"]["cities"] < 10:
        raise SystemExit(f"too few city coordinates: {payload['counts']['cities']}")
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    PUBLIC.write_text(text, encoding="utf-8")
    print(
        f"Wrote {payload['counts']['regions']} regions, {payload['counts']['cities']} cities, "
        f"{payload['counts']['neighbors']} neighbors, {payload['counts']['rivers']} rivers, "
        f"{payload['counts']['lakes']} lakes to {OUT}"
    )


if __name__ == "__main__":
    main()

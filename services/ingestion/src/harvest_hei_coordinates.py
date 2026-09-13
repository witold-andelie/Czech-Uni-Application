"""Attach map coordinates to MŠMT register HEIs.

Identity stays on the ministry register. Coordinates prefer Wikidata P625 when
IČO (P4156) or the official Czech name matches exactly. Remaining seats are
geocoded from the register address via Nominatim (country=CZ). Missing
coordinates are not invented. Does not write data/published/.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
OUT = ROOT / "data" / "sources" / "browse" / "hei-coordinates.json"
PUBLIC = ROOT / "apps" / "web" / "public" / "data" / "hei-coordinates.json"
OUTLINE_OUT = ROOT / "data" / "sources" / "browse" / "czechia-outline.json"
OUTLINE_PUBLIC = ROOT / "apps" / "web" / "public" / "data" / "czechia-outline.json"
SPARQL_URL = "https://query.wikidata.org/sparql"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OUTLINE_URL = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries/CZE.geo.json"
UA = "CzechUniApplyHarvest/0.1 (offline ingestion; contact via local operator)"
CTX = ssl.create_default_context()
SLEEP = 2
NOMINATIM_SLEEP = 1.1

SPARQL = """
SELECT ?item ?itemLabel ?enLabel ?coord ?ico ?website WHERE {
  {
    ?item wdt:P31/wdt:P279* wd:Q3918 .
    ?item wdt:P17 wd:Q213 .
  } UNION {
    ?item wdt:P31/wdt:P279* wd:Q38723 .
    ?item wdt:P17 wd:Q213 .
  }
  OPTIONAL { ?item wdt:P625 ?coord . }
  OPTIONAL { ?item wdt:P4156 ?ico . }
  OPTIONAL { ?item wdt:P856 ?website . }
  OPTIONAL { ?item rdfs:label ?enLabel FILTER (LANG(?enLabel) = "en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "cs". }
}
"""


def norm_ico(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits.zfill(8) if digits else ""


def host_of(url: str) -> str:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return host.removeprefix("www.")


def fold(value: str) -> str:
    import unicodedata

    nfkd = unicodedata.normalize("NFD", value)
    stripped = "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")
    return " ".join(stripped.casefold().split())


def request(url: str, headers: dict[str, str] | None = None, timeout: int = 90) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as response:
            return response.status, response.read()
    except Exception:
        return 0, b""


def parse_point(value: str) -> tuple[float, float] | None:
    if not value or not value.startswith("Point("):
        return None
    inner = value[len("Point(") :].rstrip(")")
    parts = inner.split()
    if len(parts) != 2:
        return None
    lon, lat = float(parts[0]), float(parts[1])
    if not (12.0 <= lon <= 19.0 and 48.4 <= lat <= 51.2):
        return None
    return lat, lon


def fetch_wikidata() -> list[dict]:
    url = SPARQL_URL + "?" + urllib.parse.urlencode({"query": SPARQL, "format": "json"})
    status, body = request(url, {"Accept": "application/sparql-results+json"})
    if status != 200:
        return []
    payload = json.loads(body.decode("utf-8"))
    rows = []
    for binding in payload.get("results", {}).get("bindings", []):
        item = binding.get("item", {}).get("value", "")
        qid = item.rsplit("/", 1)[-1] if item else ""
        coord = parse_point(binding.get("coord", {}).get("value", ""))
        rows.append(
            {
                "qid": qid,
                "url": item,
                "labelCs": binding.get("itemLabel", {}).get("value", ""),
                "labelEn": binding.get("enLabel", {}).get("value", ""),
                "ico": (binding.get("ico", {}).get("value") or "").strip(),
                "website": binding.get("website", {}).get("value", ""),
                "lat": coord[0] if coord else None,
                "lon": coord[1] if coord else None,
            }
        )
    return rows


def match_row(school: dict, rows: list[dict]) -> dict | None:
    ico = norm_ico(str(school.get("ico") or ""))
    if ico:
        hits = [row for row in rows if norm_ico(row["ico"]) == ico and row["lat"] is not None]
        unique = {row["qid"]: row for row in hits}
        if len(unique) == 1:
            return {**next(iter(unique.values())), "match": "ico"}
    host = host_of(school.get("officialUrl") or "")
    if host:
        host_hits = [
            row
            for row in rows
            if row["lat"] is not None and host_of(row.get("website") or "") == host
        ]
        unique = {row["qid"]: row for row in host_hits}
        if len(unique) == 1:
            return {**next(iter(unique.values())), "match": "website"}
    name = fold(school.get("officialName") or "")
    name_hits = [row for row in rows if row["lat"] is not None and fold(row["labelCs"]) == name]
    unique = {row["qid"]: row for row in name_hits}
    if len(unique) == 1:
        return {**next(iter(unique.values())), "match": "official_name"}
    return None


def clean_seat(seat: str) -> str:
    text = re.sub(r"P\.?\s*O\.?\s*Box\s*\d*", " ", seat, flags=re.IGNORECASE)
    return " ".join(text.split())


def digits_postcode(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits if len(digits) == 5 else ""


def postcodes_match(seat: str, result_postcode: str) -> bool:
    found = re.search(r"\b\d{3}\s*\d{2}\b", seat)
    expected = digits_postcode(found.group(0) if found else "")
    got = digits_postcode(result_postcode)
    if not expected or not got:
        return True
    return expected == got


def nominatim_query(seat: str, expect_from: str = "") -> dict | None:
    if not seat.strip():
        return None
    query = urllib.parse.urlencode(
        {
            "q": f"{seat}, Česko",
            "format": "jsonv2",
            "limit": "1",
            "countrycodes": "cz",
            "addressdetails": "1",
        }
    )
    status, body = request(f"{NOMINATIM_URL}?{query}", {"Accept": "application/json"})
    if status != 200 or not body:
        return None
    rows = json.loads(body.decode("utf-8"))
    if not rows:
        return None
    lat = float(rows[0]["lat"])
    lon = float(rows[0]["lon"])
    if not (12.0 <= lon <= 19.0 and 48.4 <= lat <= 51.2):
        return None
    address = rows[0].get("address") or {}
    if not postcodes_match(expect_from or seat, str(address.get("postcode") or "")):
        return None
    return {
        "lat": lat,
        "lon": lon,
        "qid": None,
        "url": f"{NOMINATIM_URL}?{query}",
        "match": "register_seat_nominatim",
        "labelCs": "",
        "labelEn": "",
        "ico": "",
        "website": "",
    }


def drop_named_district(text: str) -> str:
    comma = [part.strip() for part in text.split(",") if part.strip()]
    if len(comma) > 1:
        kept = [part for index, part in enumerate(comma) if re.search(r"\d", part) or index == len(comma) - 1]
        text = ", ".join(kept)
    text = re.sub(r"(\d)\s+[^\d,]+\s+(\d{3}\s*\d{2})", r"\1 \2", text)
    text = re.sub(r"\b(Praha|Brno|Liberec|Ostrava)\s+\d+\b", r"\1", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def seat_variants(seat: str) -> list[str]:
    cleaned = clean_seat(seat)
    variants: list[str] = []

    def add(value: str) -> None:
        folded = " ".join(value.split())
        if folded and folded not in variants:
            variants.append(folded)

    add(seat)
    add(cleaned)
    match = re.search(r"(\d+)\s*/\s*(\d+)", cleaned)
    if match:
        for number in (match.group(1), match.group(2)):
            add(cleaned[: match.start()] + number + cleaned[match.end() :])
    for current in list(variants):
        add(drop_named_district(current))
        add(fold(current))
        add(fold(drop_named_district(current)))
    return variants


def nominatim_seat(seat: str) -> dict | None:
    variants = seat_variants(seat)
    for index, candidate in enumerate(variants):
        if index:
            time.sleep(NOMINATIM_SLEEP)
        hit = nominatim_query(candidate, expect_from=seat)
        if hit:
            return hit
    return None


def fetch_outline() -> dict:
    status, body = request(OUTLINE_URL)
    if status != 200:
        raise SystemExit(f"Czech outline fetch failed: HTTP {status}")
    payload = json.loads(body.decode("utf-8"))
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceUrl": OUTLINE_URL,
        "note": "Simplified Czechia polygon for a self-hosted SVG map. Not a live tile service.",
        "geojson": payload,
    }


def build() -> dict:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    rows = fetch_wikidata()
    institutions = []
    matched = 0
    sources = {"wikidata": 0, "nominatim": 0}
    for index, school in enumerate(baseline["institutions"]):
        hit = match_row(school, rows) if rows else None
        if hit is None:
            if index:
                time.sleep(NOMINATIM_SLEEP)
            hit = nominatim_seat(str(school.get("seat") or ""))
            if hit:
                sources["nominatim"] += 1
        elif hit.get("match") != "register_seat_nominatim":
            sources["wikidata"] += 1
        record = {
            "institutionId": school["id"],
            "msmtCode": school["msmtCode"],
            "officialName": school["officialName"],
            "lat": hit["lat"] if hit else None,
            "lon": hit["lon"] if hit else None,
            "wikidataId": hit.get("qid") if hit else None,
            "wikidataUrl": hit.get("url") if hit and hit.get("qid") else None,
            "match": hit["match"] if hit else None,
            "sourceUrl": hit["url"] if hit else None,
        }
        if hit:
            matched += 1
        institutions.append(record)
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_register_extract",
        "catalogKind": "coordinates_not_published",
        "sourceUrl": SPARQL_URL,
        "note": (
            "School identity is the MŠMT register. Coordinates prefer Wikidata P625 "
            "when IČO or the official Czech name / website host matches uniquely. "
            "Otherwise the register seat is geocoded with Nominatim in CZ. "
            "Missing coordinates are not invented. Not written to data/published/."
        ),
        "counts": {
            "institutions": len(institutions),
            "withCoordinates": matched,
            "withoutCoordinates": len(institutions) - matched,
            "wikidataRows": len(rows),
            "wikidataMatched": sources["wikidata"],
            "nominatimMatched": sources["nominatim"],
        },
        "institutions": institutions,
    }


def main() -> None:
    payload = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    OUT.write_text(text, encoding="utf-8")
    PUBLIC.write_text(text, encoding="utf-8")
    if not OUTLINE_OUT.is_file():
        outline = fetch_outline()
        outline_text = json.dumps(outline, ensure_ascii=False, separators=(",", ":")) + "\n"
        OUTLINE_OUT.write_text(outline_text, encoding="utf-8")
        OUTLINE_PUBLIC.write_text(outline_text, encoding="utf-8")
    elif not OUTLINE_PUBLIC.is_file():
        OUTLINE_PUBLIC.write_text(OUTLINE_OUT.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        f"Wrote {payload['counts']['withCoordinates']}/{payload['counts']['institutions']} "
        f"coordinates to {OUT}"
    )


if __name__ == "__main__":
    main()

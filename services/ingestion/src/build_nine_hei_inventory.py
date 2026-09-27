"""Build a compact CSCSE-listed HEI programme inventory from official register extracts.

This is an accredited/delivered programme inventory, not an admissions catalogue.
It does not invent tuition, application windows, or Chinese titles, and does not
write data/published/.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from apply_cscse_list import LISTED

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data" / "sources" / "programmes"
OUT_DIR = ROOT / "data" / "sources" / "browse"
REGISTER_URL = "https://regvssp.msmt.cz/registrvssp/csplist.aspx"
# Written by resolve_programme_links.py. Absent is fine: the inventory then
# simply carries no programme page link and says so.
PROGRAMME_LINKS = ROOT / "data" / "sources" / "admissions" / "programme-links.json"
PROGRAMME_LINK_NOTE = (
    "School-owned programme pages resolved by exact normalised title, degree and "
    "teaching-language equality; see programmeLinks and resolve_programme_links.py. "
    "Rows without an entry show the university site instead."
)
PROGRAMME_LINK_NOTE_MISSING = (
    "No school-owned programme page index (data/sources/admissions/programme-links.json) "
    "was present for this build, so every row shows the university site."
)
PROGRAMME_LINK_NOTE_UNREADABLE = (
    "The school-owned programme page index could not be read, so no programme page link "
    "was attached and every row shows the university site."
)

NINE_HEIS: tuple[tuple[str, str], ...] = tuple(
    (item["msmtCode"].lower(), f"msmt-{item['msmtCode'].lower()}") for item in LISTED
)

DEGREE_CODE = {
    "bachelor": "b",
    "master": "m",
    "doctorate": "d",
    "other": "o",
    "unknown": "u",
}

NOTE = (
    "Accredited/delivered programme inventory from the official MŠMT register "
    "for harvested register HEIs. Not an admissions catalogue: no application "
    "window, tuition, or apply-now state. Original titles are kept in all UI "
    "locales. CSCSE listing is a lookup reference, not a certification "
    "guarantee. Not written to data/published/."
)


def row_id(institution_id: str, title: str, degree: str, language: str, faculty: str) -> str:
    raw = f"{institution_id}|{title}|{degree}|{language}|{faculty}"
    return "inv-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def years_of(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.search(r"\d+[.,]\s+\d", text):
        return None
    compact = text.replace(" ", "")
    if re.fullmatch(r"\d+[.,]\d+", compact):
        whole, frac = re.split(r"[.,]", compact, maxsplit=1)
        return float(f"{whole}.{frac}")
    match = re.search(r"\d+", text)
    return float(match.group(0)) if match else None


def compact_row(institution_id: str, programme: dict) -> list | None:
    title = str(programme.get("titleOriginal") or "").strip()
    if not title:
        return None
    degree = str(programme.get("degree") or "unknown")
    if degree not in DEGREE_CODE:
        degree = "unknown"
    language = str(programme.get("teachingLanguage") or "").strip().lower()
    if not language:
        return None
    faculty = str(programme.get("facultyName") or "").strip()
    isced = str(programme.get("iscedF") or "").strip()
    ident = row_id(institution_id, title, degree, language, faculty)
    return [
        ident,
        title,
        DEGREE_CODE[degree],
        faculty,
        years_of(programme.get("standardYears")),
        language,
        isced,
    ]


def compact_school(path: Path, institution_id: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    seen = set()
    for programme in payload.get("programmes") or []:
        row = compact_row(institution_id, programme)
        if row is None:
            continue
        if row[0] in seen:
            continue
        seen.add(row[0])
        rows.append(row)
    rows.sort(key=lambda item: (item[1].casefold(), item[2], item[5], item[3].casefold()))
    return {"id": institution_id, "rows": rows}


def build_compact(schools: list[dict], generated_at: str | None = None, link_report: dict | None = None) -> dict:
    generated = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = sum(len(school["rows"]) for school in schools)
    payload = {
        "generatedAt": generated,
        "dataClass": "official_register_extract",
        "catalogKind": "browse_with_inventory",
        "sourceUrl": REGISTER_URL,
        "academicYear": "register",
        "note": NOTE,
        "counts": {
            "schools": len(schools),
            "programmes": total,
        },
        "schools": schools,
    }
    _, report = stamp_programme_links(payload)
    if link_report is not None:
        # What the link gate kept and what it dropped, so the build can say so.
        link_report.update(report)
    return payload


def stamp_programme_links(payload: dict) -> tuple[dict, dict[str, int]]:
    """Attach school-owned programme page links, keeping the 7-field row format.

    Links sit beside the rows, keyed by the row's own id, so the positional row
    contract is untouched. A row without a proven page gets no entry and keeps
    showing the university site; the count states how many rows do have one.

    A link the index proves but this build does not publish is counted, not
    dropped quietly: the resolver is what would have to change, and CI reports
    the difference (check_programme_link_coverage.py).
    """
    report = {
        "indexLinks": 0,
        "published": 0,
        "droppedNotHttps": 0,
        "droppedForeignDomain": 0,
        "droppedUnknownRow": 0,
    }
    # Imported lazily: the resolver imports this module for row ids.
    from resolve_programme_links import allowed_domains_by_institution, registrable_host

    if not PROGRAMME_LINKS.is_file():
        payload["programmeLinkNote"] = PROGRAMME_LINK_NOTE_MISSING
        return payload, report
    try:
        index = json.loads(PROGRAMME_LINKS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload["programmeLinkNote"] = PROGRAMME_LINK_NOTE_UNREADABLE
        return payload, report
    index_links = {
        str(ident): entry
        for ident, entry in (index.get("links") or {}).items()
        if isinstance(entry, dict)
    }
    report["indexLinks"] = len(index_links)
    allowed = allowed_domains_by_institution()
    kept: dict[str, dict] = {}
    known_rows: set[str] = set()
    for school in payload.get("schools") or []:
        institution_id = str(school.get("id") or "")
        domains = allowed.get(institution_id) or set()
        for row in school.get("rows") or []:
            known_rows.add(str(row[0]))
    for ident, entry in sorted(index_links.items()):
        url = str(entry.get("url") or "")
        if not url.startswith("https://"):
            # Not a school-owned https page: drop rather than publish it.
            report["droppedNotHttps"] += 1
            continue
        if registrable_host(url) not in (allowed.get(str(entry.get("institutionId") or "")) or set()):
            report["droppedForeignDomain"] += 1
            continue
        if ident not in known_rows:
            report["droppedUnknownRow"] += 1
            continue
        kept[ident] = {
            "url": url,
            "kind": "school_programme_page",
            "reachability": str(entry.get("reachability") or "unverified"),
        }
    payload["programmeLinks"] = kept
    payload["counts"]["linkedProgrammes"] = len(kept)
    payload["programmeLinkNote"] = PROGRAMME_LINK_NOTE
    payload["programmeLinkGeneratedAt"] = str(index.get("generatedAt") or "")
    report["published"] = len(kept)
    return payload, report


def register_extracts() -> list[tuple[str, str]]:
    missing_listed = [
        item["msmtCode"].lower()
        for item in LISTED
        if not (SRC / f"{item['msmtCode'].lower()}.json").is_file()
    ]
    if missing_listed:
        raise FileNotFoundError(f"missing listed register extracts: {missing_listed}")
    paths = sorted(SRC.glob("vs_*.json"))
    return [(path.stem, f"msmt-{path.stem}") for path in paths]


def build_from_register(link_report: dict | None = None) -> dict:
    schools = []
    for filename, institution_id in register_extracts():
        path = SRC / f"{filename}.json"
        schools.append(compact_school(path, institution_id))
    return build_compact(schools, link_report=link_report)


def write_compact(payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    source_path = OUT_DIR / "nine-hei-inventory.json"
    source_path.write_text(text, encoding="utf-8")
    return source_path


def main() -> None:
    link_report: dict[str, int] = {}
    payload = build_from_register(link_report)
    source_path = write_compact(payload)
    size = source_path.stat().st_size
    print(
        f"Wrote {payload['counts']['programmes']} programmes "
        f"for {payload['counts']['schools']} schools "
        f"({size} bytes) to candidate data {source_path}"
    )
    dropped = link_report.get("indexLinks", 0) - link_report.get("published", 0)
    print(
        "School-owned programme pages: "
        f"{link_report.get('published', 0)} of {link_report.get('indexLinks', 0)} proven link(s) published"
        + (
            f"; {dropped} not published "
            f"(not https {link_report.get('droppedNotHttps', 0)}, "
            f"outside the school's domains {link_report.get('droppedForeignDomain', 0)}, "
            f"row not in the register {link_report.get('droppedUnknownRow', 0)})"
            if dropped
            else ""
        )
    )


if __name__ == "__main__":
    main()

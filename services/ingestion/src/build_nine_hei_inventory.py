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


def build_compact(schools: list[dict], generated_at: str | None = None) -> dict:
    generated = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = sum(len(school["rows"]) for school in schools)
    return {
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


def build_from_register() -> dict:
    schools = []
    for filename, institution_id in register_extracts():
        path = SRC / f"{filename}.json"
        schools.append(compact_school(path, institution_id))
    return build_compact(schools)


def write_compact(payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    source_path = OUT_DIR / "nine-hei-inventory.json"
    source_path.write_text(text, encoding="utf-8")
    return source_path


def main() -> None:
    payload = build_from_register()
    source_path = write_compact(payload)
    size = source_path.stat().st_size
    print(
        f"Wrote {payload['counts']['programmes']} programmes "
        f"for {payload['counts']['schools']} schools "
        f"({size} bytes) to candidate data {source_path}"
    )


if __name__ == "__main__":
    main()

"""Parse official MŠMT register CSV exports (Windows-1250, semicolon)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "work" / "raw" / "2026-09-06"
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
FACULTIES_OUT = ROOT / "data" / "sources" / "msmt-faculties.json"
ENCODING = "cp1250"

INST_CSV = RAW / "msmt-register-institutions.csv.txt"
FAC_CSV = RAW / "msmt-register-faculties.csv.txt"


def read_csv(path: Path) -> str:
    return path.read_bytes().decode(ENCODING)


RID = re.compile(r"^[0-9A-Za-z]{5}$")


def rows(text: str, min_fields: int, rid_index: int | None = None) -> list[dict[str, str]]:
    lines = text.splitlines()
    if not lines:
        return []
    header = [part.strip() for part in lines[0].rstrip("\r").strip().strip(";").split(";")]
    records: list[dict[str, str]] = []
    buf = ""
    for line in lines[1:]:
        buf = f"{buf}\n{line}" if buf else line
        parts = [part.strip() for part in buf.split(";")]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        if len(parts) < min_fields:
            continue
        if rid_index is not None and (rid_index >= len(parts) or not RID.match(parts[rid_index])):
            continue
        values = parts[: len(header)]
        while len(values) < len(header):
            values.append("")
        records.append(dict(zip(header, values, strict=False)))
        buf = ""
    return records


def normalize_url(host: str) -> str | None:
    host = host.strip()
    if not host:
        return None
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    host = re.sub(r"^/+", "", host)
    return f"https://{host}".rstrip("/")


def parse_institutions() -> list[dict]:
    records = []
    for row in rows(read_csv(INST_CSV), min_fields=12, rid_index=4):
        rid = row.get("rid", "").strip()
        if not rid:
            continue
        records.append(
            {
                "rid": rid,
                "msmtCode": f"VS_{rid}",
                "officialName": re.sub(r"\s+", " ", row.get("nazev_cz", "")).strip(),
                "legalTypeOriginal": row.get("typ_VS", "").strip(),
                "ownershipOriginal": row.get("text_forma_VS", "").strip(),
                "region": row.get("kraj", "").strip(),
                "seat": re.sub(r"\s+", " ", row.get("sidlo", "")).strip(),
                "ico": row.get("ic", "").strip(),
                "dataMailbox": row.get("datova_schranka", "").strip(),
                "webHost": row.get("web", "").strip(),
                "officialUrl": normalize_url(row.get("web", "")),
                "statutoryRepresentative": re.sub(r"\s+", " ", row.get("statutarni_zastupce", "")).strip() or None,
            }
        )
    return records


def parse_faculties() -> list[dict]:
    records = []
    for row in rows(read_csv(FAC_CSV), min_fields=3, rid_index=2):
        name = re.sub(r"\s+", " ", row.get("nazev_cz", "")).strip()
        rid_f = row.get("rid_f", "").strip()
        rid = row.get("rid", "").strip()
        if not rid_f or not rid:
            continue
        if name.casefold().startswith("celoškolské pracoviště"):
            continue
        records.append(
            {
                "id": f"msmt-f-{rid_f.lower()}",
                "facultyRid": rid_f,
                "institutionRid": rid,
                "institutionId": f"msmt-vs_{rid.lower()}",
                "officialName": name,
                "officialUrl": normalize_url(row.get("web", "")),
            }
        )
    records.sort(key=lambda item: (item["institutionRid"], item["officialName"].casefold()))
    return records


def merge_into_baseline(institutions: list[dict]) -> dict:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    by_code = {item["msmtCode"].upper(): item for item in institutions}
    matched = 0
    with_url = 0
    for item in payload["institutions"]:
        extra = by_code.get(item["msmtCode"].upper())
        if not extra:
            continue
        matched += 1
        item["ico"] = extra["ico"] or None
        item["seat"] = extra["seat"] or None
        item["dataMailbox"] = extra["dataMailbox"] or None
        item["webHost"] = extra["webHost"] or None
        if extra["officialUrl"]:
            item["officialUrl"] = extra["officialUrl"]
            item["officialUrlSource"] = "https://regvssp.msmt.cz/registrvssp/cvslist.aspx"
            item["officialUrlNote"] = "Hostname taken from the official MŠMT CSV (VŠ) export. https:// was prefixed when the export had no scheme; live homepage was not re-checked."
            with_url += 1
        if extra["statutoryRepresentative"]:
            item["statutoryRepresentative"] = extra["statutoryRepresentative"]
    payload["csvMerge"] = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceUrl": "https://regvssp.msmt.cz/registrvssp/cvslist.aspx",
        "encoding": ENCODING,
        "matchedInstitutions": matched,
        "institutionsWithUrl": with_url,
        "extraction": "ASP.NET POST of CSV (VŠ) from the official register list",
    }
    return payload


def main() -> None:
    institutions = parse_institutions()
    faculties = parse_faculties()
    payload = merge_into_baseline(institutions)
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    FACULTIES_OUT.write_text(
        json.dumps(
            {
                "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "dataClass": "official_register_extract",
                "catalogKind": "baseline_not_published",
                "sourceUrl": "https://regvssp.msmt.cz/registrvssp/cvslist.aspx",
                "extraction": "ASP.NET POST of CSV (F); celoškolské pracoviště rows dropped",
                "encoding": ENCODING,
                "note": "Faculty names and optional websites from the official register. These are not independent universities and are not a programme catalogue.",
                "counts": {
                    "faculties": len(faculties),
                    "institutionsWithFaculties": len({item["institutionRid"] for item in faculties}),
                },
                "faculties": faculties,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "csvInstitutions": len(institutions),
                "csvWithUrl": sum(bool(item["officialUrl"]) for item in institutions),
                "faculties": len(faculties),
                "baselineMatched": payload["csvMerge"]["matchedInstitutions"],
                "baselineWithUrl": payload["csvMerge"]["institutionsWithUrl"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

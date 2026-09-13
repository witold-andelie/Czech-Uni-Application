"""Parse one page of MŠMT programme-list HTML. Not a published admissions catalogue."""
from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "work" / "raw" / "2026-09-06"
RAW = RAW_DIR / "msmt-programmes-charles.html"
CSV = RAW_DIR / "msmt-programmes-charles.csv.txt"
OUT = ROOT / "data" / "sources" / "msmt-programmes-charles-tracer.json"
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"

DEGREE = {
    "bakalářský": "bachelor",
    "magisterský": "master",
    "navazující magisterský": "master",
    "doktorský": "doctorate",
}
LANGUAGE = {
    "angličtina": "en",
    "čeština": "cs",
    "němčina": "de",
    "francouzština": "fr",
    "ruština": "ru",
    "italština": "it",
    "polština": "pl",
}

ROW = re.compile(
    r"<tr>\s*<td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td>"
    r"<td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td>"
    r"<td>(.*?)</td><td>(.*?)</td><td>.*?(SP_\d+)",
    re.S,
)


def clean(value: str) -> str:
    text = value.replace("<br />", " / ").replace("<br/>", " / ").replace("<br>", " / ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse(html: str) -> list[dict]:
    records = []
    for kind, title, degree, programme, school, faculty, form, isced, years, language, code in ROW.findall(html):
        records.append(
            {
                "msmtProgrammeCode": code,
                "kindOriginal": clean(kind),
                "titleOriginal": clean(title),
                "degreeOriginal": clean(degree),
                "degree": DEGREE.get(clean(degree), "unknown"),
                "programmeNameOriginal": clean(programme),
                "institutionName": clean(school),
                "facultyName": clean(faculty),
                "studyFormOriginal": clean(form),
                "iscedF": clean(isced),
                "standardYears": clean(years),
                "teachingLanguageOriginal": clean(language),
                "teachingLanguage": LANGUAGE.get(clean(language), "unknown"),
            }
        )
    return records


KNOWN_DEGREE = set(DEGREE)


def parse_csv(text: str) -> list[dict]:
    lines = text.splitlines()
    if not lines:
        return []
    header = [part.strip() for part in lines[0].strip(";").split(";")]
    records = []
    buf = ""
    for line in lines[1:]:
        buf = f"{buf}\n{line}" if buf else line
        parts = [part.strip() for part in buf.split(";")]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        if len(parts) < 12:
            continue
        degree = parts[3] if len(parts) > 3 else ""
        if degree not in KNOWN_DEGREE:
            continue
        row = dict(zip(header, parts, strict=False))
        records.append(
            {
                "kindOriginal": row.get("DRUH", ""),
                "titleOriginal": row.get("NÁZEV SP/SO", ""),
                "degreeOriginal": row.get("TYP SP", ""),
                "degree": DEGREE.get(row.get("TYP SP", ""), "unknown"),
                "programmeNameOriginal": row.get("NÁZEV SP", ""),
                "institutionName": row.get("VYSOKÁ ŠKOLA", ""),
                "facultyName": row.get("FAKULTA", ""),
                "studyFormOriginal": row.get("FS", ""),
                "iscedF": row.get("ISCED-F", ""),
                "standardYears": row.get("SDS", ""),
                "teachingLanguageOriginal": row.get("JAZYK", ""),
                "teachingLanguage": LANGUAGE.get(row.get("JAZYK", ""), "unknown"),
                "accreditationValidToOriginal": row.get("PLATNOST AKREDITACE DO", "") or None,
                "newAccreditation": row.get("NOVÁ AKREDITACE", "") or None,
            }
        )
        buf = ""
    return records


def count_facets(records: list[dict]) -> dict:
    languages: dict[str, int] = {}
    degrees: dict[str, int] = {}
    for item in records:
        languages[item["teachingLanguage"]] = languages.get(item["teachingLanguage"], 0) + 1
        degrees[item["degree"]] = degrees.get(item["degree"], 0) + 1
    return {"languages": languages, "degrees": degrees, "total": len(records)}


def parse_school_csv(path: Path) -> list[dict]:
    return parse_csv(path.read_bytes().decode("cp1250"))


def write_charles_tracer(records: list[dict], first_page: list[dict]) -> None:
    facets = count_facets(records)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_register_extract",
        "catalogKind": "tracer_not_published",
        "sourceUrl": "https://regvssp.msmt.cz/registrvssp/csplist.aspx",
        "institution": "Univerzita Karlova",
        "msmtCode": "VS_11000",
        "totalOnRegister": len(records),
        "parsedFromFirstPage": len(first_page),
        "extraction": "ASP.NET POST of Export CSV from csplist.aspx after institution Detail",
        "counts": {"languages": facets["languages"], "degrees": facets["degrees"]},
        "note": "Official programme/field inventory for one HEI. Not an admissions offering.",
        "programmes": records,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_school_programmes(msmt_code: str, institution_id: str, official_name: str, records: list[dict]) -> Path:
    facets = count_facets(records)
    programmes_dir = ROOT / "data" / "sources" / "programmes"
    programmes_dir.mkdir(parents=True, exist_ok=True)
    path = programmes_dir / f"{msmt_code.lower()}.json"
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_register_extract",
        "catalogKind": "inventory_not_published",
        "sourceUrl": "https://regvssp.msmt.cz/registrvssp/csplist.aspx",
        "msmtCode": msmt_code,
        "institutionId": institution_id,
        "officialName": official_name,
        "counts": facets,
        "note": "Accredited/delivered programmes from the official register. Not imported as applyable offerings.",
        "programmes": records,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def csv_for_code(code: str) -> Path | None:
    path = RAW_DIR / f"msmt-programmes-{code.lower()}.csv.txt"
    if path.exists():
        return path
    if code == "VS_11000" and CSV.exists():
        return CSV
    return None


def main() -> None:
    from apply_cscse_list import LISTED

    first_page = parse(RAW.read_text(encoding="utf-8")) if RAW.exists() else []
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {"institutions": []}
    listed_by_code = {item["msmtCode"]: item for item in LISTED}
    listed_codes = set(listed_by_code)
    schools = []
    failed = []
    all_records = 0
    language_totals: dict[str, int] = {}
    degree_totals: dict[str, int] = {}
    for item in baseline.get("institutions") or []:
        code = item["msmtCode"]
        path = csv_for_code(code)
        if path is None:
            if code in listed_codes:
                failed.append({"msmtCode": code, "reason": "csv_missing", "required": True})
            else:
                failed.append({"msmtCode": code, "reason": "csv_missing", "required": False})
            continue
        records = parse_school_csv(path)
        if not records:
            failed.append(
                {
                    "msmtCode": code,
                    "reason": "csv_empty_or_unparsed",
                    "bytes": path.stat().st_size,
                    "required": code in listed_codes,
                }
            )
            continue
        facets = count_facets(records)
        listed = listed_by_code.get(code)
        schools.append(
            {
                "msmtCode": code,
                "institutionId": f"msmt-{code.lower()}",
                "officialName": item["officialName"],
                "listedNameZh": listed["zh"] if listed else None,
                "sourceFile": str(path.relative_to(ROOT)).replace("\\", "/"),
                "counts": facets,
                "programmes": records,
            }
        )
        all_records += facets["total"]
        for key, value in facets["languages"].items():
            language_totals[key] = language_totals.get(key, 0) + value
        for key, value in facets["degrees"].items():
            degree_totals[key] = degree_totals.get(key, 0) + value
        if code == "VS_11000":
            write_charles_tracer(records, first_page)

    required_failed = [item for item in failed if item.get("required")]
    index = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_register_extract",
        "catalogKind": "inventory_not_published",
        "sourceUrl": "https://regvssp.msmt.cz/registrvssp/csplist.aspx",
        "scope": "msmt_register_harvested",
        "extraction": "ASP.NET POST of Export CSV from csplist.aspx after institution Detail",
        "note": "Accredited/delivered programme inventory from the official register. Not an admissions catalogue: no application window, tuition or apply URL. Not written to data/published/.",
        "counts": {
            "institutionsExpected": len(baseline.get("institutions") or []),
            "institutionsParsed": len(schools),
            "institutionsFailed": len(failed),
            "requiredFailed": len(required_failed),
            "programmes": all_records,
            "languages": language_totals,
            "degrees": degree_totals,
        },
        "failed": failed,
        "institutions": [
            {
                "msmtCode": item["msmtCode"],
                "institutionId": item["institutionId"],
                "officialName": item["officialName"],
                "listedNameZh": item["listedNameZh"],
                "sourceFile": item["sourceFile"],
                "counts": item["counts"],
            }
            for item in schools
        ],
    }
    index_path = ROOT / "data" / "sources" / "msmt-programmes-cscse24.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    programmes_dir = ROOT / "data" / "sources" / "programmes"
    programmes_dir.mkdir(parents=True, exist_ok=True)
    for item in schools:
        (programmes_dir / f"{item['msmtCode'].lower()}.json").write_text(
            json.dumps(
                {
                    "generatedAt": index["generatedAt"],
                    "dataClass": "official_register_extract",
                    "catalogKind": "inventory_not_published",
                    "sourceUrl": index["sourceUrl"],
                    "msmtCode": item["msmtCode"],
                    "institutionId": item["institutionId"],
                    "officialName": item["officialName"],
                    "counts": item["counts"],
                    "note": index["note"],
                    "programmes": item["programmes"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    if BASELINE.exists():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        parsed = {item["msmtCode"]: item for item in schools}
        for item in baseline["institutions"]:
            hit = parsed.get(item["msmtCode"])
            if not hit:
                if item["msmtCode"] in listed_by_code:
                    item.pop("programmeInventory", None)
                continue
            item["programmeInventory"] = {
                "total": hit["counts"]["total"],
                "sourceUrl": "https://regvssp.msmt.cz/registrvssp/csplist.aspx",
                "languages": hit["counts"]["languages"],
                "degrees": hit["counts"]["degrees"],
                "note": "Accredited/delivered programmes from the official register. Not imported as applyable offerings.",
            }
        baseline["programmeInventoryApply"] = {
            "scope": "msmt_register_harvested",
            "institutionsParsed": len(schools),
            "programmes": all_records,
            "failed": failed,
        }
        BASELINE.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(index["counts"], ensure_ascii=False))
    if required_failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

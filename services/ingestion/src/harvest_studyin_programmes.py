"""Harvest the official Study in Czechia programme directory.

The DZS directory is a volatile discovery/admissions source.  The MŠMT
register remains the legal programme baseline.  This module keeps every DZS
programme UUID, including study-form variants, and refuses a partial paged
result.  It writes candidate data only; publication and three-locale review
remain separate.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
OUT = ROOT / "data" / "sources" / "admissions" / "studyin-programmes.json"
RUNS = ROOT / "work" / "runs"
BASE_URL = "https://studyin.gov.cz"
AJAX_URL = f"{BASE_URL}/ajax/programsearch/applyfilter"
SWITCH_PAGE_URL = f"{BASE_URL}/ajax/programsearch/switchpage"
DIRECTORY_URL = f"{BASE_URL}/study-programmes/"
PAGE_SIZE = 1000
REQUEST_DELAY_SECONDS = 1.0
UA = "CzechUniApplyHarvest/0.2 (offline ingestion; official-source verification)"

ARTICLE_RE = re.compile(r"<article\b[^>]*>.*?</article>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")

# DZS display names occasionally use a current brand or legal suffix that is
# different from the current MŠMT register spelling.  Every alias is explicit;
# fuzzy matching is deliberately avoided for legal institution identity.
INSTITUTION_NAME_ALIASES = {
    "ambis univerzita": "ambis vysoka skola a s",
    "skoda auto vysoka skola z u": "skoda auto vysoka skola o p s",
}


class HarvestIncomplete(RuntimeError):
    """Raised when a paged official response cannot be proven complete."""


def visible_text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", fragment)
    fragment = re.sub(
        r"(?is)<[^>]*class=[\"'][^\"']*\bsr-only\b[^\"']*[\"'][^>]*>.*?</[^>]+>",
        " ",
        fragment,
    )
    return WS_RE.sub(" ", unescape(TAG_RE.sub(" ", fragment))).strip()


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return WS_RE.sub(" ", value).strip()


def _attribute(fragment: str, name: str) -> str | None:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*([\"'])(.*?)\1", fragment, re.I | re.S)
    return unescape(match.group(2)).strip() if match else None


def _label_key(label: str) -> str | None:
    normalized = _normalize(label.rstrip(":"))
    mapping = {
        "study type": "studyType",
        "typ studia": "studyType",
        "study form": "studyForms",
        "forma studia": "studyForms",
        "specialization": "field",
        "obor studia": "field",
        "study language": "studyLanguage",
        "jazyk studia": "studyLanguage",
        "study duration": "duration",
        "delka studia": "duration",
        "credits": "credits",
        "kredity": "credits",
        "study fee": "tuition",
        "poplatek za studium": "tuition",
    }
    return mapping.get(normalized)


def _degree(value: str) -> str:
    normalized = _normalize(value)
    if "doctoral" in normalized or "doktorsky" in normalized:
        return "d"
    if "master" in normalized or "magistersky" in normalized:
        return "m"
    if "bachelor" in normalized or "bakalarsky" in normalized:
        return "b"
    return "unknown"


def _language(value: str) -> str:
    normalized = _normalize(value)
    names = {
        "english": "en",
        "anglictina": "en",
        "czech": "cs",
        "cestina": "cs",
        "german": "de",
        "nemcina": "de",
        "french": "fr",
        "francouzstina": "fr",
        "russian": "ru",
        "rustina": "ru",
        "polish": "pl",
        "polstina": "pl",
        "italian": "it",
        "italstina": "it",
        "slovak": "sk",
        "slovenstina": "sk",
    }
    return names.get(normalized, "und")


def _number(value: str) -> float | None:
    match = re.search(r"\d+(?:[.,]\d+)?", value.replace(" ", ""))
    return float(match.group(0).replace(",", ".")) if match else None


def _tuition(value: str) -> dict | None:
    match = re.search(r"([\d][\d\s.,]*)\s*(CZK|EUR|USD|CHF|GBP|Kč)\b", value, re.I)
    if not match:
        return None
    numeric = match.group(1).replace(" ", "")
    if "," in numeric and "." in numeric:
        # The official English directory uses e.g. 2,500.00.  Whichever
        # separator occurs last is the decimal mark.
        if numeric.rfind(".") > numeric.rfind(","):
            numeric = numeric.replace(",", "")
        else:
            numeric = numeric.replace(".", "").replace(",", ".")
    elif numeric.count(",") == 1 and len(numeric.rsplit(",", 1)[1]) <= 2:
        numeric = numeric.replace(",", ".")
    else:
        numeric = numeric.replace(",", "")
    amount = float(numeric)
    currency = "CZK" if match.group(2).casefold() in {"czk", "kč"} else match.group(2).upper()
    return {"amount": amount, "currency": currency, "period": "unknown"}


def _school_and_faculty(fragment: str) -> tuple[str, str | None]:
    text = visible_text(fragment)
    match = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", text)
    if not match:
        return text, None
    return match.group(1).strip(), match.group(2).strip() or None


def parse_listing_card(card: str, locale: str) -> dict:
    item_match = re.search(
        r"<input\b[^>]*\bname=[\"']itemId[\"'][^>]*>", card, re.I | re.S
    )
    item_id = _attribute(item_match.group(0), "value") if item_match else None
    heading = re.search(r"<h3\b[^>]*>.*?<a\b([^>]*)>(.*?)</a>.*?</h3>", card, re.I | re.S)
    if not item_id or not heading:
        raise HarvestIncomplete("Programme card is missing its official UUID or detail link")
    href = _attribute(heading.group(1), "href")
    title = visible_text(heading.group(2))
    if not href or not title:
        raise HarvestIncomplete(f"Programme {item_id} is missing title or detail URL")

    school_block = re.search(r"<p\b[^>]*class=[\"'][^\"']*font-semibold[^\"']*[\"'][^>]*>(.*?)</p>", card, re.I | re.S)
    if not school_block:
        raise HarvestIncomplete(f"Programme {item_id} is missing institution text")
    institution, faculty = _school_and_faculty(school_block.group(1))

    city = None
    location = re.search(r"<a\b[^>]*google\.com/maps[^>]*>(.*?)</a>", card, re.I | re.S)
    if location:
        city = visible_text(location.group(1)) or None

    fields: dict[str, str] = {}
    for list_item in re.findall(r"<li\b[^>]*>(.*?)</li>", card, re.I | re.S):
        tooltip = re.search(r"<span\b[^>]*role=[\"']tooltip[\"'][^>]*>(.*?)</span>", list_item, re.I | re.S)
        if not tooltip:
            continue
        key = _label_key(visible_text(tooltip.group(1)))
        if not key:
            continue
        without_tooltip = list_item[: tooltip.start()] + list_item[tooltip.end() :]
        value = visible_text(without_tooltip)
        if value:
            fields[key] = value

    forms = [part.strip() for part in (fields.get("studyForms") or "").split(",") if part.strip()]
    return {
        "id": item_id,
        "sourceLocale": locale,
        "title": title,
        "institutionName": institution,
        "facultyName": faculty,
        "city": city,
        "degree": _degree(fields.get("studyType", "")),
        "studyTypeOriginal": fields.get("studyType"),
        "studyForms": forms,
        "field": fields.get("field"),
        "studyLanguage": _language(fields.get("studyLanguage", "")),
        "studyLanguageOriginal": fields.get("studyLanguage"),
        "durationYears": _number(fields.get("duration", "")),
        "credits": _number(fields.get("credits", "")),
        "tuition": _tuition(fields.get("tuition", "")),
        "officialDirectoryUrl": urllib.parse.urljoin(BASE_URL, href),
    }


def parse_listing_response(body: str, locale: str) -> tuple[int, list[dict]]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HarvestIncomplete(f"Study in Czechia returned invalid JSON for {locale}") from exc
    blocks = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(blocks, list):
        raise HarvestIncomplete(f"Study in Czechia response has no data blocks for {locale}")
    block = next(
        (
            item
            for item in blocks
            if isinstance(item, dict)
            and item.get("targetBlock") == "#programSearchListContainer"
            and isinstance(item.get("content"), str)
        ),
        None,
    )
    if block is None:
        raise HarvestIncomplete(f"Study in Czechia response has no programme list for {locale}")
    content = block["content"]
    text = visible_text(content[:3000])
    total_match = re.search(r"(?:Results found|Nalezeno výsledků)\s*:\s*(\d+)", text, re.I)
    if not total_match:
        raise HarvestIncomplete(f"Study in Czechia response has no result count for {locale}")
    total = int(total_match.group(1))
    cards = [parse_listing_card(card, locale) for card in ARTICLE_RE.findall(content)]
    return total, cards


FetchPage = Callable[[str], tuple[int, str]]


def request(url: str, timeout: int = 60) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json,text/html;q=0.9"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace") if error.fp else ""
        return error.code, body
    except Exception:
        return 0, ""


def listing_url(locale: str, page: int, page_size: int, *, only_open: bool) -> str:
    query = {
        "pageSize": str(page_size),
        "page": str(page),
        "orderBy": "title_sort:asc",
        "language": locale,
    }
    if only_open:
        query["openApplicationsOnly"] = "true"
    endpoint = AJAX_URL if page == 1 else SWITCH_PAGE_URL
    return f"{endpoint}?{urllib.parse.urlencode(query)}"


def fetch_locale(
    locale: str,
    fetch_page: FetchPage = request,
    *,
    only_open: bool = False,
    page_size: int = PAGE_SIZE,
    sleep: Callable[[float], None] = time.sleep,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
) -> tuple[list[dict], dict]:
    records: list[dict] = []
    attempts: list[dict] = []
    expected_total: int | None = None
    expected_pages: int | None = None
    page = 1
    while expected_pages is None or page <= expected_pages:
        if page > 1 and delay_seconds:
            sleep(delay_seconds)
        url = listing_url(locale, page, page_size, only_open=only_open)
        status, body = fetch_page(url)
        ok = status == 200 and bool(body.strip())
        attempt = {"url": url, "page": page, "status": status, "ok": ok}
        attempts.append(attempt)
        if not ok:
            raise HarvestIncomplete(f"Study in Czechia {locale} page {page} failed with HTTP {status}")
        total, rows = parse_listing_response(body, locale)
        attempt["records"] = len(rows)
        attempt["reportedTotal"] = total
        if expected_total is None:
            expected_total = total
            expected_pages = max(1, math.ceil(total / page_size)) if total else 1
        elif total != expected_total:
            raise HarvestIncomplete(
                f"Study in Czechia {locale} total changed during pagination: {expected_total} -> {total}"
            )
        records.extend(rows)
        page += 1

    ids = [item["id"] for item in records]
    if len(set(ids)) != len(ids):
        raise HarvestIncomplete(f"Study in Czechia {locale} returned duplicate programme UUIDs")
    if len(records) != expected_total:
        raise HarvestIncomplete(
            f"Study in Czechia {locale} pagination was partial: {len(records)} != {expected_total}"
        )
    return records, {
        "locale": locale,
        "onlyOpen": only_open,
        "reportedTotal": expected_total,
        "records": len(records),
        "pagesExpected": expected_pages,
        "pagesSucceeded": len(attempts),
        "attempts": attempts,
    }


def _baseline_index(institutions: list[dict]) -> dict[str, str]:
    index = {
        _normalize(str(item.get("officialName") or "")): str(item["id"])
        for item in institutions
        if item.get("id") and item.get("officialName")
    }
    for alias, official_name in INSTITUTION_NAME_ALIASES.items():
        institution_id = index.get(official_name)
        if institution_id:
            index[alias] = institution_id
    return index


def merge_locales(en_rows: list[dict], cs_rows: list[dict], institutions: list[dict]) -> tuple[list[dict], dict]:
    en_by_id = {item["id"]: item for item in en_rows}
    cs_by_id = {item["id"]: item for item in cs_rows}
    if set(en_by_id) != set(cs_by_id):
        only_en = sorted(set(en_by_id) - set(cs_by_id))
        only_cs = sorted(set(cs_by_id) - set(en_by_id))
        raise HarvestIncomplete(
            f"Study in Czechia locale UUID sets differ: only-en={len(only_en)}, only-cs={len(only_cs)}"
        )
    baseline = _baseline_index(institutions)
    merged: list[dict] = []
    unmapped: dict[str, int] = {}
    for item_id in sorted(en_by_id):
        en = en_by_id[item_id]
        cs = cs_by_id[item_id]
        institution_id = baseline.get(_normalize(cs["institutionName"]))
        if institution_id is None:
            unmapped[cs["institutionName"]] = unmapped.get(cs["institutionName"], 0) + 1
        merged.append(
            {
                "id": item_id,
                "institutionId": institution_id,
                "institutionNames": {"en": en["institutionName"], "cs": cs["institutionName"]},
                "facultyNames": {"en": en.get("facultyName"), "cs": cs.get("facultyName")},
                "titles": {"en": en["title"], "cs": cs["title"]},
                "city": en.get("city") or cs.get("city"),
                "degree": en["degree"] if en["degree"] != "unknown" else cs["degree"],
                "studyForms": {"en": en["studyForms"], "cs": cs["studyForms"]},
                "fields": {"en": en.get("field"), "cs": cs.get("field")},
                "studyLanguage": en["studyLanguage"] if en["studyLanguage"] != "und" else cs["studyLanguage"],
                "durationYears": en.get("durationYears") or cs.get("durationYears"),
                "credits": en.get("credits") if en.get("credits") is not None else cs.get("credits"),
                "tuition": en.get("tuition") or cs.get("tuition"),
                "officialDirectoryUrl": en["officialDirectoryUrl"],
                "sourceStableId": item_id,
            }
        )
    return merged, {
        "mappedRecords": sum(item["institutionId"] is not None for item in merged),
        "unmappedRecords": sum(item["institutionId"] is None for item in merged),
        "mappedInstitutions": len({item["institutionId"] for item in merged if item["institutionId"]}),
        "unmappedInstitutionNames": [
            {"name": name, "records": count}
            for name, count in sorted(unmapped.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
    }


def harvest_catalog(
    fetch_page: FetchPage = request,
    *,
    institutions: list[dict] | None = None,
    page_size: int = PAGE_SIZE,
    sleep: Callable[[float], None] = time.sleep,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    now: datetime | None = None,
) -> dict:
    institutions = institutions if institutions is not None else json.loads(BASELINE.read_text(encoding="utf-8"))["institutions"]
    en_rows, en_run = fetch_locale(
        "en", fetch_page, page_size=page_size, sleep=sleep, delay_seconds=delay_seconds
    )
    cs_rows, cs_run = fetch_locale(
        "cs", fetch_page, page_size=page_size, sleep=sleep, delay_seconds=delay_seconds
    )
    open_rows, open_run = fetch_locale(
        "en",
        fetch_page,
        only_open=True,
        page_size=page_size,
        sleep=sleep,
        delay_seconds=delay_seconds,
    )
    records, mapping = merge_locales(en_rows, cs_rows, institutions)
    open_ids = {item["id"] for item in open_rows}
    unknown_open = sorted(open_ids - {item["id"] for item in records})
    if unknown_open:
        raise HarvestIncomplete(f"Open-only result contains {len(unknown_open)} UUIDs absent from the full result")
    for item in records:
        # Absence from this secondary directory's open filter is not evidence
        # that the university has closed the programme.  University/faculty
        # admissions sources remain authoritative for windows and closure.
        item["directoryReportsApplicationsOpen"] = item["id"] in open_ids
        item["applicationStatus"] = "directory_open" if item["id"] in open_ids else "not_reported_open"

    current = now or datetime.now(timezone.utc)
    return {
        "generatedAt": current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceUrl": DIRECTORY_URL,
        "dataClass": "official_programme_discovery",
        "catalogKind": "candidate_not_published",
        "note": (
            "Official DZS directory cross-check for volatile programme facts. MŠMT remains the legal baseline; "
            "absence from the DZS open filter never means closed. An open flag still requires the programme detail "
            "and university application target before publication."
        ),
        "counts": {
            "programmes": len(records),
            "openApplications": len(open_ids),
            "institutions": len({item["institutionId"] for item in records if item["institutionId"]}),
            "unmappedProgrammes": mapping["unmappedRecords"],
        },
        "coverage": {
            "complete": True,
            "localeUuidSetsMatch": True,
            "mapping": mapping,
            "runs": [en_run, cs_run, open_run],
        },
        "programmes": records,
    }


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest the complete official DZS programme directory")
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    if args.page_size < 1 or args.page_size > 1000:
        raise SystemExit("--page-size must be between 1 and 1000")
    payload = harvest_catalog(page_size=args.page_size)
    atomic_write(args.output, payload)
    RUNS.mkdir(parents=True, exist_ok=True)
    atomic_write(
        RUNS / "studyin-programmes-latest.json",
        {
            "generatedAt": payload["generatedAt"],
            "counts": payload["counts"],
            "coverage": payload["coverage"],
            "output": str(args.output.relative_to(ROOT)).replace("\\", "/"),
        },
    )
    print(json.dumps({"generatedAt": payload["generatedAt"], **payload["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

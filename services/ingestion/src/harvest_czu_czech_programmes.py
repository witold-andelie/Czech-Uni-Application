"""Harvest CZU's Czech-facing bachelor/master catalogue from official pages.

The public REST API on ``studuj.czu.cz`` is access restricted, so completeness
is established with two independent public signals: the catalogue count on the
homepage and the Yoast programme sitemap.  Every sitemap detail page is then
read for degree, teaching language, faculty, duration, application dates and
the official application target.  Output remains candidate data and never
bypasses the source-bound zh-CN/en/cs publication review.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable

from harvest_czu_programmes import (
    HarvestIncomplete,
    _application_status,
    _attribute,
    _duration,
    _normalize,
    _sections,
    _write_raw,
    request,
    visible_text,
)


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sources" / "admissions" / "czu-czech-programmes.json"
ENGLISH_OUT = ROOT / "data" / "sources" / "admissions" / "czu-english-programmes.json"
BASE_URL = "https://studuj.czu.cz"
CATALOGUE_URL = f"{BASE_URL}/"
SITEMAP_INDEX_URL = f"{BASE_URL}/wp-sitemap.xml"
PROGRAMMES_SITEMAP_URL = f"{BASE_URL}/programmes-sitemap.xml"
PROGRAMMES_ARCHIVE_URL = f"{BASE_URL}/programmes/"
ADMISSIONS_URL = f"{BASE_URL}/prijimaci-rizeni/"
GENERAL_APPLY_URL = "https://is.czu.cz/prihlaska/"
REQUEST_DELAY_SECONDS = 2.0

HEADING_RE = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.I | re.S)
TITLE_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)

FACULTY_NAMES = {
    "fappz": "Fakulta agrobiologie, potravinových a přírodních zdrojů",
    "fld": "Fakulta lesnická a dřevařská",
    "ftz": "Fakulta tropického zemědělství",
    "fzp": "Fakulta životního prostředí",
    "ivp": "Institut vzdělávání a poradenství",
    "pef": "Provozně ekonomická fakulta",
    "tf": "Technická fakulta",
}

CZECH_MONTHS = {
    "leden": 1,
    "ledna": 1,
    "únor": 2,
    "února": 2,
    "březen": 3,
    "března": 3,
    "duben": 4,
    "dubna": 4,
    "květen": 5,
    "května": 5,
    "červen": 6,
    "června": 6,
    "červenec": 7,
    "července": 7,
    "srpen": 8,
    "srpna": 8,
    "září": 9,
    "říjen": 10,
    "října": 10,
    "listopad": 11,
    "listopadu": 11,
    "prosinec": 12,
    "prosince": 12,
}

FetchPage = Callable[[str], tuple[int, dict[str, str], str]]


def _xml(document: str, label: str) -> ET.Element:
    try:
        return ET.fromstring(document)
    except ET.ParseError as exc:
        raise HarvestIncomplete(f"CZU Czech {label} returned invalid XML") from exc


def parse_sitemap_index(document: str) -> None:
    root = _xml(document, "sitemap index")
    urls = {
        (node.text or "").strip()
        for node in root.findall(".//{*}loc")
        if (node.text or "").strip()
    }
    if PROGRAMMES_SITEMAP_URL not in urls:
        raise HarvestIncomplete("CZU Czech sitemap index omitted the programme sitemap")


def parse_programme_sitemap(document: str) -> list[dict]:
    root = _xml(document, "programme sitemap")
    rows: list[dict] = []
    seen: set[str] = set()
    archive_seen = False
    for node in root.findall(".//{*}url"):
        loc_node = node.find("{*}loc")
        modified_node = node.find("{*}lastmod")
        url = (loc_node.text or "").strip() if loc_node is not None else ""
        if url == PROGRAMMES_ARCHIVE_URL:
            archive_seen = True
            continue
        if not url.startswith(PROGRAMMES_ARCHIVE_URL) or not url.endswith("/"):
            raise HarvestIncomplete(f"CZU Czech programme sitemap contains an unexpected URL: {url!r}")
        if url in seen:
            raise HarvestIncomplete(f"CZU Czech programme sitemap repeats a detail URL: {url}")
        seen.add(url)
        rows.append(
            {
                "officialProgrammeUrl": url,
                "sourceModifiedAt": (modified_node.text or "").strip()
                if modified_node is not None
                else None,
            }
        )
    if not archive_seen or not rows:
        raise HarvestIncomplete("CZU Czech programme sitemap omitted its archive or detail URLs")
    return rows


def parse_home_count(document: str) -> int:
    match = re.search(
        r"<span\b[^>]*class=[\"'][^\"']*\bquery-5\b[^\"']*\bcount-type-total\b[^\"']*[\"'][^>]*>\s*(\d+)\s*</span>",
        document,
        re.I | re.S,
    )
    if not match:
        raise HarvestIncomplete("CZU Czech catalogue page omitted its official result count")
    return int(match.group(1))


def _czech_date(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize(value).rstrip(".")
    numeric = re.search(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b", normalized)
    if numeric:
        try:
            return datetime(
                int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1))
            ).date().isoformat()
        except ValueError:
            return None
    named = re.search(r"\b(\d{1,2})\.?\s+([a-záčďéěíňóřšťúůýž]+)\s+(20\d{2})\b", normalized)
    if not named:
        return None
    month = CZECH_MONTHS.get(named.group(2))
    if month is None:
        return None
    try:
        return datetime(int(named.group(3)), month, int(named.group(1))).date().isoformat()
    except ValueError:
        return None


def _tuition(value: str | None) -> dict | None:
    if not value:
        return None
    match = re.search(r"(?:(€|EUR|CZK|Kč)\s*)?([\d][\d\s,.]*)(?:\s*(€|EUR|CZK|Kč))?", value, re.I)
    if not match:
        return None
    token = (match.group(1) or match.group(3) or "").casefold()
    currency = "EUR" if token in {"€", "eur"} else "CZK" if token in {"czk", "kč"} else None
    if currency is None:
        return None
    raw_number = match.group(2).replace(" ", "").replace(",", "")
    try:
        amount = float(raw_number)
    except ValueError:
        return None
    lowered = value.casefold()
    return {
        "amount": amount,
        "currency": currency,
        "period": "year" if any(token in lowered for token in ("rok", "ročn", "year")) else "unknown",
        "displayOriginal": value,
    }


def _taxonomy_classes(document: str) -> list[str]:
    matches = re.finditer(r"\bclass=([\"'])(.*?)\1", document, re.I | re.S)
    for match in matches:
        classes = match.group(2).split()
        if "programmes" in classes and "status-publish" in classes:
            return classes
    raise HarvestIncomplete("CZU Czech programme detail omitted its published taxonomy classes")


def _requirements(document: str, programme_url: str) -> tuple[str | None, list[str]]:
    heading = next(
        (
            match
            for match in HEADING_RE.finditer(document)
            if _normalize(visible_text(match.group(1))) == "požadavky na přijetí"
        ),
        None,
    )
    if heading is None:
        return None, []
    next_heading = HEADING_RE.search(document, heading.end())
    block = document[heading.end() : next_heading.start() if next_heading else len(document)]
    content = visible_text(block)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else None
    urls: list[str] = []
    for anchor in re.finditer(r"<a\b([^>]*)>", block, re.I | re.S):
        href = _attribute(anchor.group(1), "href")
        if not href:
            continue
        url = urllib.parse.urljoin(programme_url, href)
        if url.startswith("https://") and url not in urls:
            urls.append(url)
    return digest, urls


def parse_detail(document: str, expected: dict, now: datetime) -> dict:
    body = re.search(r"<body\b[^>]*\bclass=([\"'])(.*?)\1", document, re.I | re.S)
    post_match = re.search(r"\bpostid-(\d+)\b", body.group(2) if body else "")
    if post_match is None:
        raise HarvestIncomplete("CZU Czech programme detail omitted its stable post ID")
    post_id = post_match.group(1)
    title_match = TITLE_RE.search(document)
    title = visible_text(title_match.group(1)) if title_match else ""
    if not title:
        raise HarvestIncomplete(f"CZU Czech programme {post_id} omitted its title")

    classes = _taxonomy_classes(document)
    degrees = [item.removeprefix("degree-") for item in classes if item.startswith("degree-")]
    faculties = [item.removeprefix("faculty-") for item in classes if item.startswith("faculty-")]
    fields = [item.removeprefix("programme-fields-") for item in classes if item.startswith("programme-fields-")]
    degree_map = {"bakalar": "b", "magistr": "m"}
    if len(degrees) != 1 or degrees[0] not in degree_map:
        raise HarvestIncomplete(f"CZU Czech programme {post_id} has no supported single degree")
    if len(faculties) != 1 or faculties[0] not in FACULTY_NAMES:
        raise HarvestIncomplete(f"CZU Czech programme {post_id} has no supported single faculty")
    if not fields:
        raise HarvestIncomplete(f"CZU Czech programme {post_id} omitted its subject fields")

    sections = _sections(document)
    language_original = sections.get("jazyk studia")
    language_map = {"čeština": "cs", "angličtina": "en"}
    study_language = language_map.get(_normalize(language_original or ""))
    if study_language is None:
        raise HarvestIncomplete(
            f"CZU Czech programme {post_id} has an unsupported teaching language: {language_original!r}"
        )
    degree_original = _normalize(sections.get("stupeň studia") or "")
    expected_degree_terms = {"b": "bakalář", "m": "magister"}
    if expected_degree_terms[degree_map[degrees[0]]] not in degree_original:
        raise HarvestIncomplete(f"CZU Czech programme {post_id} degree classes and detail text disagree")

    start_original = sections.get("příjem přihlášek od")
    end_original = sections.get("příjem přihlášek do")
    start = _czech_date(start_original)
    end = _czech_date(end_original)
    if bool(start_original) != bool(start) or bool(end_original) != bool(end):
        raise HarvestIncomplete(f"CZU Czech programme {post_id} has an unparseable application date")
    status = _application_status(start, end, now)

    apply_url = None
    for anchor in re.finditer(r"<a\b([^>]*)>(.*?)</a>", document, re.I | re.S):
        href = _attribute(anchor.group(1), "href")
        if not href:
            continue
        candidate = urllib.parse.urljoin(expected["officialProgrammeUrl"], href)
        if "is.czu.cz/prihlaska" in candidate:
            apply_url = candidate
            break
    if apply_url and not apply_url.startswith("https://"):
        raise HarvestIncomplete(f"CZU Czech programme {post_id} has an unsafe application URL")

    requirements_hash, evidence_urls = _requirements(document, expected["officialProgrammeUrl"])
    modes_original = [
        value.strip()
        for value in re.split(r"[,/]", sections.get("druh studia") or "")
        if value.strip()
    ]
    return {
        "id": f"czu-studuj-{post_id}",
        "sourceStableId": post_id,
        "institutionId": "msmt-vs_41000",
        "titles": {"cs": title},
        "sourceLanguage": "cs",
        "studyLanguage": study_language,
        "degree": degree_map[degrees[0]],
        "faculty": {
            "slug": faculties[0],
            "nameOriginal": FACULTY_NAMES[faculties[0]],
        },
        "fieldsOriginal": sorted(set(fields)),
        "studyModesOriginal": modes_original,
        "officialProgrammeUrl": expected["officialProgrammeUrl"],
        "sourceModifiedAt": expected.get("sourceModifiedAt"),
        "durationYears": _duration(sections.get("délka studia")),
        "tuition": _tuition(sections.get("školné")),
        "applicationWindows": [
            {
                "roundOriginal": "Přijímací řízení",
                "start": start,
                "end": end,
                "datePrecision": "day" if start and end else "unknown",
                "sourceTimezone": "Europe/Prague",
                "statusAtFetch": status,
                "startOriginal": start_original,
                "endOriginal": end_original,
                "sourceUrl": expected["officialProgrammeUrl"],
            }
        ]
        if start or end
        else [],
        "applicationStatus": status,
        "applyUrl": apply_url,
        "generalApplyPortalUrl": GENERAL_APPLY_URL,
        "admissionRequirementsTextSha256": requirements_hash,
        "admissionEvidenceUrls": evidence_urls,
        "sourceHtmlSha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
        "publicationStatus": "candidate_not_published",
    }


def parse_admissions_page(document: str) -> dict:
    text = visible_text(document)
    if "přijímacího řízení" not in text.casefold() or "ČZU" not in text:
        raise HarvestIncomplete("CZU Czech admissions page did not return its expected body")
    apply_urls = [
        urllib.parse.urljoin(ADMISSIONS_URL, unescape(href))
        for href in re.findall(r"href=[\"']([^\"']+)[\"']", document, re.I)
        if "is.czu.cz/prihlaska" in href
    ]
    fee_match = re.search(r"poplatek.{0,140}?(\d[\d\s]*)\s*(?:Kč|CZK)", text, re.I)
    if not apply_urls or not fee_match:
        raise HarvestIncomplete("CZU Czech admissions page omitted its apply link or fee")
    return {
        "generalApplyPortalUrl": apply_urls[0],
        "applicationFee": {
            "amount": float(fee_match.group(1).replace(" ", "")),
            "currency": "CZK",
            "displayOriginal": fee_match.group(0),
        },
    }


def _title_key(title: str, degree: str) -> tuple[str, str]:
    normalized = _normalize(title).replace("–", "-").replace("—", "-")
    return normalized, degree


def crosscheck_english_source(programmes: list[dict], english_payload: dict | None) -> dict:
    english_payload = english_payload or {}
    reference = english_payload.get("programmes") or []
    portal = [item for item in programmes if item["studyLanguage"] == "en"]
    if not reference:
        return {
            "status": "unavailable",
            "czechPortalEnglishProgrammes": len(portal),
            "englishSourceProgrammes": 0,
        }
    portal_keys = Counter(_title_key(item["titles"]["cs"], item["degree"]) for item in portal)
    reference_keys = Counter(
        _title_key(str((item.get("titles") or {}).get("en") or ""), str(item.get("degree") or ""))
        for item in reference
    )
    missing = list((reference_keys - portal_keys).elements())
    extra = list((portal_keys - reference_keys).elements())
    return {
        "status": "agrees" if not missing and not extra else "disagrees",
        "czechPortalEnglishProgrammes": len(portal),
        "englishSourceProgrammes": len(reference),
        "missingInCzechPortal": [f"{degree}:{title}" for title, degree in missing],
        "extraInCzechPortal": [f"{degree}:{title}" for title, degree in extra],
    }


def harvest_catalog(
    fetch_page: FetchPage = request,
    *,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    raw_dir: Path | None = None,
    english_payload: dict | None = None,
) -> dict:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    generated_at = current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if raw_dir is None and fetch_page is request:
        raw_dir = ROOT / "work" / "raw" / current.date().isoformat() / "czu-studuj"
    if english_payload is None and ENGLISH_OUT.is_file():
        english_payload = json.loads(ENGLISH_OUT.read_text(encoding="utf-8"))

    attempts: list[dict] = []

    def fetch(url: str, raw_name: str) -> str:
        status, _headers, body = fetch_page(url)
        attempts.append({"url": url, "httpStatus": status, "bytes": len(body.encode("utf-8"))})
        _write_raw(raw_dir, raw_name, body)
        if status != 200 or not body:
            raise HarvestIncomplete(f"CZU Czech source fetch failed: status={status} url={url}")
        return body

    homepage = fetch(CATALOGUE_URL, "catalogue.html")
    if delay_seconds:
        sleep(delay_seconds)
    index_body = fetch(SITEMAP_INDEX_URL, "wp-sitemap.xml")
    parse_sitemap_index(index_body)
    if delay_seconds:
        sleep(delay_seconds)
    sitemap_body = fetch(PROGRAMMES_SITEMAP_URL, "programmes-sitemap.xml")
    catalogue = parse_programme_sitemap(sitemap_body)
    homepage_total = parse_home_count(homepage)
    if homepage_total != len(catalogue):
        raise HarvestIncomplete(
            f"CZU Czech catalogue total mismatch: homepage={homepage_total}, sitemap={len(catalogue)}"
        )
    if delay_seconds:
        sleep(delay_seconds)
    admissions_body = fetch(ADMISSIONS_URL, "admissions.html")
    admissions = parse_admissions_page(admissions_body)

    programmes: list[dict] = []
    seen_ids: set[str] = set()
    for item in catalogue:
        if delay_seconds:
            sleep(delay_seconds)
        slug = item["officialProgrammeUrl"].rstrip("/").split("/")[-1]
        detail = fetch(item["officialProgrammeUrl"], f"programmes/{slug}.html")
        parsed = parse_detail(detail, item, current)
        if parsed["sourceStableId"] in seen_ids:
            raise HarvestIncomplete(
                f"CZU Czech catalogue repeats post ID {parsed['sourceStableId']}"
            )
        seen_ids.add(parsed["sourceStableId"])
        parsed["generalApplyPortalUrl"] = admissions["generalApplyPortalUrl"]
        programmes.append(parsed)

    statuses = Counter(item["applicationStatus"] for item in programmes)
    degree_counts = Counter(item["degree"] for item in programmes)
    language_counts = Counter(item["studyLanguage"] for item in programmes)
    faculty_counts = Counter(item["faculty"]["slug"] for item in programmes)
    details_with_window = sum(
        bool(
            item["applicationWindows"]
            and item["applicationWindows"][0]["start"]
            and item["applicationWindows"][0]["end"]
        )
        for item in programmes
    )
    english_crosscheck = crosscheck_english_source(programmes, english_payload)
    counts = {
        "programmes": len(programmes),
        "degrees": {"bachelor": degree_counts["b"], "master": degree_counts["m"]},
        "teachingLanguages": {"cs": language_counts["cs"], "en": language_counts["en"]},
        "faculties": dict(sorted(faculty_counts.items())),
        "detailsWithCompleteWindow": details_with_window,
        "openByDetailDates": statuses["open"],
        "upcomingByDetailDates": statuses["upcoming"],
        "closedByDetailDates": statuses["closed"],
        "unknownByDetailDates": statuses["unknown"],
    }
    coverage = {
        "homepageReportedTotal": homepage_total,
        "sitemapDetailTotal": len(catalogue),
        "receivedUniqueProgrammeIds": len(seen_ids),
        "detailPagesExpected": len(catalogue),
        "detailPagesParsed": len(programmes),
        "complete": len(programmes) == homepage_total == len(catalogue) == len(seen_ids),
        "englishSourceCrosscheck": english_crosscheck,
        "claimBoundary": (
            "Completeness applies only to the bachelor/master catalogue exposed by studuj.czu.cz. "
            "It includes Czech- and English-taught records identified by each detail page, excludes "
            "doctoral programmes, and does not imply automatic formal publication."
        ),
    }
    payload = {
        "generatedAt": generated_at,
        "dataClass": "official_university_admissions_extract",
        "catalogKind": "candidate_not_published",
        "institutionId": "msmt-vs_41000",
        "institutionNameOriginal": "Česká zemědělská univerzita v Praze",
        "sourceLanguage": "cs",
        "scope": {
            "teachingLanguages": sorted(language_counts),
            "degrees": ["b", "m"],
            "claim": "official_czu_czech_portal_bachelor_master_catalogue_on_source",
            "excludes": ["doctoral programmes"],
        },
        "sourceUrls": {
            "catalogue": CATALOGUE_URL,
            "sitemapIndex": SITEMAP_INDEX_URL,
            "programmeSitemap": PROGRAMMES_SITEMAP_URL,
            "admissions": ADMISSIONS_URL,
            "generalApplyPortal": admissions["generalApplyPortalUrl"],
        },
        "applicationFee": admissions["applicationFee"],
        "counts": counts,
        "coverage": coverage,
        "attempts": attempts,
        "programmes": programmes,
    }
    if raw_dir is not None:
        _write_raw(
            raw_dir,
            "harvest-summary.json",
            json.dumps(
                {
                    "generatedAt": generated_at,
                    "counts": counts,
                    "coverage": coverage,
                    "attempts": attempts,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
    return payload


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    payload = harvest_catalog()
    atomic_write(OUT, payload)
    print(
        json.dumps(
            {
                "output": str(OUT),
                "generatedAt": payload["generatedAt"],
                "counts": payload["counts"],
                "coverage": payload["coverage"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

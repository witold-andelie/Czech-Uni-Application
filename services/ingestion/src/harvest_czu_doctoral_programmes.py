"""Cross-check CZU doctoral offerings against current faculty admissions evidence.

CZU does not expose doctoral admissions through the bachelor/master portals.
The legal programme baseline therefore comes from the compact MŠMT register
inventory, while six faculty sources provide the academic-year admission
windows.  The resulting records are candidates only and never bypass the
source-bound zh-CN/en/cs publication review.

One Faculty of Engineering regulation is an image-only PDF.  Its reviewed
transcription is guarded by the exact source SHA-256; a changed file fails
closed until a human reviews the replacement.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from harvest_czu_programmes import HarvestIncomplete, visible_text


ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "data" / "sources" / "browse" / "nine-hei-inventory.json"
OUT = ROOT / "data" / "sources" / "admissions" / "czu-doctoral-programmes.json"
INSTITUTION_ID = "msmt-vs_41000"
ACADEMIC_YEAR = "2026/2027"
GENERAL_APPLY_URL = "https://is.czu.cz/prihlaska/"
REQUEST_DELAY_SECONDS = 1.0

FetchAsset = Callable[[str], tuple[int, dict[str, str], bytes]]


SOURCE_ASSETS = (
    {
        "id": "czu-dsp-fappz-2026-2027",
        "url": "https://www.af.czu.cz/dl/150405?lang=cs",
        "kind": "pdf",
        "rawName": "fappz-admissions-2026-2027.pdf",
        "sourceLanguage": "cs",
        "expectedTokens": (
            "Nařízení děkana č. 17/2025",
            "Vyhlášení přijímacího řízení do doktorských studijních programů",
            "2026/2027",
        ),
    },
    {
        "id": "czu-dsp-pef-2026-2027",
        "url": "https://www.pef.czu.cz/dl/113306?lang=en",
        "kind": "pdf",
        "rawName": "pef-admissions-2026-2027.pdf",
        "sourceLanguage": "en",
        "expectedTokens": (
            "Dean's Regulation No. 2/2026",
            "Organization of the admission procedure for doctoral study programs",
            "2026/2027",
        ),
    },
    {
        "id": "czu-dsp-pef-czech-programmes",
        "url": (
            "https://www.pef.czu.cz/cs/r-7009-veda-a-vyzkum/"
            "r-7028-doktorske-studium/r-8126-doktorske-programy"
        ),
        "kind": "html",
        "rawName": "pef-czech-programmes.html",
        "sourceLanguage": "cs",
        "expectedTokens": (
            "Doktorské programy",
            "Podniková a odvětvová ekonomika",
            "Systémové inženýrství a informatika",
        ),
    },
    {
        "id": "czu-dsp-fzp-cs-2026-2027",
        "url": "https://www.fzp.czu.cz/dl/151487?lang=cs",
        "kind": "pdf",
        "rawName": "fzp-czech-admissions-2026-2027.pdf",
        "sourceLanguage": "cs",
        "expectedTokens": (
            "Nařízení děkana č. 14/2025",
            "studium v českém jazyce",
            "2026/2027",
        ),
    },
    {
        "id": "czu-dsp-fzp-en-2026-2027",
        "url": "https://www.fzp.czu.cz/dl/151488?lang=en",
        "kind": "pdf",
        "rawName": "fzp-english-admissions-2026-2027.pdf",
        "sourceLanguage": "en",
        "expectedTokens": (
            "Dean's Regulation No. 15/2025",
            "doctoral degree programmes taught in English",
            "2026/2027",
        ),
    },
    {
        "id": "czu-dsp-fld-2026-2027",
        "url": (
            "https://www.fld.czu.cz/en/r-9414-study/r-10989-visual-study/"
            "admission-procedures-for-doctoral-study-for-the-2026-2027-ac.html"
        ),
        "kind": "html",
        "rawName": "fld-admissions-2026-2027.html",
        "sourceLanguage": "en",
        "expectedTokens": (
            "Admission procedures for Doctoral Study for the 2026/2027 academic year",
            "Global Change Forestry",
            "For DSPs taught in Czech",
        ),
    },
    {
        "id": "czu-dsp-tf-2026-2027-page",
        "url": (
            "https://www.tf.czu.cz/cs/r-6970-veda-a-vyzkum/r-7923-aktuality-vav/"
            "prijimaci-rizeni-pro-doktorske-studium-v-akademickem-roce-20.html"
        ),
        "kind": "html",
        "rawName": "tf-admissions-2026-2027.html",
        "sourceLanguage": "cs",
        "expectedTokens": (
            "Přijímací řízení pro doktorské studium v akademickém roce 2026/2027",
            "Procesní a informační inženýrství v agrárním sektoru",
            "Engineering of Agricultural Technological Systems",
        ),
    },
    {
        "id": "czu-dsp-tf-2026-2027-scan",
        "url": "https://www.tf.czu.cz/dl/152519?lang=cs",
        "kind": "reviewed_scan",
        "rawName": "tf-regulation-1-2026.pdf",
        "sourceLanguage": "cs",
        "reviewedSha256": "3034c9b0dd94266697daf5a862a9bdb42a0d81a3005920574a5ab0dfe0987f0c",
        "reviewedAt": "2026-09-11",
        "reviewedText": (
            "Nařízení děkana TF č. 1/2026. Elektronickou přihlášku uchazeč odešle "
            "prostřednictvím UIS a její vytištěnou verzi podepíše na oddělení pro "
            "vědu a výzkum děkanátu TF do 31. 5. 2026. Přijímací zkoušky se budou "
            "konat dne 11. 6. 2026."
        ),
        "expectedTokens": (
            "Nařízení děkana TF č. 1/2026",
            "do 31. 5. 2026",
        ),
    },
    {
        "id": "czu-dsp-ftz-2026-2027",
        "url": "https://www.ftz.czu.cz/dl/147891?lang=en",
        "kind": "pdf",
        "rawName": "ftz-admissions-2026-2027.pdf",
        "sourceLanguage": "en",
        "expectedTokens": (
            "Regulation of the Dean No. 10/2025",
            "doctoral study programs in the 2026/2027 academic year",
            "FTZ offers doctoral studies in three doctoral study programs",
        ),
    },
)


FACULTY_RULES = {
    "Fakulta agrobiologie, potravinových a přírodních zdrojů": {
        "slug": "fappz",
        "programmeEvidence": {
            "cs": ("czu-dsp-fappz-2026-2027",),
            "en": ("czu-dsp-fappz-2026-2027",),
        },
        "windows": {
            "cs": (
                {
                    "roundOriginal": "Řádný termín",
                    "start": None,
                    "end": "2026-04-21",
                    "sourceId": "czu-dsp-fappz-2026-2027",
                    "verificationTokens": ("do 21. 04. 2026",),
                },
                {
                    "roundOriginal": "Náhradní termín",
                    "start": None,
                    "end": "2026-08-25",
                    "sourceId": "czu-dsp-fappz-2026-2027",
                    "verificationTokens": ("do 25. 08. 2026",),
                },
            ),
            "en": (
                {
                    "roundOriginal": "Regular deadline",
                    "start": None,
                    "end": "2026-03-06",
                    "sourceId": "czu-dsp-fappz-2026-2027",
                    "verificationTokens": ("do 06. 03. 2026",),
                },
                {
                    "roundOriginal": "Alternative deadline",
                    "start": None,
                    "end": "2026-04-21",
                    "sourceId": "czu-dsp-fappz-2026-2027",
                    "verificationTokens": ("do 21. 04. 2026",),
                },
            ),
        },
    },
    "Provozně ekonomická fakulta": {
        "slug": "pef",
        "programmeEvidence": {
            "cs": ("czu-dsp-pef-czech-programmes",),
            "en": ("czu-dsp-pef-2026-2027",),
        },
        "windows": {
            "cs": (
                {
                    "roundOriginal": "Admission procedure 2026",
                    "start": "2026-03-16",
                    "end": "2026-04-30",
                    "sourceId": "czu-dsp-pef-2026-2027",
                    "verificationTokens": ("March 16, 2026", "April 30, 2026"),
                },
            ),
            "en": (
                {
                    "roundOriginal": "Admission procedure 2026",
                    "start": "2026-03-16",
                    "end": "2026-04-30",
                    "sourceId": "czu-dsp-pef-2026-2027",
                    "verificationTokens": ("March 16, 2026", "April 30, 2026"),
                },
            ),
        },
    },
    "Fakulta životního prostředí": {
        "slug": "fzp",
        "programmeEvidence": {
            "cs": ("czu-dsp-fzp-cs-2026-2027",),
            "en": ("czu-dsp-fzp-en-2026-2027",),
        },
        "windows": {
            "cs": (
                {
                    "roundOriginal": "1. etapa",
                    "start": "2026-01-31",
                    "end": "2026-05-31",
                    "sourceId": "czu-dsp-fzp-cs-2026-2027",
                    "verificationTokens": ("od 31. 1. do 31. 5. 2026",),
                },
                {
                    "roundOriginal": "2. etapa",
                    "start": "2026-07-01",
                    "end": "2026-08-20",
                    "sourceId": "czu-dsp-fzp-cs-2026-2027",
                    "verificationTokens": ("od 1. 7. do 20. 8. 2026",),
                },
            ),
            "en": (
                {
                    "roundOriginal": "Stage 1",
                    "start": "2025-11-19",
                    "end": "2026-03-20",
                    "sourceId": "czu-dsp-fzp-en-2026-2027",
                    "verificationTokens": ("from 19. 11. 2025 to 20. 3. 2026",),
                },
                {
                    "roundOriginal": "Stage 2",
                    "start": "2026-07-01",
                    "end": "2026-08-20",
                    "sourceId": "czu-dsp-fzp-en-2026-2027",
                    "verificationTokens": ("from 1. 7. to 20. 8. 2026",),
                },
            ),
        },
    },
    "Fakulta lesnická a dřevařská": {
        "slug": "fld",
        "programmeEvidence": {
            "cs": ("czu-dsp-fld-2026-2027",),
            "en": ("czu-dsp-fld-2026-2027",),
        },
        "windows": {
            "cs": (
                {
                    "roundOriginal": "DSPs taught in Czech",
                    "start": "2025-10-01",
                    "end": "2026-06-07",
                    "sourceId": "czu-dsp-fld-2026-2027",
                    "verificationTokens": ("from 1 October 2025 to 7 June 2026",),
                },
            ),
            "en": (
                {
                    "roundOriginal": "DSPs taught in English",
                    "start": "2025-10-01",
                    "end": "2026-03-15",
                    "sourceId": "czu-dsp-fld-2026-2027",
                    "verificationTokens": ("from 1 October 2025 to 15 March 2026",),
                },
            ),
        },
    },
    "Technická fakulta": {
        "slug": "tf",
        "programmeEvidence": {
            "cs": ("czu-dsp-tf-2026-2027-page",),
            "en": ("czu-dsp-tf-2026-2027-page",),
        },
        "applyUrl": "https://is.czu.cz/prihlaska/zaloz_eosobu.pl?fakulta=30;",
        "windows": {
            "cs": (
                {
                    "roundOriginal": "Nařízení děkana TF č. 1/2026",
                    "start": None,
                    "end": "2026-05-31",
                    "sourceId": "czu-dsp-tf-2026-2027-scan",
                    "verificationTokens": ("do 31. 5. 2026",),
                    "extractionMethod": "human_reviewed_scan_transcription_sha256_guarded",
                },
            ),
            "en": (
                {
                    "roundOriginal": "Nařízení děkana TF č. 1/2026",
                    "start": None,
                    "end": "2026-05-31",
                    "sourceId": "czu-dsp-tf-2026-2027-scan",
                    "verificationTokens": ("do 31. 5. 2026",),
                    "extractionMethod": "human_reviewed_scan_transcription_sha256_guarded",
                },
            ),
        },
    },
    "Fakulta tropického zemědělství": {
        "slug": "ftz",
        "programmeEvidence": {
            "en": ("czu-dsp-ftz-2026-2027",),
        },
        "windows": {
            "en": (
                {
                    "roundOriginal": "Admission procedure stage 1",
                    "start": "2026-01-05",
                    "end": "2026-02-10",
                    "sourceId": "czu-dsp-ftz-2026-2027",
                    "verificationTokens": ("5 January - 10 February 2026",),
                },
                {
                    "roundOriginal": "Admission procedure stage 2",
                    "start": "2026-04-06",
                    "end": "2026-05-12",
                    "sourceId": "czu-dsp-ftz-2026-2027",
                    "verificationTokens": ("6 April - 12 May 2026",),
                },
                {
                    "roundOriginal": "Admission procedure stage 3 (may not open)",
                    "start": "2026-07-07",
                    "end": "2026-08-11",
                    "sourceId": "czu-dsp-ftz-2026-2027",
                    "verificationTokens": ("7 July - 11 August 2026", "may not be open"),
                    "conditionalOnVacancies": True,
                    "confirmedOpened": False,
                },
            ),
        },
    },
}


TITLE_ALIASES = {
    "Ochrana lesů a myslivosti": ("Ochrana lesů a myslivost",),
}


def request_asset(url: str, timeout: int = 90) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Czech-Uni-Apply/1.0 official-source-audit",
            "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKC", unescape(value)).replace("\u00ad", "")
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    return re.sub(r"[\W_]+", " ", value.casefold(), flags=re.UNICODE).strip()


def _decode_html(body: bytes, headers: dict[str, str]) -> str:
    content_type = next(
        (value for key, value in headers.items() if key.casefold() == "content-type"),
        "",
    )
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    charsets = [match.group(1)] if match else []
    charsets.extend(["utf-8", "windows-1250"])
    for charset in charsets:
        try:
            return body.decode(charset)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def _pdf_text(body: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment guard
        raise HarvestIncomplete("pypdf is required to verify CZU doctoral PDFs") from exc
    try:
        reader = PdfReader(io.BytesIO(body))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise HarvestIncomplete("CZU doctoral PDF could not be parsed") from exc


def _write_raw(raw_dir: Path | None, relative: str, body: bytes) -> None:
    if raw_dir is None:
        return
    target = raw_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)


def _extract_asset_text(spec: dict, body: bytes, headers: dict[str, str]) -> str:
    digest = hashlib.sha256(body).hexdigest()
    kind = spec["kind"]
    if kind == "reviewed_scan":
        if digest != spec["reviewedSha256"]:
            raise HarvestIncomplete(
                f"Reviewed scan changed for {spec['id']}: expected "
                f"{spec['reviewedSha256']}, got {digest}"
            )
        return spec["reviewedText"]
    if kind == "pdf":
        text = _pdf_text(body)
        if not text.strip():
            raise HarvestIncomplete(f"CZU doctoral PDF has no extractable text: {spec['id']}")
        return text
    if kind == "html":
        return visible_text(_decode_html(body, headers))
    raise HarvestIncomplete(f"Unsupported CZU doctoral source kind: {kind}")


def _load_doctoral_inventory(payload: dict) -> list[dict]:
    school = next(
        (item for item in payload.get("schools", []) if item.get("id") == INSTITUTION_ID),
        None,
    )
    if school is None:
        raise HarvestIncomplete("CZU is missing from the compact MŠMT inventory")
    records: list[dict] = []
    for row in school.get("rows", []):
        if not isinstance(row, list) or len(row) != 7:
            raise HarvestIncomplete("CZU compact inventory contains a malformed row")
        record_id, title, degree, faculty, duration, language, isced = row
        if degree != "d":
            continue
        records.append(
            {
                "id": record_id,
                "titleOriginal": title,
                "degree": degree,
                "faculty": faculty,
                "durationYears": duration,
                "studyLanguage": language,
                "iscedBroadOrNarrowCode": isced,
            }
        )
    if not records or len({item["id"] for item in records}) != len(records):
        raise HarvestIncomplete("CZU doctoral inventory is empty or repeats stable IDs")
    return records


def _window_status(window: dict, now: datetime) -> str:
    current_date = now.astimezone(ZoneInfo("Europe/Prague")).date()
    start = datetime.fromisoformat(window["start"]).date() if window.get("start") else None
    end = datetime.fromisoformat(window["end"]).date() if window.get("end") else None
    if end is not None and end < current_date:
        return "closed"
    if window.get("conditionalOnVacancies") and not window.get("confirmedOpened"):
        return "unknown"
    if start is None:
        return "unknown"
    if start > current_date:
        return "upcoming"
    if end is None or current_date <= end:
        return "open"
    return "unknown"


def _programme_status(windows: list[dict]) -> str:
    statuses = {item["statusAtFetch"] for item in windows}
    for status in ("open", "upcoming", "unknown", "closed"):
        if status in statuses:
            return status
    return "unknown"


def _verified_windows(rule: dict, language: str, assets: dict[str, dict], now: datetime) -> list[dict]:
    result: list[dict] = []
    for source_window in rule.get("windows", {}).get(language, ()):
        source_id = source_window["sourceId"]
        source = assets.get(source_id)
        if source is None:
            raise HarvestIncomplete(f"CZU doctoral window source was not fetched: {source_id}")
        folded = _fold(source["text"])
        for token in source_window.get("verificationTokens", ()):
            if _fold(token) not in folded:
                raise HarvestIncomplete(
                    f"CZU doctoral source {source_id} omitted reviewed window token {token!r}"
                )
        window = {
            "roundOriginal": source_window["roundOriginal"],
            "academicYear": ACADEMIC_YEAR,
            "start": source_window.get("start"),
            "end": source_window.get("end"),
            "datePrecision": (
                "day" if source_window.get("start") and source_window.get("end") else "end_only"
            ),
            "sourceTimezone": "Europe/Prague",
            "sourceUrl": source["url"],
            "sourceId": source_id,
            "conditionalOnVacancies": bool(source_window.get("conditionalOnVacancies")),
            "confirmedOpened": bool(source_window.get("confirmedOpened", True)),
            "extractionMethod": source_window.get("extractionMethod", source["extractionMethod"]),
        }
        window["statusAtFetch"] = _window_status(window, now)
        result.append(window)
    return result


def build_catalog(
    inventory_payload: dict,
    assets: dict[str, dict],
    *,
    now: datetime,
) -> dict:
    rows = _load_doctoral_inventory(inventory_payload)
    baseline_faculties = {item["faculty"] for item in rows}
    configured_faculties = set(FACULTY_RULES)
    if baseline_faculties != configured_faculties:
        missing = sorted(baseline_faculties - configured_faculties)
        stale = sorted(configured_faculties - baseline_faculties)
        raise HarvestIncomplete(
            f"CZU doctoral faculty configuration mismatch: missing={missing}, stale={stale}"
        )

    programmes: list[dict] = []
    faculty_coverage: list[dict] = []
    for faculty in sorted(baseline_faculties):
        rule = FACULTY_RULES[faculty]
        faculty_rows = [item for item in rows if item["faculty"] == faculty]
        faculty_programmes: list[dict] = []
        for row in faculty_rows:
            evidence_ids = tuple(rule.get("programmeEvidence", {}).get(row["studyLanguage"], ()))
            if not evidence_ids:
                raise HarvestIncomplete(
                    f"No CZU doctoral programme evidence configured for {faculty} {row['studyLanguage']}"
                )
            exact = _fold(row["titleOriginal"])
            aliases = TITLE_ALIASES.get(row["titleOriginal"], ())
            matched_ids: list[str] = []
            matched_variant: str | None = None
            for source_id in evidence_ids:
                source = assets.get(source_id)
                if source is None:
                    raise HarvestIncomplete(f"Programme source was not fetched: {source_id}")
                source_text = _fold(source["text"])
                if exact in source_text:
                    matched_ids.append(source_id)
                    continue
                for alias in aliases:
                    if _fold(alias) in source_text:
                        matched_ids.append(source_id)
                        matched_variant = alias
                        break
            if not matched_ids:
                raise HarvestIncomplete(
                    f"CZU doctoral offering was not found in faculty evidence: "
                    f"{faculty} / {row['studyLanguage']} / {row['titleOriginal']}"
                )

            windows = _verified_windows(rule, row["studyLanguage"], assets, now)
            if not windows:
                raise HarvestIncomplete(
                    f"CZU doctoral offering has no official {ACADEMIC_YEAR} window: {row['id']}"
                )
            source_ids = sorted(set(matched_ids + [item["sourceId"] for item in windows]))
            programme = {
                **row,
                "institutionId": INSTITUTION_ID,
                "sourceLanguage": row["studyLanguage"],
                "facultySlug": rule["slug"],
                "academicYear": ACADEMIC_YEAR,
                "officialProgrammeEvidenceUrls": [assets[item]["url"] for item in matched_ids],
                "admissionEvidenceUrls": [assets[item]["url"] for item in source_ids],
                "matchedSourceIds": source_ids,
                "sourceTitleVariant": matched_variant,
                "applicationWindows": windows,
                "applicationStatus": _programme_status(windows),
                "applyUrl": rule.get("applyUrl", GENERAL_APPLY_URL),
                "generalApplyPortalUrl": GENERAL_APPLY_URL,
                "publicationStatus": "candidate_not_published",
            }
            faculty_programmes.append(programme)
            programmes.append(programme)

        faculty_coverage.append(
            {
                "faculty": faculty,
                "facultySlug": rule["slug"],
                "baselineOfferings": len(faculty_rows),
                "matchedOfferings": len(faculty_programmes),
                "offeringsWithOfficialWindow": sum(
                    bool(item["applicationWindows"]) for item in faculty_programmes
                ),
                "studyLanguages": dict(
                    sorted(Counter(item["studyLanguage"] for item in faculty_rows).items())
                ),
                "applicationStatuses": dict(
                    sorted(Counter(item["applicationStatus"] for item in faculty_programmes).items())
                ),
                "sourceIds": sorted(
                    {source_id for item in faculty_programmes for source_id in item["matchedSourceIds"]}
                ),
            }
        )

    programmes.sort(key=lambda item: (item["studyLanguage"], item["titleOriginal"].casefold()))
    statuses = Counter(item["applicationStatus"] for item in programmes)
    languages = Counter(item["studyLanguage"] for item in programmes)
    all_windows = [window for item in programmes for window in item["applicationWindows"]]
    complete_window_programmes = sum(
        any(window.get("start") and window.get("end") for window in item["applicationWindows"])
        for item in programmes
    )
    generated_at = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "generatedAt": generated_at,
        "dataClass": "official_admissions_extract",
        "catalogKind": "candidate_not_published",
        "institutionId": INSTITUTION_ID,
        "institutionName": "Česká zemědělská univerzita v Praze",
        "academicYear": ACADEMIC_YEAR,
        "legalBaseline": {
            "source": inventory_payload.get("sourceUrl"),
            "sourceGeneratedAt": inventory_payload.get("generatedAt"),
            "inventoryAcademicYear": inventory_payload.get("academicYear"),
        },
        "counts": {
            "programmes": len(programmes),
            "faculties": len(faculty_coverage),
            "teachingLanguages": dict(sorted(languages.items())),
            "matchedToFacultyAdmissionEvidence": len(programmes),
            "withAnyOfficialWindow": sum(bool(item["applicationWindows"]) for item in programmes),
            "withAtLeastOneCompleteWindow": complete_window_programmes,
            "applicationWindowRecords": len(all_windows),
            "conditionalWindowRecords": sum(
                bool(item.get("conditionalOnVacancies")) for item in all_windows
            ),
            "openByOfficialDates": statuses.get("open", 0),
            "upcomingByOfficialDates": statuses.get("upcoming", 0),
            "closedByOfficialDates": statuses.get("closed", 0),
            "unknownByOfficialDates": statuses.get("unknown", 0),
            "awaitingNextAcademicYearWindow": sum(
                item["applicationStatus"] == "closed" for item in programmes
            ),
        },
        "coverage": {
            "complete": len(programmes) == len(rows) and all(
                item["matchedOfferings"] == item["baselineOfferings"]
                and item["offeringsWithOfficialWindow"] == item["baselineOfferings"]
                for item in faculty_coverage
            ),
            "declaredScope": (
                "All CZU doctoral offerings in the current compact MŠMT register baseline, "
                "cross-checked against the six faculties' official 2026/2027 admissions evidence"
            ),
            "baselineOfferings": len(rows),
            "matchedOfferings": len(programmes),
            "baselineFaculties": len(baseline_faculties),
            "facultiesWithProgrammeAndWindowEvidence": len(faculty_coverage),
            "facultyCoverage": faculty_coverage,
            "allApplicationWindowsClosedAtFetch": bool(programmes)
            and all(item["applicationStatus"] == "closed" for item in programmes),
            "nextAcademicYearWindowEvidenceInThisArtifact": False,
            "claimBoundary": (
                "Completeness is limited to matching the MŠMT CZU doctoral baseline to the "
                "configured 2026/2027 faculty evidence. It does not assert that a 2027/2028 "
                "round has or has not been published elsewhere, does not infer an unannounced "
                "second round, and does not publish untranslated candidate records."
            ),
        },
        "sources": [
            {
                "id": source_id,
                "url": item["url"],
                "httpStatus": item["httpStatus"],
                "contentType": item["contentType"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "sourceLanguage": item["sourceLanguage"],
                "extractionMethod": item["extractionMethod"],
                "reviewedAt": item.get("reviewedAt"),
            }
            for source_id, item in sorted(assets.items())
        ],
        "programmes": programmes,
        "publicationStatus": "candidate_not_published",
        "note": (
            "Language is a programme attribute, independent of UI locale. Source-listed "
            "application end dates are closed as of the fetch time; no future round is inferred."
        ),
    }


def harvest_catalog(
    fetch_asset: FetchAsset = request_asset,
    *,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    raw_dir: Path | None = None,
    inventory_payload: dict | None = None,
) -> dict:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if inventory_payload is None:
        inventory_payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if raw_dir is None and fetch_asset is request_asset:
        raw_dir = ROOT / "work" / "raw" / current.date().isoformat() / "czu-doctoral"

    assets: dict[str, dict] = {}
    for index, spec in enumerate(SOURCE_ASSETS):
        if index and delay_seconds:
            sleep(delay_seconds)
        status, headers, body = fetch_asset(spec["url"])
        _write_raw(raw_dir, spec["rawName"], body)
        if status != 200 or not body:
            raise HarvestIncomplete(
                f"CZU doctoral source fetch failed: status={status} url={spec['url']}"
            )
        text = _extract_asset_text(spec, body, headers)
        folded = _fold(text)
        for token in spec.get("expectedTokens", ()):
            if _fold(token) not in folded:
                raise HarvestIncomplete(
                    f"CZU doctoral source {spec['id']} omitted expected token {token!r}"
                )
        content_type = next(
            (value for key, value in headers.items() if key.casefold() == "content-type"),
            "application/pdf" if spec["kind"] in {"pdf", "reviewed_scan"} else "text/html",
        )
        assets[spec["id"]] = {
            "url": spec["url"],
            "httpStatus": status,
            "contentType": content_type,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "sourceLanguage": spec["sourceLanguage"],
            "extractionMethod": (
                "human_reviewed_scan_transcription_sha256_guarded"
                if spec["kind"] == "reviewed_scan"
                else "pypdf_text_layer"
                if spec["kind"] == "pdf"
                else "static_html_visible_text"
            ),
            "reviewedAt": spec.get("reviewedAt"),
            "text": text,
        }
    return build_catalog(inventory_payload, assets, now=current)


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECONDS)
    args = parser.parse_args()
    payload = harvest_catalog(delay_seconds=args.delay)
    atomic_write(args.output, payload)
    print(json.dumps({"output": str(args.output), "counts": payload["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

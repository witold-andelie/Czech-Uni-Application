"""Harvest CZU's official English bachelor/master catalogue and live windows.

The WordPress REST collection supplies the complete, paginated catalogue and
stable post IDs.  Each official detail page supplies the application dates,
duration, tuition and faculty evidence that the REST representation omits.
The result is candidate data only; it is never a substitute for zh-CN/en/cs
review or for the separate Czech-taught programme inventory.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sources" / "admissions" / "czu-english-programmes.json"
BASE_URL = "https://study.czu.cz"
CATALOGUE_URL = f"{BASE_URL}/"
PROGRAMMES_API = (
    f"{BASE_URL}/wp-json/wp/v2/programmes"
    "?per_page=100&_embed=wp%3Aterm"
)
OPEN_PROGRAMMES_URL = f"{BASE_URL}/open-programmes/"
ADMISSIONS_URL = f"{BASE_URL}/admission/"
GENERAL_APPLY_URL = "https://is.czu.cz/prihlaska/?lang=en"
REQUEST_DELAY_SECONDS = 2.0
UA = "CzechUniApplyHarvest/0.3 (offline ingestion; official-source verification)"

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
HEADING_RE = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.I | re.S)


class HarvestIncomplete(RuntimeError):
    """Raised when CZU's official catalogue cannot be proven complete."""


FetchPage = Callable[[str], tuple[int, dict[str, str], str]]


def visible_text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", fragment)
    return WS_RE.sub(" ", unescape(TAG_RE.sub(" ", fragment))).strip()


def _normalize(value: str) -> str:
    return WS_RE.sub(" ", value.casefold().replace("\xa0", " ")).strip()


def _attribute(fragment: str, name: str) -> str | None:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*([\"'])(.*?)\1", fragment, re.I | re.S)
    return unescape(match.group(2)).strip() if match else None


def request(url: str, timeout: int = 75) -> tuple[int, dict[str, str], str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json,text/html;q=0.9"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            headers = {key.casefold(): value for key, value in response.headers.items()}
            return response.status, headers, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace") if error.fp else ""
        headers = {key.casefold(): value for key, value in error.headers.items()}
        return error.code, headers, body
    except Exception:
        return 0, {}, ""


def _embedded_terms(row: dict, taxonomy: str) -> list[dict]:
    groups = (row.get("_embedded") or {}).get("wp:term") or []
    return [
        term
        for group in groups
        if isinstance(group, list)
        for term in group
        if isinstance(term, dict) and term.get("taxonomy") == taxonomy
    ]


def parse_programme_api(body: str, headers: dict[str, str]) -> list[dict]:
    try:
        rows = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HarvestIncomplete("CZU programme API returned invalid JSON") from exc
    if not isinstance(rows, list):
        raise HarvestIncomplete("CZU programme API did not return a list")
    try:
        reported_total = int(headers["x-wp-total"])
        reported_pages = int(headers["x-wp-totalpages"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HarvestIncomplete("CZU programme API omitted pagination totals") from exc
    if reported_pages != 1 or reported_total != len(rows):
        raise HarvestIncomplete(
            f"CZU programme pagination mismatch: total={reported_total}, "
            f"pages={reported_pages}, received={len(rows)}"
        )
    if not rows:
        raise HarvestIncomplete("CZU programme API returned an empty catalogue")

    parsed: list[dict] = []
    seen_ids: set[int] = set()
    seen_urls: set[str] = set()
    degree_map = {"bachelor": "b", "master": "m"}
    for row in rows:
        post_id = row.get("id")
        link = row.get("link")
        title = visible_text(str((row.get("title") or {}).get("rendered") or ""))
        if not isinstance(post_id, int) or post_id in seen_ids:
            raise HarvestIncomplete(f"CZU programme has an invalid or duplicate post ID: {post_id!r}")
        if not isinstance(link, str) or not link.startswith(f"{BASE_URL}/programmes/") or link in seen_urls:
            raise HarvestIncomplete(f"CZU programme {post_id} has an invalid or duplicate detail URL")
        if row.get("type") != "programmes" or row.get("status") != "publish" or not title:
            raise HarvestIncomplete(f"CZU programme {post_id} is not a complete published record")
        degrees = _embedded_terms(row, "degree")
        faculties = _embedded_terms(row, "faculty")
        fields = _embedded_terms(row, "programme-fields")
        if len(degrees) != 1 or degrees[0].get("slug") not in degree_map:
            raise HarvestIncomplete(f"CZU programme {post_id} has no supported single degree")
        if len(faculties) != 1 or not faculties[0].get("name"):
            raise HarvestIncomplete(f"CZU programme {post_id} has no single faculty")
        if not fields:
            raise HarvestIncomplete(f"CZU programme {post_id} has no subject field")
        seen_ids.add(post_id)
        seen_urls.add(link)
        parsed.append(
            {
                "id": f"czu-study-{post_id}",
                "sourceStableId": str(post_id),
                "institutionId": "msmt-vs_41000",
                "titles": {"en": title},
                "sourceLanguage": "en",
                "studyLanguage": "en",
                "degree": degree_map[degrees[0]["slug"]],
                "faculty": {
                    "sourceId": str(faculties[0].get("id")),
                    "slug": faculties[0].get("slug"),
                    "nameOriginal": visible_text(str(faculties[0]["name"])),
                },
                "fieldsOriginal": [visible_text(str(item.get("name") or "")) for item in fields],
                "officialProgrammeUrl": link,
                "sourceModifiedAt": row.get("modified_gmt"),
            }
        )
    return sorted(parsed, key=lambda item: int(item["sourceStableId"]))


def _sections(document: str) -> dict[str, str]:
    headings = list(HEADING_RE.finditer(document))
    result: dict[str, str] = {}
    for index, heading in enumerate(headings):
        label = _normalize(visible_text(heading.group(1)))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(document)
        value = visible_text(document[heading.end() : end])
        if label and value:
            result.setdefault(label, value)
    return result


def _date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().rstrip(".")
    for pattern in ("%d %B, %Y", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    match = re.search(r"\b(\d{1,2})\s+([A-Za-z]+),?\s+(20\d{2})\b", value)
    if match:
        try:
            return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()
        except ValueError:
            return None
    return None


def _duration(value: str | None) -> float | None:
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return float(match.group(0).replace(",", ".")) if match else None


def _tuition(value: str | None) -> dict | None:
    if not value:
        return None
    match = re.search(r"(?:(€|EUR|CZK|Kč)\s*)?([\d][\d\s,.]*)(?:\s*(€|EUR|CZK|Kč))?", value, re.I)
    if not match:
        return None
    token = (match.group(1) or match.group(3) or "").casefold()
    currency = "EUR" if token in {"€", "eur"} else "CZK" if token in {"czk", "kč"} else None
    if not currency:
        return None
    number = match.group(2).replace(" ", "").replace(",", "")
    try:
        amount = float(number)
    except ValueError:
        return None
    return {
        "amount": amount,
        "currency": currency,
        "period": "year" if "year" in value.casefold() else "unknown",
        "displayOriginal": value,
    }


def _application_status(start: str | None, end: str | None, now: datetime) -> str:
    if not start or not end:
        return "unknown"
    start_date = datetime.fromisoformat(start).date()
    end_date = datetime.fromisoformat(end).date()
    if end_date < start_date:
        raise HarvestIncomplete(f"CZU application window ends before it starts: {start}..{end}")
    today = now.astimezone(timezone.utc).date()
    if today < start_date:
        return "upcoming"
    if today > end_date:
        return "closed"
    return "open"


def parse_detail(document: str, expected: dict, now: datetime) -> dict:
    post_id = expected["sourceStableId"]
    if not re.search(rf"\bpostid-{re.escape(post_id)}\b", document):
        raise HarvestIncomplete(f"CZU detail page does not identify programme {post_id}")
    sections = _sections(document)
    start_original = sections.get("applications start")
    end_original = sections.get("applications end")
    start = _date(start_original)
    end = _date(end_original)
    if bool(start_original) != bool(start) or bool(end_original) != bool(end):
        raise HarvestIncomplete(f"CZU programme {post_id} has an unparseable application date")
    status = _application_status(start, end, now)

    apply_match = next(
        (
            match
            for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", document, re.I | re.S)
            if "apply now" in visible_text(match.group(2)).casefold()
        ),
        None,
    )
    apply_url = _attribute(apply_match.group(1), "href") if apply_match else None
    if apply_url:
        apply_url = urllib.parse.urljoin(BASE_URL, apply_url)
        if not apply_url.startswith("https://"):
            raise HarvestIncomplete(f"CZU programme {post_id} has an unsafe application URL")

    requirements_heading = next(
        (match for match in HEADING_RE.finditer(document) if _normalize(visible_text(match.group(1))) == "admission requirements"),
        None,
    )
    evidence_urls: list[str] = []
    requirements_hash = None
    if requirements_heading:
        next_heading = HEADING_RE.search(document, requirements_heading.end())
        block = document[requirements_heading.end() : next_heading.start() if next_heading else len(document)]
        requirements_text = visible_text(block)
        requirements_hash = hashlib.sha256(requirements_text.encode("utf-8")).hexdigest()
        for anchor in re.finditer(r"<a\b([^>]*)>", block, re.I | re.S):
            href = _attribute(anchor.group(1), "href")
            if href:
                url = urllib.parse.urljoin(expected["officialProgrammeUrl"], href)
                if url.startswith("https://") and url not in evidence_urls:
                    evidence_urls.append(url)

    return {
        **expected,
        "durationYears": _duration(sections.get("study duration")),
        "tuition": _tuition(sections.get("tuition fee")),
        "tuitionEu": _tuition(sections.get("tuition fee (eu students)")),
        "applicationWindows": [
            {
                "roundOriginal": "Application",
                "start": start,
                "end": end,
                "datePrecision": "day" if start and end else "unknown",
                "sourceTimezone": "Europe/Prague",
                "statusAtFetch": status,
                "startOriginal": start_original,
                "endOriginal": end_original,
                "sourceUrl": expected["officialProgrammeUrl"],
            }
        ] if start or end else [],
        "applicationStatus": status,
        "applyUrl": apply_url,
        "generalApplyPortalUrl": GENERAL_APPLY_URL,
        "admissionRequirementsTextSha256": requirements_hash,
        "admissionEvidenceUrls": evidence_urls,
        "sourceHtmlSha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
        "publicationStatus": "candidate_not_published",
    }


def parse_open_count(document: str) -> int:
    match = re.search(
        r"<span\b[^>]*class=[\"'][^\"']*\bquery-8\b[^\"']*[\"'][^>]*>\s*(\d+)\s*</span>",
        document,
        re.I | re.S,
    )
    if not match:
        raise HarvestIncomplete("CZU open-programmes page omitted its official result count")
    return int(match.group(1))


def parse_admissions_page(document: str) -> dict:
    if "Admissions" not in document or "CZU" not in document:
        raise HarvestIncomplete("CZU admissions page did not return its expected body")
    apply_urls = [
        urllib.parse.urljoin(ADMISSIONS_URL, unescape(value))
        for value in re.findall(r"href=[\"']([^\"']+)[\"']", document, re.I)
        if "is.czu.cz/prihlaska" in value or "prihlaska.czu.cz" in value
    ]
    fee_match = re.search(r"admission fee\D{0,40}(?:CZK|Kč)\s*([\d\s]+)", visible_text(document), re.I)
    if not apply_urls or not fee_match:
        raise HarvestIncomplete("CZU admissions page omitted its apply link or application fee")
    return {
        "generalApplyPortalUrl": apply_urls[0],
        "applicationFee": {
            "amount": float(fee_match.group(1).replace(" ", "")),
            "currency": "CZK",
            "displayOriginal": fee_match.group(0),
        },
    }


def _write_raw(raw_dir: Path | None, relative: str, body: str) -> None:
    if raw_dir is None:
        return
    target = raw_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def harvest_catalog(
    fetch_page: FetchPage = request,
    *,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    raw_dir: Path | None = None,
) -> dict:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    generated_at = current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if raw_dir is None and fetch_page is request:
        raw_dir = ROOT / "work" / "raw" / current.date().isoformat() / "czu-study"

    attempts: list[dict] = []

    def fetch(url: str, raw_name: str) -> tuple[dict[str, str], str]:
        status, headers, body = fetch_page(url)
        attempts.append({"url": url, "httpStatus": status, "bytes": len(body.encode("utf-8"))})
        _write_raw(raw_dir, raw_name, body)
        if status != 200 or not body:
            raise HarvestIncomplete(f"CZU source fetch failed: status={status} url={url}")
        return headers, body

    api_headers, api_body = fetch(PROGRAMMES_API, "programmes-api.json")
    catalogue = parse_programme_api(api_body, api_headers)
    if delay_seconds:
        sleep(delay_seconds)
    _, open_body = fetch(OPEN_PROGRAMMES_URL, "open-programmes.html")
    open_page_count = parse_open_count(open_body)
    if delay_seconds:
        sleep(delay_seconds)
    _, admissions_body = fetch(ADMISSIONS_URL, "admissions.html")
    admissions = parse_admissions_page(admissions_body)

    programmes: list[dict] = []
    for index, item in enumerate(catalogue):
        if delay_seconds:
            sleep(delay_seconds)
        _, detail_body = fetch(
            item["officialProgrammeUrl"],
            f"programmes/{item['sourceStableId']}-{item['officialProgrammeUrl'].rstrip('/').split('/')[-1]}.html",
        )
        parsed = parse_detail(detail_body, item, current)
        parsed["generalApplyPortalUrl"] = admissions["generalApplyPortalUrl"]
        programmes.append(parsed)

    statuses = Counter(item["applicationStatus"] for item in programmes)
    degree_counts = Counter(item["degree"] for item in programmes)
    faculty_counts = Counter(item["faculty"]["slug"] for item in programmes)
    detail_open_count = statuses["open"]
    counts = {
        "programmes": len(programmes),
        "degrees": {"bachelor": degree_counts["b"], "master": degree_counts["m"]},
        "faculties": dict(sorted(faculty_counts.items())),
        "detailsWithCompleteWindow": sum(
            bool(item["applicationWindows"] and item["applicationWindows"][0]["start"] and item["applicationWindows"][0]["end"])
            for item in programmes
        ),
        "openByDetailDates": detail_open_count,
        "upcomingByDetailDates": statuses["upcoming"],
        "closedByDetailDates": statuses["closed"],
        "unknownByDetailDates": statuses["unknown"],
        "openPageReported": open_page_count,
    }
    payload = {
        "generatedAt": generated_at,
        "dataClass": "official_university_admissions_extract",
        "catalogKind": "candidate_not_published",
        "institutionId": "msmt-vs_41000",
        "institutionNameOriginal": "Czech University of Life Sciences Prague",
        "sourceLanguage": "en",
        "scope": {
            "teachingLanguages": ["en"],
            "degrees": ["b", "m"],
            "claim": "official_czu_english_bachelor_master_catalogue_on_source",
            "excludes": ["czech-taught programmes", "doctoral programmes"],
        },
        "sourceUrls": {
            "catalogue": CATALOGUE_URL,
            "api": PROGRAMMES_API,
            "openProgrammes": OPEN_PROGRAMMES_URL,
            "admissions": ADMISSIONS_URL,
            "generalApplyPortal": admissions["generalApplyPortalUrl"],
        },
        "applicationFee": admissions["applicationFee"],
        "counts": counts,
        "coverage": {
            "apiReportedTotal": int(api_headers["x-wp-total"]),
            "apiReportedPages": int(api_headers["x-wp-totalpages"]),
            "receivedUniqueProgrammeIds": len({item["sourceStableId"] for item in programmes}),
            "detailPagesExpected": len(catalogue),
            "detailPagesParsed": len(programmes),
            "complete": len(programmes) == int(api_headers["x-wp-total"]),
            "availabilityCrosscheck": "agrees" if detail_open_count == open_page_count else "disagrees",
            "claimBoundary": (
                "Completeness applies only to the English bachelor/master catalogue exposed by "
                "study.czu.cz. It does not claim all CZU programmes or automatic formal publication."
            ),
        },
        "attempts": attempts,
        "programmes": programmes,
    }
    if raw_dir is not None:
        _write_raw(raw_dir, "harvest-summary.json", json.dumps({"generatedAt": generated_at, "counts": counts, "coverage": payload["coverage"], "attempts": attempts}, ensure_ascii=False, indent=2) + "\n")
    return payload


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    payload = harvest_catalog()
    atomic_write(OUT, payload)
    print(json.dumps({"output": str(OUT), "generatedAt": payload["generatedAt"], "counts": payload["counts"], "coverage": payload["coverage"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

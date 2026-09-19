"""Offline coverage gap report, plus optional live classification of career pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from harvest_nine_hei_jobs import load_registered_job_sources

ROOT = Path(__file__).resolve().parents[4]
HEI_BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
JOB_CHECKS = ROOT / "data" / "sources" / "job-source-checks.json"

CAREER_PATHS = (
    "/kariera",
    "/kariera/",
    "/jobs",
    "/jobs/",
    "/careers",
    "/careers/",
    "/volna-mista",
    "/volna-mista/",
    "/vyberova-rizeni",
    "/uredni-deska",
)


def classify_listing_html(url: str, html: str) -> str | None:
    blob = f"{url}\n{html}".lower()
    if "jm-ajax/get_listings" in blob or "wp-json/wp/v2/job-listings" in blob:
        return "czu_wp_job_manager"
    if "vyberova-rizeni/ajax.php" in blob or "pracid=" in blob:
        return "cuni_ajax"
    if "/en/about-us/careers/vacancies/" in blob or "/kariera/volna-mista/" in blob:
        return "muni_vacancies"
    if "api.capybara.lmc.cz" in blob or "jobs.cz" in blob:
        return "lmc_graphql"
    if "recruitis" in blob:
        return "recruitis_widget"
    if "job-listing" in blob or "volné místo" in blob or "výběrové řízení" in blob:
        return "generic_listing_links"
    return None


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def covered_employer_ids(registry: list[dict] | None = None) -> set[str]:
    sources = registry if registry is not None else load_registered_job_sources()
    return {str(item.get("employerId")) for item in sources if item.get("employerId")}


def build_probe_report(
    *,
    fetch_page=None,
    registry: list[dict] | None = None,
    institutions: list[dict] | None = None,
    checks: list[dict] | None = None,
) -> dict[str, Any]:
    if institutions is None:
        baseline = _load_json(HEI_BASELINE) or {}
        institutions = list(baseline.get("institutions") or [])
    if checks is None:
        payload = _load_json(JOB_CHECKS) or {}
        checks = list(payload.get("rows") or [])
    check_by_id = {str(row.get("institutionId")): row for row in checks if isinstance(row, dict)}
    covered = covered_employer_ids(registry)
    gaps = []
    live_hits = []
    for institution in institutions:
        ident = str(institution.get("id") or "")
        if not ident or ident in covered:
            continue
        official_url = str(institution.get("officialUrl") or "")
        check = check_by_id.get(ident) or {}
        row = {
            "institutionId": ident,
            "officialName": institution.get("officialName"),
            "officialUrl": official_url,
            "checkResult": check.get("result"),
            "checkEvidenceUrls": check.get("evidenceUrls") or [],
            "suggestedParser": None,
            "probedUrls": [],
        }
        if fetch_page is not None and official_url:
            origin = f"{urlsplit(official_url).scheme}://{urlsplit(official_url).netloc}"
            candidates = [official_url, *[urljoin(origin, path) for path in CAREER_PATHS]]
            seen: set[str] = set()
            for url in candidates:
                if url in seen:
                    continue
                seen.add(url)
                status, body = fetch_page(url)
                row["probedUrls"].append({"url": url, "status": status})
                if status == 200 and body:
                    parser = classify_listing_html(url, body)
                    if parser:
                        row["suggestedParser"] = parser
                        row["suggestedListingUrl"] = url
                        live_hits.append(row)
                        break
        gaps.append(row)
    return {
        "catalogKind": "coverage_probe_not_published",
        "institutionCount": len(institutions),
        "coveredEmployerCount": len(covered),
        "gapCount": len(gaps),
        "liveHits": len(live_hits),
        "gaps": gaps,
    }

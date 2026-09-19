from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from engine.probe_job_sources import build_probe_report, classify_listing_html  # noqa: E402


def test_probe_offline_lists_heis_without_job_sources() -> None:
    report = build_probe_report(
        institutions=[
            {"id": "msmt-vs_14000", "officialName": "Masaryk", "officialUrl": "https://www.muni.cz"},
            {"id": "msmt-vs_61000", "officialName": "Ambis", "officialUrl": "https://www.ambis.cz"},
        ],
        registry=[{"id": "muni-careers", "employerId": "msmt-vs_14000", "parser": "muni_vacancies", "url": "https://www.muni.cz/en/about-us/careers", "sourceType": "official_job_listing"}],
        checks=[{"institutionId": "msmt-vs_61000", "result": "official_site_checked_no_central_listing", "evidenceUrls": ["https://www.ambis.cz"]}],
    )
    assert report["institutionCount"] == 2
    assert report["coveredEmployerCount"] == 1
    assert report["gapCount"] == 1
    assert report["gaps"][0]["institutionId"] == "msmt-vs_61000"
    assert report["liveHits"] == 0


def test_classifier_detects_known_platforms() -> None:
    assert classify_listing_html("https://jobs.czu.cz/", "jm-ajax/get_listings") == "czu_wp_job_manager"
    assert (
        classify_listing_html(
            "https://www.muni.cz/en/about-us/careers",
            '<a href="/en/about-us/careers/vacancies/81700">Role</a>',
        )
        == "muni_vacancies"
    )


def test_live_probe_does_not_run_unless_fetch_injected() -> None:
    called = []

    def fetch(url: str):
        called.append(url)
        return 200, '<a href="/en/about-us/careers/vacancies/1">Researcher</a>'

    report = build_probe_report(
        fetch_page=fetch,
        institutions=[{"id": "msmt-vs_99999", "officialName": "Test", "officialUrl": "https://jobs.test"}],
        registry=[],
        checks=[],
    )
    assert called
    assert report["liveHits"] == 1
    assert report["gaps"][0]["suggestedParser"] == "muni_vacancies"

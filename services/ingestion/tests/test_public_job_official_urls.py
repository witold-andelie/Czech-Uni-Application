from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from engine.urls import official_detail_allowed  # noqa: E402

SNAPSHOT = ROOT / "data" / "published" / "snapshots" / "v2026-09-19.1" / "browse" / "nine-hei-jobs.json"


def test_published_jobs_are_not_generic_listings() -> None:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert len(snapshot["jobs"]) == 15
    for job in snapshot["jobs"]:
        url = job.get("officialDetailUrl") or job.get("sourceUrl")
        source = {"url": job.get("listingUrl") or "", "singleVacancyDocument": False}
        ok, reason = official_detail_allowed(url, source)
        assert ok, (job["id"], reason, url)


def test_cuni_board_without_pracid_is_generic() -> None:
    ok, reason = official_detail_allowed(
        "https://cuni.cz/UKEN-1573.html",
        {"url": "https://cuni.cz/UKEN-1573.html"},
    )
    assert ok is False
    assert reason == "official-detail-url-is-generic-listing"
    ok, reason = official_detail_allowed(
        "https://cuni.cz/UKEN-1573.html?pracid=202609-AP2-MFF-KTIML-074",
        {"url": "https://cuni.cz/UKEN-1573.html"},
    )
    assert ok is True


def test_muni_and_czu_listing_roots_are_generic() -> None:
    ok, reason = official_detail_allowed(
        "https://www.muni.cz/en/about-us/careers/vacancies",
        {"url": "https://www.muni.cz/en/about-us/careers"},
    )
    assert ok is False
    assert reason == "official-detail-url-is-generic-listing"
    ok, _ = official_detail_allowed(
        "https://www.muni.cz/en/about-us/careers/vacancies/81700",
        {"url": "https://www.muni.cz/en/about-us/careers"},
    )
    assert ok is True
    ok, reason = official_detail_allowed("https://jobs.czu.cz/", {"url": "https://jobs.czu.cz/"})
    assert ok is False
    assert reason == "official-detail-url-is-generic-listing"
    ok, _ = official_detail_allowed(
        "https://jobs.czu.cz/job/tf_asistent-znalostniho-transferu-t1/",
        {"url": "https://jobs.czu.cz/"},
    )
    assert ok is True

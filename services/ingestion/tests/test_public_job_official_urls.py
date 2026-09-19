from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from engine.urls import official_detail_allowed  # noqa: E402

AUDIT = ROOT / "data" / "sources" / "coverage" / "public-job-official-urls.json"
SNAPSHOT = ROOT / "data" / "published" / "snapshots" / "v2026-09-19.1" / "browse" / "nine-hei-jobs.json"


def test_published_jobs_are_not_generic_listings() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    published_ids = {job["id"] for job in snapshot["jobs"]}
    audited_ids = {row["id"] for row in audit["jobs"]}
    assert published_ids == audited_ids
    assert audit["counts"]["genericListings"] == 0
    assert audit["counts"]["publishedJobs"] == 15
    by_id = {row["id"]: row for row in audit["jobs"]}
    for job in snapshot["jobs"]:
        url = job.get("officialDetailUrl") or job.get("sourceUrl")
        source = {"url": job.get("listingUrl") or "", "singleVacancyDocument": False}
        ok, reason = official_detail_allowed(url, source)
        row = by_id[job["id"]]
        assert ok, (job["id"], reason, url)
        assert row["officialUrl"] == url
        if job["id"] == "job-41000-1598":
            assert row["verdict"] == "official_gone"
            assert row["httpStatus"] == 404
        else:
            assert row["verdict"] == "vacancy_document"
            assert row["httpStatus"] == 200


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

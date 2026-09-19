from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

DETAIL = "https://www.d3s.mff.cuni.cz/positions/2026-1/"
LISTING = "https://www.d3s.mff.cuni.cz/positions/"


def test_operational_d3s_job_points_at_vacancy_document_and_is_not_approved() -> None:
    payload = json.loads((ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json").read_text(encoding="utf-8"))
    job = next(item for item in payload["jobs"] if item["id"] == "job-cuni-d3s-postdoc")
    evidence = next(item for item in payload["evidence"] if item["id"] == "ev-job-cuni-d3s-postdoc")
    window = next(item for item in payload["windows"] if item["id"] == "win-job-cuni-d3s-postdoc")
    assert job["officialDetailUrl"] == DETAIL
    assert job["sourceUrl"] == DETAIL
    assert job["listingUrl"] == LISTING
    assert job["applicationUrl"] == DETAIL
    assert job["publicationStatus"] == "review_pending"
    assert job["translationStatus"] == "unreviewed"
    assert job["visibility"] == "review_pending"
    assert evidence["url"] == DETAIL
    assert window["applicationUrl"] == DETAIL
    reviews = json.loads((ROOT / "data" / "sources" / "reviews" / "job-translations.json").read_text(encoding="utf-8"))
    locales = reviews["reviews"]["job-cuni-d3s-postdoc"]["locales"]
    assert locales["zh-CN"]["status"] == "revoked"
    assert locales["en"]["status"] == "revoked"
    assert locales["cs"]["status"] == "revoked"


def test_frozen_snapshot_keeps_listing_url_until_rereview() -> None:
    payload = json.loads(
        (ROOT / "data" / "published" / "snapshots" / "v2026-09-17.1" / "browse" / "nine-hei-jobs.json").read_text(
            encoding="utf-8"
        )
    )
    job = next(item for item in payload["jobs"] if item["id"] == "job-cuni-d3s-postdoc")
    assert job["sourceUrl"] == LISTING
    assert job.get("officialDetailUrl") in (None, "", LISTING)

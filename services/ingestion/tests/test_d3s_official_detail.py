from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from harvest_nine_hei_jobs import apply_translation_review, load_job_reviews  # noqa: E402
from publication_rules import job_fact_hash  # noqa: E402

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
    assert job["publicationStatus"] == "approved"
    assert job["translationStatus"] == "verified"
    assert job["visibility"] == "public"
    assert evidence["url"] == DETAIL
    assert window["applicationUrl"] == DETAIL
    reviews = json.loads((ROOT / "data" / "sources" / "reviews" / "job-translations.json").read_text(encoding="utf-8"))
    entry = reviews["reviews"]["job-cuni-d3s-postdoc"]
    assert entry["sourceHash"] == job["sourceHash"]
    assert entry["factHash"] == job["translationReview"]["factHash"]
    locales = entry["locales"]
    assert locales["zh-CN"]["status"] == "reviewed"
    assert locales["en"]["status"] == "reviewed"
    assert locales["cs"]["status"] == "reviewed"
    assert entry["factHash"] == job_fact_hash(job, [window])
    applied = apply_translation_review(dict(job), job["sourceHash"], load_job_reviews(), [window])
    assert applied["publicationStatus"] == "approved"
    assert applied["translationStatus"] == "verified"


def test_frozen_snapshot_keeps_listing_url_until_rereview() -> None:
    payload = json.loads(
        (ROOT / "data" / "published" / "snapshots" / "v2026-09-17.1" / "browse" / "nine-hei-jobs.json").read_text(
            encoding="utf-8"
        )
    )
    job = next(item for item in payload["jobs"] if item["id"] == "job-cuni-d3s-postdoc")
    assert job["sourceUrl"] == LISTING
    assert job.get("officialDetailUrl") in (None, "", LISTING)

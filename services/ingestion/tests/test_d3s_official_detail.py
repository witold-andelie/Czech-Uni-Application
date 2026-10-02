from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from harvest_nine_hei_jobs import apply_translation_review  # noqa: E402
from publication_rules import job_fact_hash  # noqa: E402

DETAIL = "https://www.d3s.mff.cuni.cz/positions/2026-1/"
# Live records change daily; these tests pin a frozen copy and an immutable snapshot.
FROZEN = json.loads((Path(__file__).parent / "fixtures" / "frozen_live_records.json").read_text(encoding="utf-8"))
PINNED_SNAPSHOT = ROOT / "data" / "published" / "snapshots" / "v2026-09-29.2"
LISTING = "https://www.d3s.mff.cuni.cz/positions/"


def test_operational_d3s_job_points_at_vacancy_document_and_is_not_approved() -> None:
    payload = FROZEN
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
    entry = FROZEN["reviews"]["job-cuni-d3s-postdoc"]
    assert entry["sourceHash"] == job["sourceHash"]
    assert entry["factHash"] == job["translationReview"]["factHash"]
    locales = entry["locales"]
    assert locales["zh-CN"]["status"] == "reviewed"
    assert locales["en"]["status"] == "reviewed"
    assert locales["cs"]["status"] == "reviewed"
    assert entry["factHash"] == job_fact_hash(job, [window], entry["normalizationVersion"])
    applied = apply_translation_review(dict(job), job["sourceHash"], FROZEN["reviews"], [window])
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


def test_active_snapshot_uses_d3s_vacancy_document() -> None:
    payload = json.loads((PINNED_SNAPSHOT / "browse" / "nine-hei-jobs.json").read_text(encoding="utf-8"))
    job = next(item for item in payload["jobs"] if item["id"] == "job-cuni-d3s-postdoc")
    assert job["officialDetailUrl"] == DETAIL
    assert job["sourceUrl"] == DETAIL
    assert job["listingUrl"] == LISTING

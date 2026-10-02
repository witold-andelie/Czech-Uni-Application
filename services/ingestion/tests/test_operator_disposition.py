from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from harvest_nine_hei_jobs import (  # noqa: E402
    apply_translation_review,
    operator_disposition,
    reconcile_stored_reviews,
)

# A frozen copy of the two VŠB records and their reviews: the live files change daily.
FROZEN_PATH = Path(__file__).parent / "fixtures" / "frozen_live_records.json"
CANDIDATES = FROZEN_PATH
REVIEWS = FROZEN_PATH
KEEP = "job-27000-56"
DROP = "job-27000-70"
REASON = f"duplicate_record_of_{KEEP}"


def load_case() -> tuple[dict, list[dict], dict]:
    payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    job = next(item for item in payload["jobs"] if item["id"] == DROP)
    window = next(
        (item for item in payload["windows"] if item.get("ownerId") == DROP),
        None,
    )
    reviews = json.loads(REVIEWS.read_text(encoding="utf-8"))
    return job, ([window] if window else []), reviews["reviews"][DROP]


def frozen_reviews() -> dict:
    return json.loads(REVIEWS.read_text(encoding="utf-8"))["reviews"]


def test_reviewed_record_is_approved_without_a_disposition() -> None:
    from publication_rules import job_fact_hash

    job, windows, entry = load_case()
    entry = {key: value for key, value in entry.items() if key != "disposition"}
    # The duplicate's own facts move with the live advert; what is under test
    # is that only the disposition withholds a review that matches them.
    entry["factHash"] = job_fact_hash(job, windows, entry["normalizationVersion"])
    applied = apply_translation_review(dict(job), job["sourceHash"], {DROP: entry}, windows)
    assert applied["publicationStatus"] == "approved"
    assert applied["translationStatus"] == "verified"
    assert "reviewDisposition" not in applied


def test_recorded_duplicate_disposition_survives_reconciliation() -> None:
    """The same advert must not reach the public snapshot twice."""
    job, windows, entry = load_case()
    disposition = entry.get("disposition")
    assert isinstance(disposition, dict), "the VŠB duplicate decision is recorded in the review file"
    assert disposition["publicationStatus"] == "rejected"
    assert disposition["visibility"] == "archived"
    assert disposition["reason"] == REASON
    assert disposition["decidedBy"] and disposition["decidedAt"]

    payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    jobs = [item for item in payload["jobs"] if item["id"] in {KEEP, DROP}]
    payload["jobs"] = jobs
    payload["windows"] = [item for item in payload.get("windows") or [] if item.get("ownerId") in {KEEP, DROP}]
    reconciled = reconcile_stored_reviews(payload, reviews=frozen_reviews())
    applied = next(item for item in reconciled["jobs"] if item["id"] == DROP)
    assert applied["publicationStatus"] == "rejected"
    assert applied["visibility"] == "archived"
    assert applied["lastAttemptReason"] == REASON
    assert applied["reviewDisposition"] == operator_disposition(entry)
    # The other record of the same advert is left to be published on its own review.
    kept = next(item for item in payload["jobs"] if item["id"] == KEEP)
    assert kept.get("lastAttemptReason") != REASON
    assert "reviewDisposition" not in kept


def test_disposition_cannot_widen_what_is_published() -> None:
    job, windows, entry = load_case()
    with pytest.raises(ValueError, match="publicationStatus"):
        operator_disposition({**entry, "disposition": {"publicationStatus": "approved", "visibility": "public",
                                                       "reason": REASON, "decidedBy": "operator",
                                                       "decidedAt": "2026-09-26T00:00:00Z"}})
    with pytest.raises(ValueError, match="visibility"):
        operator_disposition({**entry, "disposition": {"publicationStatus": "rejected", "visibility": "public",
                                                       "reason": REASON, "decidedBy": "operator",
                                                       "decidedAt": "2026-09-26T00:00:00Z"}})
    with pytest.raises(ValueError, match="reason"):
        operator_disposition({**entry, "disposition": {"publicationStatus": "rejected", "visibility": "archived",
                                                       "reason": "not a slug", "decidedBy": "operator",
                                                       "decidedAt": "2026-09-26T00:00:00Z"}})
    with pytest.raises(ValueError, match="decidedAt"):
        operator_disposition({**entry, "disposition": {"publicationStatus": "rejected", "visibility": "archived",
                                                       "reason": REASON, "decidedBy": "operator",
                                                       "decidedAt": ""}})
    assert operator_disposition({}) is None


def test_both_records_of_the_vsb_advert_describe_one_advert() -> None:
    payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    jobs = {item["id"]: item for item in payload["jobs"]}
    kept, dropped = jobs[KEEP], jobs[DROP]
    assert kept["sourceItemId"] == dropped["sourceItemId"]
    assert kept["sourceUrl"] == dropped["sourceUrl"]
    assert (
        kept["title"]["cs"].replace(" ", "").casefold()
        == dropped["title"]["cs"].replace(" ", "").casefold()
    )

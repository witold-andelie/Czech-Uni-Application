"""Publication withholds the records it cannot state, instead of failing all of them.

The public research library publishes two kinds of claim about a position: that it
is a paid opportunity and that its official page still announces it.  A record
whose evidence supports neither claim used to fail the whole snapshot, which
withheld every other position for a reason that belonged to one record alone.
Selection now withholds those records by id and reason - docs/PRODUCT.md calls
them the review background - while validation still refuses to publish one.

These tests run the real selection over the real candidate file, because the
distinction they protect is between records that are withheld and records that
are published, not between fixtures.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import publish  # noqa: E402
from live_evidence import CONFIRMED_STATUSES, load_evidence, parse_ts  # noqa: E402

SOURCES = ROOT / "data" / "sources"
CANDIDATES = SOURCES / "browse" / "nine-hei-jobs.json"
LIVE_EVIDENCE = SOURCES / "coverage" / "live-title-verification.json"


def staged_selection(tmp_path: Path) -> tuple[list[dict], dict]:
    """Run the publication selection over the real candidate file."""
    staging = tmp_path / "candidate" / "browse"
    staging.mkdir(parents=True)
    shutil.copy(CANDIDATES, staging / "nine-hei-jobs.json")
    publish._select_approved_jobs(tmp_path / "candidate", LIVE_EVIDENCE)
    payload = json.loads((staging / "nine-hei-jobs.json").read_text(encoding="utf-8"))
    return payload["jobs"], payload["publicationSelection"]


def candidate_records() -> dict[str, dict]:
    payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    return {job["id"]: job for job in payload["jobs"]}


def test_published_records_still_carry_confirmed_compensation(tmp_path: Path) -> None:
    """Withholding must not become a quieter way to publish an unconfirmed record."""
    jobs, selection = staged_selection(tmp_path)
    assert jobs, "the selection published nothing"
    assert all(job["paidStatus"] == "confirmed" for job in jobs)
    assert all(job["publicationStatus"] == "approved" for job in jobs)
    assert all(job["translationStatus"] == "verified" for job in jobs)
    assert selection["approved"] == len(jobs)
    assert selection["withheldCount"] == len(selection["withheld"])


def test_every_withheld_record_says_why_and_is_not_published(tmp_path: Path) -> None:
    jobs, selection = staged_selection(tmp_path)
    published_ids = {job["id"] for job in jobs}
    assert selection["withheld"], "the current candidate set has nothing to withhold"
    for item in selection["withheld"]:
        assert item["id"] not in published_ids
        assert item["reasons"] or item.get("liveEvidence"), item
        for reason in item["reasons"]:
            assert item["id"] in reason
    assert set(selection["withheldIds"]) == {item["id"] for item in selection["withheld"]}


def test_compensation_unconfirmed_records_are_withheld_by_name(tmp_path: Path) -> None:
    _jobs, selection = staged_selection(tmp_path)
    unconfirmed = {
        ident for ident, record in candidate_records().items()
        if record.get("publicationStatus") == "approved" and record.get("paidStatus") != "confirmed"
    }
    withheld = {item["id"]: item for item in selection["withheld"]}
    assert unconfirmed, "the candidate set should still carry unconfirmed-pay leads"
    assert unconfirmed <= set(withheld)
    for ident in unconfirmed:
        assert any("lacks confirmed compensation evidence" in reason for reason in withheld[ident]["reasons"])


def test_records_whose_source_no_longer_verifies_them_are_withheld_not_closed(tmp_path: Path) -> None:
    """Some official pages no longer answer with the record's own announcement.

    docs/CRAWLING_RULES.md: an unavailable official source holds publication of
    the record.  AGENTS.md: a 404 is not evidence that a vacancy ended.  The
    records therefore keep their own lifecycleStatus and are withheld from the
    snapshot with the live-evidence reason recorded - they are neither marked
    closed nor silently dropped.
    """
    jobs, selection = staged_selection(tmp_path)
    withheld = {item["id"]: item for item in selection["withheld"]}
    records = candidate_records()
    unverified = {
        ident for ident, item in withheld.items() if item.get("liveEvidence")
    }
    assert unverified, "the live source changes should be visible in the selection"
    for ident in unverified:
        record = records[ident]
        assert record.get("lifecycleStatus") not in {"closed", "expired"}, (
            f"{ident} must not be closed on the strength of an HTTP status alone"
        )
        assert record.get("publicationStatus") == "approved"
        assert withheld[ident]["liveEvidence"].startswith("no live verification within ")
    assert unverified & {job["id"] for job in jobs} == set()


def test_live_evidence_gate_passes_for_the_staged_selection(tmp_path: Path) -> None:
    """Every published record either has fresh live proof or a closed window.

    The gate itself is the shared rule (services/ingestion/src/live_evidence.py);
    what this test protects is that withholding did not quietly widen it.  The
    window exemption is the gate's own: a record whose announced deadline has
    already passed is expected to be archived rather than to re-prove a live
    announcement.
    """
    staging = tmp_path / "candidate" / "browse"
    staging.mkdir(parents=True)
    shutil.copy(CANDIDATES, staging / "nine-hei-jobs.json")
    publish._select_approved_jobs(tmp_path / "candidate", LIVE_EVIDENCE)
    staged_jobs = staging / "nine-hei-jobs.json"
    payload = json.loads(staged_jobs.read_text(encoding="utf-8"))

    assert publish.live_evidence_errors(staged_jobs, LIVE_EVIDENCE, publish.LIVE_EVIDENCE_MAX_AGE_DAYS) == []

    evidence = load_evidence(LIVE_EVIDENCE)
    fresh: set[str] = set()
    for row in evidence.get("rows") or []:
        if str(row.get("status")) not in set(CONFIRMED_STATUSES):
            continue
        checked = row.get("checkedAt") or row.get("verifiedAt")
        if not isinstance(checked, str):
            continue
        try:
            moment = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        except ValueError:
            continue
        if datetime.now(timezone.utc) - moment <= timedelta(days=publish.LIVE_EVIDENCE_MAX_AGE_DAYS):
            fresh.add(str(row.get("candidateId")))

    closed_windows: set[str] = set()
    for window in payload.get("windows") or []:
        moment = parse_ts(window.get("closesAt"))
        if moment is not None and moment < datetime.now(timezone.utc):
            closed_windows.add(str(window.get("ownerId")))

    for job in payload["jobs"]:
        assert job["id"] in fresh or job["id"] in closed_windows, (
            f"{job['id']} is published without fresh live verification and without a "
            "closed announced window"
        )


def test_an_unconfirmed_record_cannot_smuggle_into_the_selection(tmp_path: Path) -> None:
    staging = tmp_path / "candidate" / "browse"
    staging.mkdir(parents=True)
    payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    payload["jobs"].append({
        "id": "job-smuggled",
        "publicationStatus": "approved",
        "translationStatus": "verified",
        "visibility": "public",
        "paidStatus": "unconfirmed",
    })
    (staging / "nine-hei-jobs.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    publish._select_approved_jobs(tmp_path / "candidate", LIVE_EVIDENCE)
    selected = json.loads((staging / "nine-hei-jobs.json").read_text(encoding="utf-8"))
    assert "job-smuggled" not in {job["id"] for job in selected["jobs"]}
    assert "job-smuggled" in set(selected["publicationSelection"]["withheldIds"])

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import harvest_nine_hei_jobs as jobs_harvester  # noqa: E402


def _seed(job_id: str) -> dict:
    return next(item for item in jobs_harvester.load_verified_candidates() if item["id"] == job_id)


def test_cenmas_seed_expires_after_closing_announcement() -> None:
    """The discontinued CenMAS call (deadline 14 September 2026) is dropped once
    the announcement date passes: seed carries a real closesAt, and job_record
    returns no record as of today."""
    seed = _seed("job-cuni-cenmas-asia-postdoc")
    assert seed["closesAt"] == "2026-09-14"
    before_close = date(2026, 9, 14)
    record, _ = jobs_harvester.job_record(seed, "2026-09-06T00:00:00Z", True, "", as_of=before_close)
    assert record["id"] == "job-cuni-cenmas-asia-postdoc"
    after_close = date(2026, 9, 22)
    record, _ = jobs_harvester.job_record(seed, "2026-09-06T00:00:00Z", True, "", as_of=after_close)
    assert record == {}


def test_d3s_seed_survives_with_no_deadline() -> None:
    """The rolling D3S call has no closesAt, so the seed survives the same day as
    today (2026-09-22) instead of being expired."""
    seed = _seed("job-cuni-d3s-postdoc")
    assert seed["closesAt"] is None
    assert seed["roundType"] == "rolling"
    record, _ = jobs_harvester.job_record(seed, "2026-09-06T00:00:00Z", True, "", as_of=date(2026, 9, 22))
    assert record["id"] == "job-cuni-d3s-postdoc"


def test_active_snapshot_keeps_expired_cenmas_out_and_d3s_in() -> None:
    pointer = json.loads((ROOT / "data" / "published" / "current.json").read_text(encoding="utf-8"))
    assert pointer["snapshotDir"] == f"snapshots/{pointer['activeVersion']}"
    payload = json.loads(
        (
            ROOT
            / "data"
            / "published"
            / pointer["snapshotDir"]
            / "browse"
            / "nine-hei-jobs.json"
        ).read_text(encoding="utf-8")
    )
    job_ids = {item["id"] for item in payload["jobs"]}
    assert "job-cuni-d3s-postdoc" in job_ids
    assert "job-cuni-cenmas-asia-postdoc" not in job_ids
    assert "job-cuni-cenmas-asia-postdoc" in payload["publicationSelection"]["excludedIds"]
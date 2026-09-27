from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from check_job_coverage import check  # noqa: E402


def _jobs(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": rows}), encoding="utf-8")
    return path


def _floor(tmp_path: Path, identities: int, approved: int) -> Path:
    path = tmp_path / "floor.json"
    path.write_text(
        json.dumps({"identityTotal": identities, "approvedTotal": approved}),
        encoding="utf-8",
    )
    return path


def test_job_floor_passes_when_counts_hold(tmp_path: Path) -> None:
    jobs = _jobs(
        tmp_path,
        [
            {"id": "a", "publicationStatus": "approved"},
            {"id": "b", "publicationStatus": "review_pending"},
        ],
    )
    floor = _floor(tmp_path, 2, 1)
    ok, messages = check(jobs, floor)
    assert ok
    assert "2 identities" in messages[0]


def test_job_floor_fails_when_identities_drop(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path, [{"id": "a", "publicationStatus": "approved"}])
    floor = _floor(tmp_path, 2, 1)
    ok, messages = check(jobs, floor)
    assert not ok
    assert any("identities" in item for item in messages)


def test_job_floor_fails_when_approved_drop(tmp_path: Path) -> None:
    jobs = _jobs(
        tmp_path,
        [
            {"id": "a", "publicationStatus": "review_pending"},
            {"id": "b", "publicationStatus": "review_pending"},
        ],
    )
    floor = _floor(tmp_path, 2, 1)
    ok, messages = check(jobs, floor)
    assert not ok
    assert any("approved" in item for item in messages)

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import safety_status  # noqa: E402
import worker  # noqa: E402
from schedule import ScheduleManager  # noqa: E402

NOW = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)
NOW_TEXT = "2026-09-12T15:00:00Z"


def _job(job_id: str = "job-public-open", **overrides) -> dict:
    payload = {
        "id": job_id,
        "employerId": "msmt-vs_41000",
        "title": {"zh-CN": "研究助理", "en": "Research assistant", "cs": "Výzkumný asistent"},
        "sourceUrl": "https://example.invalid/job",
        "applicationUrl": "https://example.invalid/apply",
        "lifecycleStatus": "open",
        "wholeOpportunityClosed": False,
        "publicationStatus": "approved",
        "visibility": "public",
        "sourceHash": "sha256:" + ("ab" * 32),
    }
    payload.update(overrides)
    return payload


def _window(window_id: str, owner: str, closes: str | None, status: str = "unknown") -> dict:
    return {
        "id": window_id,
        "ownerType": "research_job",
        "ownerId": owner,
        "opensAt": None,
        "closesAt": closes,
        "timezone": "Europe/Prague",
        "datePrecision": "date",
        "status": status,
        "applicationUrl": "https://example.invalid/apply",
    }


def _catalog(job: dict, windows: list[dict]) -> dict:
    return {"jobs": [job], "windows": windows}


def _public_ids(catalog: dict) -> set[str]:
    return {item["id"] for item in catalog["jobs"] if safety_status.job_is_public(item)}


def test_network_failure_is_not_closure() -> None:
    previous = _catalog(_job(), [_window("w1", "job-public-open", "2026-12-01")])
    failed = _catalog(
        _job(lastAttemptReason="recheck_http_503", lastAttemptAt=NOW_TEXT),
        [_window("w1", "job-public-open", "2026-12-01")],
    )
    assert safety_status.closures_from_recheck(previous, failed, NOW_TEXT) == []


def test_page_closure_becomes_whole_opportunity_record() -> None:
    previous = _catalog(_job(), [_window("w1", "job-public-open", "2026-12-01")])
    closed = _catalog(
        _job(
            wholeOpportunityClosed=True,
            lifecycleStatus="closed",
            closureReason="page_announced_closure",
            closedAt=NOW_TEXT,
            lastAttemptReason="recheck_ok",
        ),
        [_window("w1", "job-public-open", "2026-12-01", status="closed")],
    )
    records = safety_status.closures_from_recheck(previous, closed, NOW_TEXT)
    assert len(records) == 2
    whole = next(item for item in records if item["scope"] == "whole_opportunity")
    assert whole["status"] == "closed"
    assert whole["reason"] == "page_announced_closure"
    assert whole["entityId"] == "job-public-open"


def test_overlay_hides_job_from_public_list_but_keeps_detail_tombstone(tmp_path: Path) -> None:
    safety_dir = tmp_path / "safety"
    job = _job()
    windows = [_window("w-future", "job-public-open", "2026-12-01")]
    published = _catalog(job, windows)
    assert "job-public-open" in _public_ids(published)

    payload = safety_status.activate_safety_overlay(
        [
            {
                "entityType": "research_job",
                "entityId": "job-public-open",
                "status": "closed",
                "scope": "whole_opportunity",
                "windowId": None,
                "observedSourceHash": job["sourceHash"],
                "observedAt": NOW_TEXT,
                "closedAt": NOW_TEXT,
                "datePrecision": "datetime",
                "reason": "page_announced_closure",
                "evidenceUrl": job["sourceUrl"],
            }
        ],
        safety_dir=safety_dir,
        source_checked_at=NOW_TEXT,
        now=NOW,
        public_copy=tmp_path / "safety-status.json",
    )
    overlaid = safety_status.apply_overlay_to_catalog(published, payload)
    assert "job-public-open" not in _public_ids(overlaid)
    detail = overlaid["jobs"][0]
    assert detail["id"] == "job-public-open"
    assert detail["wholeOpportunityClosed"] is True
    assert detail["lifecycleStatus"] == "closed"
    assert all(item["status"] == "closed" for item in overlaid["windows"])
    assert (tmp_path / "safety-status.json").is_file()


def test_snapshot_rollback_does_not_reopen_later_closure(tmp_path: Path) -> None:
    safety_dir = tmp_path / "safety"
    older_snapshot = _catalog(_job(), [_window("w1", "job-public-open", "2026-12-01")])
    safety_status.activate_safety_overlay(
        [
            {
                "entityType": "research_job",
                "entityId": "job-public-open",
                "status": "closed",
                "scope": "whole_opportunity",
                "closedAt": NOW_TEXT,
                "reason": "page_announced_closure",
                "evidenceUrl": "https://example.invalid/job",
            }
        ],
        safety_dir=safety_dir,
        now=NOW,
        public_copy=None,
    )
    overlay = safety_status.load_overlay(safety_dir)
    rolled_back = safety_status.apply_overlay_to_catalog(older_snapshot, overlay)
    assert rolled_back["jobs"][0]["wholeOpportunityClosed"] is True
    assert "job-public-open" not in _public_ids(rolled_back)


def test_reopen_without_evidence_is_ignored(tmp_path: Path) -> None:
    safety_dir = tmp_path / "safety"
    safety_status.activate_safety_overlay(
        [
            {
                "entityType": "research_job",
                "entityId": "job-public-open",
                "status": "closed",
                "scope": "whole_opportunity",
                "closedAt": NOW_TEXT,
                "reason": "page_announced_closure",
            }
        ],
        safety_dir=safety_dir,
        now=NOW,
        public_copy=None,
    )
    safety_status.activate_safety_overlay(
        [
            {
                "entityType": "research_job",
                "entityId": "job-public-open",
                "status": "open",
                "scope": "whole_opportunity",
                "reason": "page_reachable_again",
            }
        ],
        safety_dir=safety_dir,
        now=NOW,
        public_copy=None,
    )
    overlay = safety_status.load_overlay(safety_dir)
    whole = next(item for item in overlay["entities"] if item["scope"] == "whole_opportunity")
    assert whole["status"] == "closed"


def test_one_round_closing_leaves_other_round_open(tmp_path: Path) -> None:
    safety_dir = tmp_path / "safety"
    catalog = _catalog(
        _job(),
        [
            _window("round-1", "job-public-open", "2026-09-01"),
            _window("round-2", "job-public-open", "2026-12-01"),
        ],
    )
    payload = safety_status.activate_safety_overlay(
        [
            {
                "entityType": "research_job",
                "entityId": "job-public-open",
                "status": "closed",
                "scope": "window",
                "windowId": "round-1",
                "closedAt": NOW_TEXT,
                "reason": "deadline_expired",
            }
        ],
        safety_dir=safety_dir,
        now=NOW,
        public_copy=None,
    )
    overlaid = safety_status.apply_overlay_to_catalog(catalog, payload)
    by_id = {item["id"]: item for item in overlaid["windows"]}
    assert by_id["round-1"]["status"] == "closed"
    assert by_id["round-2"]["status"] != "closed"
    assert overlaid["jobs"][0]["wholeOpportunityClosed"] is False
    assert "job-public-open" in _public_ids(overlaid)


def test_whole_role_closure_overrides_future_window(tmp_path: Path) -> None:
    safety_dir = tmp_path / "safety"
    catalog = _catalog(_job(), [_window("future", "job-public-open", "2027-01-01")])
    payload = safety_status.activate_safety_overlay(
        [
            {
                "entityType": "research_job",
                "entityId": "job-public-open",
                "status": "closed",
                "scope": "whole_opportunity",
                "closedAt": NOW_TEXT,
                "reason": "page_announced_closure",
            }
        ],
        safety_dir=safety_dir,
        now=NOW,
        public_copy=None,
    )
    overlaid = safety_status.apply_overlay_to_catalog(catalog, payload)
    assert overlaid["jobs"][0]["wholeOpportunityClosed"] is True
    assert overlaid["windows"][0]["status"] == "closed"
    assert "job-public-open" not in _public_ids(overlaid)


def test_recheck_503_does_not_activate_overlay(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(
        json.dumps(_catalog(_job(), [_window("active", "job-public-open", "2026-12-01")])),
        encoding="utf-8",
    )
    safety_dir = tmp_path / "safety"
    worker.recheck_open_jobs(
        fetch_page=lambda _url: (503, ""),
        now=NOW,
        jobs_path=jobs_path,
        schedule_manager=ScheduleManager(tmp_path / "schedule.json"),
        use_lock=False,
        safety_dir=safety_dir,
    )
    overlay = safety_status.load_overlay(safety_dir)
    assert overlay.get("entities") in ([], None) or overlay["generationId"].endswith(".0")
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert payload["jobs"][0]["wholeOpportunityClosed"] is False


def test_verified_recheck_publishes_overlay_and_saved_item_explains_closure(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    job = _job()
    jobs_path.write_text(
        json.dumps(_catalog(job, [_window("w1", "job-public-open", "2026-12-01")])),
        encoding="utf-8",
    )
    safety_dir = tmp_path / "safety"
    worker.recheck_open_jobs(
        fetch_page=lambda _url: (
            200,
            "<h1>Research assistant</h1><p>This position has been filled. Applications are closed.</p>",
        ),
        now=NOW,
        jobs_path=jobs_path,
        schedule_manager=ScheduleManager(tmp_path / "schedule.json"),
        use_lock=False,
        safety_dir=safety_dir,
    )
    overlay = safety_status.load_overlay(safety_dir)
    assert any(item.get("scope") == "whole_opportunity" and item.get("status") == "closed" for item in overlay["entities"])
    saved = safety_status.apply_overlay_to_catalog(_catalog(job, [_window("w1", "job-public-open", "2026-12-01")]), overlay)
    assert saved["jobs"][0]["id"] == "job-public-open"
    assert saved["jobs"][0]["wholeOpportunityClosed"] is True
    assert "job-public-open" not in _public_ids(saved)

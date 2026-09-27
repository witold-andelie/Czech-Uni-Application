"""Tests for the live-evidence publish gate's per-record withholding policy.

Owner decision 2026-09-26 (docs/REFRESH_POLICY.md, docs/ACCEPTANCE.md A96): one
record whose official page no longer verifies it is withheld by id and reason and
the rest of the publication proceeds. These tests hold that line, and hold the
harder line on the other side - a verifier failure that would empty the public
library still stops the run.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from live_evidence import publication_gate  # noqa: E402

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _job(ident: str, **overrides) -> dict:
    job = {
        "id": ident,
        "publicationStatus": "approved",
        "visibility": "public",
        "translationStatus": "verified",
    }
    job.update(overrides)
    return job


def _jobs(*items: dict, windows: list | None = None) -> dict:
    return {"jobs": list(items), "windows": windows or []}


def _evidence(*rows: dict) -> dict:
    return {"confirmedStatuses": ["matched", "operator_verified"], "rows": list(rows)}


def _matched(ident: str) -> dict:
    return {"candidateId": ident, "status": "matched", "checkedAt": RECENT}


def test_one_unconfirmed_record_does_not_hold_the_publication():
    jobs = _jobs(_job("keep"), _job("stale"))
    evidence = _evidence(_matched("keep"), {"candidateId": "stale", "status": "non_match", "checkedAt": RECENT})
    errors, withheld = publication_gate(jobs, evidence, now=NOW)
    assert errors == []
    assert withheld == [("stale", "non_match")]


def test_a_404_row_is_reported_as_withheld_and_never_as_closed():
    """A missing official page is a source change; the gate must not call it closure."""
    jobs = _jobs(_job("keep"), _job("gone"))
    evidence = _evidence(
        _matched("keep"), {"candidateId": "gone", "status": "http_404", "checkedAt": RECENT}
    )
    errors, withheld = publication_gate(jobs, evidence, now=NOW)
    assert errors == []
    assert withheld == [("gone", "http_404")]


def test_nothing_verified_holds_the_run_because_it_would_publish_an_empty_library():
    jobs = _jobs(_job("one"), _job("two"))
    evidence = _evidence({"candidateId": "one", "status": "http_404", "checkedAt": RECENT})
    errors, withheld = publication_gate(jobs, evidence, now=NOW)
    assert withheld == [("one", "http_404"), ("two", "no evidence row")]
    assert all(error.startswith("LIVE_EVIDENCE_MISSING") for error in errors)
    assert any("empty research library" in error for error in errors)


def test_an_absent_evidence_file_holds_the_run():
    errors, withheld = publication_gate(_jobs(_job("keep")), {}, now=NOW)
    assert withheld == []
    assert errors == [
        "LIVE_EVIDENCE_MISSING: live-title-verification.json is missing or empty: "
        "run verify_live_titles.py before publishing"
    ]


def test_a_closed_window_is_not_required_to_re_prove_its_announcement():
    jobs = _jobs(
        _job("keep"),
        _job("lapsed"),
        windows=[
            {"ownerType": "research_job", "ownerId": "lapsed", "closesAt": "2026-09-01T00:00:00Z"},
        ],
    )
    evidence = _evidence(_matched("keep"))
    errors, withheld = publication_gate(jobs, evidence, now=NOW)
    assert errors == []
    assert withheld == []


def test_an_archived_or_review_pending_record_is_not_gated():
    jobs = _jobs(
        _job("keep"),
        _job("archived", visibility="archived"),
        _job("pending", publicationStatus="review_pending"),
        _job("unreviewed", translationStatus="machine"),
        _job("gone", lifecycleStatus="unavailable"),
    )
    evidence = _evidence(_matched("keep"))
    errors, withheld = publication_gate(jobs, evidence, now=NOW)
    assert errors == []
    assert withheld == []


def _run_cli(jobs_path: Path, evidence_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "services" / "ingestion" / "src" / "cli" / "check_live_evidence.py"),
            "--jobs",
            str(jobs_path),
            "--evidence",
            str(evidence_path),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_cli_reports_the_withheld_records_and_succeeds(tmp_path: Path):
    jobs_path = tmp_path / "nine-hei-jobs.json"
    evidence_path = tmp_path / "live-title-verification.json"
    jobs_path.write_text(
        json.dumps(_jobs(_job("keep"), _job("unread"))), encoding="utf-8"
    )
    evidence_path.write_text(
        json.dumps(
            _evidence(
                _matched("keep"),
                {"candidateId": "unread", "status": "source_change_noted", "checkedAt": RECENT},
            )
        ),
        encoding="utf-8",
    )
    result = _run_cli(jobs_path, evidence_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "held unread: source_change_noted" in result.stdout
    assert "withheld by id and reason" in result.stdout


def test_the_cli_fails_when_nothing_is_verified(tmp_path: Path):
    jobs_path = tmp_path / "nine-hei-jobs.json"
    evidence_path = tmp_path / "live-title-verification.json"
    jobs_path.write_text(json.dumps(_jobs(_job("only"))), encoding="utf-8")
    evidence_path.write_text(json.dumps(_evidence()), encoding="utf-8")
    result = _run_cli(jobs_path, evidence_path)
    assert result.returncode == 1
    assert "publication held" in result.stdout


def test_the_cli_strict_flag_holds_on_a_single_record(tmp_path: Path):
    jobs_path = tmp_path / "nine-hei-jobs.json"
    evidence_path = tmp_path / "live-title-verification.json"
    jobs_path.write_text(
        json.dumps(_jobs(_job("keep"), _job("unread"))), encoding="utf-8"
    )
    evidence_path.write_text(
        json.dumps(
            _evidence(
                _matched("keep"),
                {"candidateId": "unread", "status": "source_change_noted", "checkedAt": RECENT},
            )
        ),
        encoding="utf-8",
    )
    result = _run_cli(jobs_path, evidence_path, "--strict")
    assert result.returncode == 1
    assert "unread" in result.stdout

"""Offline tests for the live title-matching rules and the evidence gate.

No network access: the matcher is pure text logic, and the gate only reads
evidence JSON from disk.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from live_title_matching import (  # noqa: E402
    extract_pdf_text,
    norm,
    norm_title,
    strip_gender_marker,
    title_matches,
)

def _titles(**kwargs: str) -> list[dict[str, str]]:
    return [{"title": value, "locale": locale} for locale, value in kwargs.items()]


def test_contiguous_title_matches() -> None:
    page = "<html><body><h1>Odborný pracovník v analytické laboratoři</h1></body></html>"
    result = title_matches(page, _titles(**{"cs": "Odborný pracovník v analytické laboratoři"}))
    assert result["matched"] is True
    assert result["matchedLocale"] == "cs"
    assert "analytické laboratoři" in result["contextSnippet"]


def test_dual_gender_slash_form_matches_masculine_title() -> None:
    """VŠCHT renders ODBORNÝ/NÁ PRACOVNÍK/CE for a reviewed masculine title."""
    page = "<p>Laboratoř hledá zaměstnance na pozici ODBORNÝ/NÁ PRACOVNÍK/CE V ANALYTICKÉ LABORATOŘI (úvazek 1,0) - 560</p>"
    result = title_matches(page, _titles(**{"cs": "Odborný pracovník v analytické laboratoři", "en": "Odborný pracovník v analytické laboratoři"}))
    assert result["matched"] is True
    assert result["contextSnippet"]


def test_gender_marker_is_stripped_from_the_needle_only() -> None:
    assert strip_gender_marker("provozní technik - strojní zámečník m/ž") == "provozní technik - strojní zámečník"
    assert strip_gender_marker("postdoktorská pozice (m/ž)") == "postdoktorská pozice"
    # a page spelling stays untouched
    page = "PROVOZNÍ TECHNIK – STROJNÍ ZÁMEČNÍK, OBSLUHA NEUTRALIZAČNÍ STANICE A ÚDRŽBA BUDOVY"
    result = title_matches(page, _titles(**{"cs": "Provozní technik - strojní zámečník M/Ž"}))
    assert result["matched"] is True


def test_slash_spacing_variants_both_ways() -> None:
    # official page renders "pracovnice/ Akademický", review stores "pracovnice/Akademický"
    page = "<p>pozice pracovnice/ Akademický pracovník na katedře</p>"
    result = title_matches(page, _titles(**{"cs": "pracovnice/Akademický pracovník"}))
    assert result["matched"] is True
    # and the mirror case: review stores a spaced slash, page does not
    page = "<p>pozice pracovnice/Akademický pracovník na katedře</p>"
    result = title_matches(page, _titles(**{"cs": "pracovnice / Akademický pracovník"}))
    assert result["matched"] is True


def test_department_clause_block() -> None:
    page = "<h2>DevOps &amp; Software Engineer</h2><p>Katedra kybernetiky</p>"
    result = title_matches(page, _titles(**{"en": "DevOps & Software Engineer Department: Department of Cybernetics"}))
    assert result["matched"] is True


def test_distinctive_substring() -> None:
    """A page that spells the tail of a title differently still proves it."""
    page = "Děkan vyhlašuje výběrové řízení na místo Odborný asistent v oboru informatických technologií, Katedra aplikované matematiky."
    result = title_matches(page, _titles(**{"cs": "Odborný asistent v oboru informatických technologií pro Katedru aplikované matematiky"}))
    assert result["matched"] is True
    assert "informatických technologií" in result["contextSnippet"]


def test_unrelated_page_does_not_match() -> None:
    page = "<html><body>Volná místa: údržbář, kuchař, receptář</body></html>"
    result = title_matches(page, _titles(**{"cs": "Odborný asistent v oboru informatika"}))
    assert result["matched"] is False


def test_short_and_empty_titles_are_ignored() -> None:
    result = title_matches("random page text", _titles(**{"cs": "", "en": "short"}))
    assert result["matched"] is False


def test_norm_collapses_entities_and_whitespace() -> None:
    assert norm(" A&nbsp;B – C ") == "a b - c"
    assert norm_title("  PhD student ") == "phd student"


def test_extract_pdf_text_reports_failure_without_inventing_text() -> None:
    text = extract_pdf_text(b"not a pdf at all")
    assert "error" in text.lower()
    assert "not a pdf" not in text


# ---------------------------------------------------------------------------
# Evidence gate (offline)
# ---------------------------------------------------------------------------

from live_evidence import missing_live_evidence  # noqa: E402


def _evidence(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "generatedAt": "2026-09-26T00:00:00Z",
        "confirmedStatuses": ["matched", "operator_verified"],
        "rows": rows,
    }


def _row(candidate_id: str, status: str, checked_at: str = "2026-09-26T00:00:00Z") -> dict[str, object]:
    return {"candidateId": candidate_id, "status": status, "checkedAt": checked_at}


def _job(candidate_id: str, **overrides: object) -> dict[str, object]:
    """A job in the same state publication would expose, so the gate checks it."""
    job: dict[str, object] = {
        "id": candidate_id,
        "publicationStatus": "approved",
        "visibility": "public",
        "translationStatus": "verified",
        "lifecycleStatus": "unknown",
    }
    job.update(overrides)
    return job


def test_gate_accepts_recent_confirmed_rows() -> None:
    missing = missing_live_evidence(
        {"jobs": [_job("a"), _job("b")]},
        _evidence([_row("a", "matched"), _row("b", "operator_verified")]),
        now=datetime.fromisoformat("2026-09-26T00:00:00+00:00"),
    )
    assert missing == []


def test_gate_only_checks_jobs_publication_would_expose() -> None:
    # Archived, blocked and untranslated candidates are not entering the
    # snapshot, so the gate does not demand fresh proof of them.
    missing = missing_live_evidence(
        {"jobs": [_job("live"), _job("closed", lifecycleStatus="closed"), _job("hidden", visibility="private")]},
        _evidence([_row("live", "matched")]),
        now=datetime.fromisoformat("2026-09-26T00:00:00+00:00"),
    )
    assert missing == []


def test_gate_rejects_stale_and_unconfirmed_rows() -> None:
    evidence = _evidence(
        [
            _row("stale", "matched", "2026-09-01T00:00:00Z"),
            _row("dead", "non_match"),
            _row("gone", "http_404"),
            _row("failed", "fetch_error"),
            _row("changed", "source_change_noted"),
        ]
    )
    missing = missing_live_evidence(
        {"jobs": [_job("stale"), _job("dead"), _job("gone"), _job("failed"), _job("changed")]},
        evidence,
        now=datetime.fromisoformat("2026-09-26T00:00:00+00:00"),
    )
    assert [job_id for job_id, _ in missing] == ["changed", "dead", "failed", "gone", "stale"]


def test_gate_reports_missing_evidence_for_snapshot_jobs(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(_evidence([_row("known", "matched")])), encoding="utf-8")
    snap = tmp_path / "jobs.json"
    snap.write_text(
        json.dumps({"jobs": [_job("known"), _job("unknown")]}), encoding="utf-8"
    )
    missing = missing_live_evidence(
        json.loads(snap.read_text(encoding="utf-8")),
        json.loads(evidence.read_text(encoding="utf-8")),
        now=datetime.fromisoformat("2026-09-26T00:00:00+00:00"),
    )
    assert missing == [("unknown", "no evidence row")]


def test_gate_exempts_jobs_whose_window_has_closed() -> None:
    evidence = _evidence([])
    jobs = {
        "jobs": [_job("past"), _job("future"), _job("no-window")],
        "windows": [
            {"id": "w1", "ownerId": "past", "closesAt": "2026-09-20T00:00:00Z"},
            {"id": "w2", "ownerId": "future", "closesAt": "2026-12-01T00:00:00Z"},
        ],
    }
    missing = missing_live_evidence(
        jobs, evidence, now=datetime.fromisoformat("2026-09-26T00:00:00+00:00")
    )
    assert [job_id for job_id, _ in missing] == ["future", "no-window"]


def test_gate_requires_evidence_when_the_file_is_missing() -> None:
    missing = missing_live_evidence({"jobs": [{"id": "a"}]}, {})
    assert missing[0][0] == "<evidence>"


def test_gate_cli_holds_publication_and_names_the_reason(tmp_path: Path) -> None:
    import subprocess

    jobs = tmp_path / "jobs.json"
    jobs.write_text(
        json.dumps({"jobs": [_job("confirmed"), _job("gone")], "windows": []}), encoding="utf-8"
    )
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(_evidence([_row("confirmed", "matched"), _row("gone", "source_change_noted")])),
        encoding="utf-8",
    )
    script = ROOT / "services" / "ingestion" / "src" / "cli" / "check_live_evidence.py"
    held = subprocess.run(
        [sys.executable, str(script), "--jobs", str(jobs), "--evidence", str(evidence)],
        capture_output=True,
        text=True,
    )
    assert held.returncode == 1
    assert "publication held: 1 job(s)" in held.stdout
    assert "gone: source_change_noted" in held.stdout

    evidence.write_text(
        json.dumps(_evidence([_row("confirmed", "matched"), _row("gone", "matched")])),
        encoding="utf-8",
    )
    passed = subprocess.run(
        [sys.executable, str(script), "--jobs", str(jobs), "--evidence", str(evidence)],
        capture_output=True,
        text=True,
    )
    assert passed.returncode == 0
    assert "live evidence ok" in passed.stdout

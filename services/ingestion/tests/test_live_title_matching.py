"""Offline tests for the live title-matching rules and the evidence gate.

No network access: the matcher is pure text logic, and the gate only reads
evidence JSON from disk.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
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


def test_an_entity_dash_on_the_page_matches_the_title_dash() -> None:
    """2026-10-10: the RoboProx table writes "&#8211;"; the dash stayed past the folding."""
    page = '<td><a href="https://www.euraxess.cz/jobs/190055">Postdoc Position &#8211; Robots with whole-body tactile sensing</a></td>'
    assert norm(page) == norm("Postdoc Position – Robots with whole-body tactile sensing")
    assert title_matches(page, _titles(en="Postdoc Position – Robots with whole-body tactile sensing"))["matched"] is True


def test_curly_quotes_on_the_page_match_the_title() -> None:
    """2026-10-10: CTU's 6G PhD notice shows its title verbatim and matched nothing."""
    page = "Posted on: 16 September 2026 PhD position in “Semantic Communication for Robots” Apply now"
    titles = _titles(en="PhD position in “Semantic Communication for Robots”", cs='Doktorská pozice "Sémantické komunikace"')
    assert title_matches(page, titles)["matched"] is True
    assert norm("„Univerzita“ ‘x’") == norm("\"Univerzita\" 'x'")


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


def test_gate_cli_withholds_one_record_and_publishes_the_rest(tmp_path: Path) -> None:
    """One source change no longer holds the whole publication.

    Owner decision 2026-09-26 (docs/REFRESH_POLICY.md, docs/ACCEPTANCE.md A96):
    the record is withheld by id and reason inside the snapshot and everything
    else publishes, so the gate reports it and exits 0. `--strict` keeps the
    older hard stop for an operator who wants one.
    """
    import subprocess

    jobs = tmp_path / "jobs.json"
    jobs.write_text(
        json.dumps({"jobs": [_job("confirmed"), _job("gone")], "windows": []}), encoding="utf-8"
    )
    evidence = tmp_path / "evidence.json"
    # The CLI judges freshness against the real clock: check "now".
    checked = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence.write_text(
        json.dumps(
            {
                **_evidence([_row("confirmed", "matched", checked), _row("gone", "source_change_noted", checked)]),
                "generatedAt": checked,
            }
        ),
        encoding="utf-8",
    )
    script = ROOT / "services" / "ingestion" / "src" / "cli" / "check_live_evidence.py"
    held = subprocess.run(
        [sys.executable, str(script), "--jobs", str(jobs), "--evidence", str(evidence)],
        capture_output=True,
        text=True,
    )
    assert held.returncode == 0
    assert "will be withheld by id and reason" in held.stdout
    assert "held gone: source_change_noted" in held.stdout

    strict = subprocess.run(
        [sys.executable, str(script), "--jobs", str(jobs), "--evidence", str(evidence), "--strict"],
        capture_output=True,
        text=True,
    )
    assert strict.returncode == 1
    assert "publication held" in strict.stdout
    assert "gone has no live verification within 7 days (source_change_noted)" in strict.stdout

    evidence.write_text(
        json.dumps({**_evidence([_row("confirmed", "matched", checked), _row("gone", "matched", checked)]), "generatedAt": checked}),
        encoding="utf-8",
    )
    passed = subprocess.run(
        [sys.executable, str(script), "--jobs", str(jobs), "--evidence", str(evidence)],
        capture_output=True,
        text=True,
    )
    assert passed.returncode == 0
    assert "live evidence ok" in passed.stdout


def test_a_record_the_budget_did_not_reach_keeps_its_earlier_confirmation(tmp_path: Path) -> None:

    script = ROOT / "services" / "ingestion" / "src" / "cli" / "verify_live_titles.py"
    source = script.read_text(encoding="utf-8")
    # The budget branch carries a confirmed earlier row instead of overwriting it.
    budget = source.index("time.time() - started >= args.budget")
    assert source.index('previous.get("status") in confirmed', budget) < source.index('"status": "skipped_budget"', budget)


def test_a_host_that_does_not_answer_is_asked_once_per_run(tmp_path: Path, monkeypatch) -> None:
    """2026-10-22..27: eud.is.cvut.cz answered nothing; seven archived notices on it,
    never confirmed and so first in line, spent each whole budget (some 3.5 minutes
    each) while the confirmations of 80 public posts lapsed."""
    sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src" / "cli"))
    import verify_live_titles as v

    dead, live = "https://eud.is.cvut.cz/pub/deska/36000002/ifis/", "https://www.vut.cz/jobs/"

    def task(ident: str, url: str, archived: bool = False) -> dict:
        return {"candidateId": ident, "employerId": "msmt-vs_21000", "sourceUrl": url, "applicationUrl": url,
                "sourceHash": "sha256:x", "discoverySourceId": None, "archived": archived,
                "titles": [{"locale": "cs", "title": "Postdoktorand v robotice"}]}

    tasks = [task("old-archived", dead + "5471", archived=True), task("confirmed", dead + "5581"),
             task("never", dead + "5590"), task("elsewhere", live + "1")]
    previous = {"generatedAt": "2026-10-21T09:00:00Z", "rows": [
        {"candidateId": "confirmed", "status": "matched", "checkedAt": "2026-10-21T09:00:00Z", "httpStatus": 200},
        {"candidateId": "elsewhere", "status": "matched", "checkedAt": "2026-10-20T09:00:00Z", "httpStatus": 200}]}
    (tmp_path / "previous.json").write_text(json.dumps(previous), encoding="utf-8")
    fetched: list[str] = []

    def vet(url):
        fetched.append(url)
        if url.startswith(dead):
            return {"httpStatus": 0, "finalUrl": url, "tool": "scrapling_get", "bodyText": "", "blocked": False, "blockedReasons": []}
        return {"httpStatus": 200, "finalUrl": url, "tool": "scrapling_get", "bodyText": "<h1>Postdoktorand v robotice</h1>",
                "blocked": False, "blockedReasons": []}

    monkeypatch.setattr(v, "load_tasks", lambda _status: list(tasks))
    monkeypatch.setattr(v, "discovery_listing_page", lambda _task: None)
    monkeypatch.setattr(v, "vet_one", vet)
    monkeypatch.setattr(v, "HOST_DELAY_S", 0)
    out = tmp_path / "live.json"
    monkeypatch.setattr(sys, "argv", ["verify_live_titles.py", "--output", str(out), "--merge-from", str(tmp_path / "previous.json"),
                                      "--operator-evidence", str(tmp_path / "none.json")])
    try:
        v.main()
    except SystemExit:
        pass
    rows = {row["candidateId"]: row for row in json.loads(out.read_text(encoding="utf-8"))["rows"]}
    assert sum(url.startswith(dead) for url in fetched) == 1
    assert dead + "5471" not in fetched  # the archived notice comes last, after its host went quiet
    assert rows["elsewhere"]["status"] == "matched"
    assert rows["confirmed"]["status"] == "matched" and rows["confirmed"]["carriedFrom"] == "2026-10-21T09:00:00Z"
    assert rows["never"]["status"] in {"skipped_budget", "http_0"}
    unanswered = [row for row in rows.values() if row["status"] == "skipped_budget"]
    assert unanswered and all("did not answer" in row["reason"] for row in unanswered)

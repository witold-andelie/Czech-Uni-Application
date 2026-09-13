from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import harvest_czu_doctoral_programmes as doctoral  # noqa: E402
import worker  # noqa: E402
from schedule import ScheduleManager, to_iso  # noqa: E402


def _inventory() -> dict:
    return json.loads(doctoral.INVENTORY.read_text(encoding="utf-8"))


def _complete_assets() -> dict[str, dict]:
    rows = doctoral._load_doctoral_inventory(_inventory())
    assets: dict[str, dict] = {}
    specs = {item["id"]: item for item in doctoral.SOURCE_ASSETS}
    for source_id, spec in specs.items():
        assets[source_id] = {
            "url": spec["url"],
            "httpStatus": 200,
            "contentType": "application/pdf" if spec["kind"] != "html" else "text/html",
            "bytes": 100,
            "sha256": "a" * 64,
            "sourceLanguage": spec["sourceLanguage"],
            "extractionMethod": "test_fixture",
            "reviewedAt": spec.get("reviewedAt"),
            "text": " ".join(spec.get("expectedTokens", ())),
        }

    for row in rows:
        rule = doctoral.FACULTY_RULES[row["faculty"]]
        for source_id in rule["programmeEvidence"][row["studyLanguage"]]:
            title = row["titleOriginal"]
            if title == "Ochrana lesů a myslivosti":
                title = "Ochrana lesů a myslivost"
            assets[source_id]["text"] += f" {title}"
        for window in rule["windows"][row["studyLanguage"]]:
            assets[window["sourceId"]]["text"] += " " + " ".join(
                window["verificationTokens"]
            )
    return assets


def test_czu_doctoral_crosscheck_matches_all_register_offerings() -> None:
    payload = doctoral.build_catalog(
        _inventory(),
        _complete_assets(),
        now=datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc),
    )

    assert payload["catalogKind"] == "candidate_not_published"
    assert payload["counts"]["programmes"] == 60
    assert payload["counts"]["faculties"] == 6
    assert payload["counts"]["teachingLanguages"] == {"cs": 30, "en": 30}
    assert payload["counts"]["matchedToFacultyAdmissionEvidence"] == 60
    assert payload["counts"]["withAnyOfficialWindow"] == 60
    assert payload["counts"]["closedByOfficialDates"] == 60
    assert payload["counts"]["openByOfficialDates"] == 0
    assert payload["coverage"]["complete"] is True
    assert payload["coverage"]["allApplicationWindowsClosedAtFetch"] is True
    assert len(payload["coverage"]["facultyCoverage"]) == 6
    variant = next(
        item for item in payload["programmes"] if item["titleOriginal"] == "Ochrana lesů a myslivosti"
    )
    assert variant["sourceTitleVariant"] == "Ochrana lesů a myslivost"


def test_unknown_start_never_becomes_open_from_future_end_alone() -> None:
    window = {"start": None, "end": "2026-10-01"}
    assert (
        doctoral._window_status(
            window, datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
        )
        == "unknown"
    )


def test_conditional_round_is_not_reported_open_without_confirmation() -> None:
    window = {
        "start": "2026-07-07",
        "end": "2026-08-11",
        "conditionalOnVacancies": True,
        "confirmedOpened": False,
    }
    assert (
        doctoral._window_status(
            window, datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        )
        == "unknown"
    )


def test_reviewed_scan_hash_change_fails_closed() -> None:
    spec = next(item for item in doctoral.SOURCE_ASSETS if item["kind"] == "reviewed_scan")
    with pytest.raises(doctoral.HarvestIncomplete, match="Reviewed scan changed"):
        doctoral._extract_asset_text(spec, b"changed scan", {"Content-Type": "application/pdf"})


def test_czu_doctoral_refresh_has_independent_two_hour_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    payload = doctoral.build_catalog(_inventory(), _complete_assets(), now=now)
    monkeypatch.setattr(doctoral, "harvest_catalog", lambda **_kwargs: payload)
    monkeypatch.setattr(worker, "RUNS", tmp_path / "runs")
    manager = ScheduleManager(tmp_path / "schedule.json")
    manager.init_state(now)

    result = worker.refresh_czu_doctoral_programme_availability(
        now=now,
        output_path=tmp_path / "doctoral.json",
        schedule_manager=manager,
        use_lock=False,
    )
    state = manager.load_state(now)
    task = state["czuDoctoralProgrammeAvailability"]
    assert result["published"] is False
    assert task["programmesCount"] == 60
    assert task["matchedProgrammesCount"] == 60
    assert task["lastSuccessAt"] == to_iso(now)
    assert task["nextDueAt"] == to_iso(now + timedelta(hours=2))
    assert state["czuCzechProgrammeAvailability"]["lastSuccessAt"] is None

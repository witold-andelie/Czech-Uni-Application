from __future__ import annotations

import copy
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


def _register_rows() -> list[dict]:
    """The CZU doctoral offerings in the committed register; MŠMT adds some (60 -> 62 on 2026-10-14)."""
    return doctoral._load_doctoral_inventory(_inventory())


def _complete_assets(inventory: dict | None = None) -> dict[str, dict]:
    rows = doctoral._load_doctoral_inventory(inventory or _inventory())
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

    rows = _register_rows()
    languages = {lang: sum(row["studyLanguage"] == lang for row in rows) for lang in ("cs", "en")}
    assert payload["catalogKind"] == "candidate_not_published"
    assert payload["counts"]["programmes"] == len(rows)
    assert payload["counts"]["faculties"] == 6
    assert payload["counts"]["teachingLanguages"] == languages
    assert payload["counts"]["matchedToFacultyAdmissionEvidence"] == len(rows)
    assert payload["counts"]["withAnyOfficialWindow"] == len(rows)
    assert payload["counts"]["closedByOfficialDates"] == len(rows)
    assert payload["counts"]["openByOfficialDates"] == 0
    assert payload["coverage"]["complete"] is True
    assert payload["coverage"]["allApplicationWindowsClosedAtFetch"] is True
    assert len(payload["coverage"]["facultyCoverage"]) == 6


def _register_spelling(title: str) -> dict:
    """A copy of the register that spells one doctoral offering ``title``.

    Until 2026-10-23 MŠMT spelt "Ochrana lesů a myslivosti" where the faculty
    writes "myslivost"; on 10-24 the register was corrected, and a test that
    looked the old spelling up in the day's data failed CI from that day.
    """
    inventory = copy.deepcopy(_inventory())
    school = next(item for item in inventory["schools"] if item["id"] == doctoral.INSTITUTION_ID)
    doctoral_rows = [row for row in school["rows"] if row[2] == "d"]
    row = next((row for row in doctoral_rows if row[1].startswith("Ochrana lesů a myslivost")), doctoral_rows[0])
    row[1] = title
    return inventory


def test_a_register_spelling_the_faculty_writes_otherwise_is_matched_through_its_alias() -> None:
    inventory = _register_spelling("Ochrana lesů a myslivosti")
    payload = doctoral.build_catalog(inventory, _complete_assets(inventory), now=datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc))
    variant = next(item for item in payload["programmes"] if item["titleOriginal"] == "Ochrana lesů a myslivosti")
    assert variant["sourceTitleVariant"] == "Ochrana lesů a myslivost"
    assert payload["counts"]["matchedToFacultyAdmissionEvidence"] == len(_register_rows())


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
    assert task["programmesCount"] == len(_register_rows())
    assert task["matchedProgrammesCount"] == len(_register_rows())
    assert task["lastSuccessAt"] == to_iso(now)
    assert task["nextDueAt"] == to_iso(now + timedelta(hours=24))
    assert state["czuCzechProgrammeAvailability"]["lastSuccessAt"] is None


def _drop_titles(assets: dict[str, dict], count: int) -> list[str]:
    """Remove `count` register titles from the faculty evidence they were matched in."""
    rows = _register_rows()
    expected = {token for spec in doctoral.SOURCE_ASSETS for token in spec.get("expectedTokens", ())}
    dropped: list[str] = []
    for row in rows:
        title = row["titleOriginal"]
        evidence = doctoral.FACULTY_RULES[row["faculty"]]["programmeEvidence"][row["studyLanguage"]]
        texts = [assets[source_id]["text"] for source_id in evidence]
        if title in expected or any(text.count(title) != 1 for text in texts) or title == "Ochrana lesů a myslivosti":
            continue
        if any(title in other["titleOriginal"] and other is not row for other in rows):
            continue
        for source_id in evidence:
            assets[source_id]["text"] = assets[source_id]["text"].replace(f" {title}", "")
        dropped.append(title)
        if len(dropped) == count:
            return dropped
    raise AssertionError("not enough droppable titles")


def test_a_register_offering_the_admissions_call_does_not_name_is_kept_without_a_window() -> None:
    """2026-10-09: MŠMT listed doctoral "Forest Science" at FLD after the 2026/2027 call."""
    assets = _complete_assets()
    (title,) = _drop_titles(assets, 1)
    payload = doctoral.build_catalog(_inventory(), assets, now=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc))
    kept = next(item for item in payload["programmes"] if item["titleOriginal"] == title)
    assert kept["applicationWindows"] == [] and kept["applicationStatus"] == "unknown"
    assert kept["admissionAnnouncement"] == "not_in_current_announcement"
    assert payload["counts"]["programmes"] == len(_register_rows())
    assert payload["counts"]["notInCurrentAdmissionAnnouncement"] == 1
    assert payload["counts"]["matchedToFacultyAdmissionEvidence"] == len(_register_rows()) - 1
    assert payload["coverage"]["complete"] is False


def test_many_offerings_missing_from_the_calls_still_stop_the_pass() -> None:
    assets = _complete_assets()
    _drop_titles(assets, 3)
    with pytest.raises(doctoral.HarvestIncomplete, match="were not found in faculty evidence"):
        doctoral.build_catalog(_inventory(), assets, now=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc))

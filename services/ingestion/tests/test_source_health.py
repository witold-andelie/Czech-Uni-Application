from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import harvest_nine_hei_jobs as harvest  # noqa: E402
import source_health  # noqa: E402

AVCR_INLINE = (
    "<div class='vystupy'>Czech Academy of Sciences announces ... the following job openings:<br><br>"
    "<div style='padding:20px 0'><b>09/30/2026</b><br><b>Institute of Physics of the CAS</b> announces an open "
    "competition ... for a position <b>Postdoctoral Researcher – Magnetism in Thin-Film Materials. </b><br>"
    "<b><a href='?inzerat=1908' style='line-height:2.8'>Requirements</a></b><br>Application deadline: <b>10/21/2026</b></div>"
    "<div style='padding:20px 0'><b>09/30/2026</b><br><b>Institute of Molecular Genetics of the CAS</b> announces "
    "an open competition ... for a position <b>Preclinical Study Coordinator. </b><br>"
    "<b><a href='?inzerat=1909'>Requirements</a></b><br>Application deadline: <b>10/31/2026</b></div>"
    "<div style='padding:20px 0'><b>09/24/2026</b><br><b>Heyrovsk&yacute; Institute of the CAS</b> announces "
    "an open competition ... for a position <b>Senior scientist / postdoctoral researcher in Electrochemistry. </b><br>"
    "<b><a href='?inzerat=1897'>Requirements</a></b><br>Application deadline: <b>10/08/2026</b></div></div>"
)


def test_avcr_inline_list_yields_research_openings_with_institute_and_deadline() -> None:
    rows = harvest.parse_avcr_vacancies(AVCR_INLINE)
    assert [row["code"] for row in rows] == ["avcr1908", "avcr1897"]
    first = rows[0]
    assert first["title"] == "Postdoctoral Researcher – Magnetism in Thin-Film Materials"
    assert first["sourceUrl"] == "https://www.avcr.cz/en/about-us/career/selection-procedures/?inzerat=1908"
    assert first["employerName"] == "Institute of Physics of the CAS"
    assert first["listingDeadline"] == "2026-10-21"
    assert first["employerId"] is None
    assert rows[1]["employerName"] == "Heyrovský Institute of the CAS"


def test_avcr_openings_quarantine_with_their_institute_and_count_as_listed() -> None:
    source = {
        "id": "avcr-selection-procedures",
        "url": "https://www.avcr.cz/en/about-us/career/selection-procedures/",
        "baseUrl": "https://www.avcr.cz",
        "official": True,
        "sourceType": "official_job_listing",
        "employerId": None,
        "parser": "avcr_vacancies",
        "followDetails": True,
    }
    result = harvest.discover_registered_candidates(lambda url: (200, AVCR_INLINE), registry=[source])
    assert result["candidates"] == []
    assert {row["employerName"] for row in result["quarantined"]} == {
        "Institute of Physics of the CAS",
        "Heyrovský Institute of the CAS",
    }
    assert result["listedBySource"] == {"avcr-selection-procedures": 2}


def _day(ledger: dict, day: str, listed: int | None, complete: bool) -> dict:
    return source_health.update(ledger, [{"sourceId": "s", "listed": listed, "complete": complete}], day)


def test_alarm_when_a_source_that_listed_vacancies_goes_empty() -> None:
    ledger = {"sources": {}}
    _day(ledger, "2026-10-01", 14, True)
    _day(ledger, "2026-10-02", 0, True)
    assert source_health.alarms(ledger) == []
    _day(ledger, "2026-10-03", 0, True)
    assert len(source_health.alarms(ledger)) == 1
    assert "listed no rows" in source_health.alarms(ledger)[0]
    # The same day written again (each checkpoint of a tick) changes nothing.
    _day(ledger, "2026-10-03", 0, True)
    assert len(ledger["sources"]["s"]["history"]) == 3


def test_no_alarm_for_a_small_school_without_current_vacancies() -> None:
    ledger = {"sources": {}}
    for day, listed in (("2026-10-01", 1), ("2026-10-02", 0), ("2026-10-03", 0)):
        _day(ledger, day, listed, True)
    assert source_health.alarms(ledger) == []


def test_alarm_when_a_source_stays_incomplete() -> None:
    ledger = {"sources": {}}
    for day, complete in (("2026-10-01", False), ("2026-10-02", False)):
        _day(ledger, day, 5, complete)
    assert source_health.alarms(ledger) == []
    _day(ledger, "2026-10-03", 5, False)
    assert "incomplete" in source_health.alarms(ledger)[0]
    _day(ledger, "2026-10-04", 5, True)
    assert source_health.alarms(ledger) == []


def test_observations_skip_sources_a_bounded_pass_has_not_reached() -> None:
    discovery = {
        "expectedSourceIds": ["a", "b", "c", "d"],
        "completeSourceIds": ["a"],
        "deferredSourceIds": ["c"],
        "listedBySource": {"a": 4},
        "attempts": [{"sourceId": "b", "ok": False}, {"sourceId": "e", "kind": "adapter", "listed": 9}],
    }
    rows = source_health.observations_from_discovery(discovery)
    assert rows == [
        {"sourceId": "a", "listed": 4, "complete": True},
        {"sourceId": "b", "listed": None, "complete": False},
    ]


def test_record_writes_a_day_keyed_ledger(tmp_path: Path) -> None:
    path = tmp_path / "coverage" / "source-health.json"
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    source_health.record([{"sourceId": "a", "listed": 3, "complete": True}], path, now)
    source_health.record([{"sourceId": "a", "listed": 4, "complete": True}], path, now)
    ledger = json.loads(path.read_text(encoding="utf-8"))
    assert ledger["sources"]["a"]["history"] == [{"day": "2026-10-03", "listed": 4, "complete": True}]
    assert ledger["sources"]["a"]["peakListed"] == 4

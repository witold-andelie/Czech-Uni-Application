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


def test_avcr_openings_resolve_to_their_institute_and_count_as_listed() -> None:
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
    # The institute each opening names is its employer (v. v. i. register).
    assert {row["employerId"] for row in result["candidates"]} == {"rvvi-68378271", "rvvi-61388955"}
    assert result["quarantined"] == []
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


def test_institute_listings_honour_base_href_and_keep_research_titles_only() -> None:
    html = (
        '<base href="https://www.imc.cas.cz/cs/">'
        '<a href="o-ustavu/pracovni-mista/postdoktorandska-pozice-polymery">Postdoktorandská pozice v Oddělení polymerů</a>'
        '<a href="o-ustavu/pracovni-mista/hr-asistentka">HR asistent*ka</a>'
        '<a href="o-ustavu/pracovni-mista/asistent-reditele">Asistent / asistentka zástupce ředitele pro vědu a výzkum</a>'
        '<a href="o-ustavu/pracovni-mista/zapojte-se">Zapojte se do honorovaného výzkumu</a>'
    )
    rows = harvest.parse_generic_listing_links(
        html,
        "https://www.imc.cas.cz/cs/o-ustavu/pracovni-mista/",
        [r"/cs/o-ustavu/pracovni-mista/[a-z0-9-]+$"],
        research_titles_only=True,
        exclude_titles=["^Zapojte se"],
    )
    assert [row["sourceUrl"] for row in rows] == [
        "https://www.imc.cas.cz/cs/o-ustavu/pracovni-mista/postdoktorandska-pozice-polymery"
    ]


def test_json_links_keep_research_types_only() -> None:
    payload = (
        '{"type":"success","payload":['
        '{"openPositionId":427,"link":"\/en\/open-positions\/427\/postdoc","type":"Scientific position","title":"Postdoctoral fellow in computational chemistry"},'
        '{"openPositionId":430,"link":"\/en\/open-positions\/430\/hr","type":"Other position","title":"HR generalist"}]}'
    )
    source = {"itemsPath": "payload", "idField": "openPositionId", "typeAllow": ["Scientific position"], "linkBase": "https://www.uochb.cz/"}
    rows = harvest.parse_json_links(payload, "https://www.uochb.cz/en/api/open-positions", source)
    assert rows == [{"title": "Postdoctoral fellow in computational chemistry", "sourceUrl": "https://www.uochb.cz/en/open-positions/427/postdoc", "code": "427"}]


def test_anchored_sections_read_each_listed_vacancy() -> None:
    html = (
        '<ul><li><a href="#PhdCompass">Postdoctoral position in COMPASS Upgrade ECRH team</a></li>'
        '<li><a href="#HR">HR asistent*ka</a></li></ul>'
        '<div><b id="PhdCompass">Postdoctoral position in COMPASS Upgrade ECRH team</b></div>'
        "<div>A postdoctoral research position is available. Requirements: PhD in physics. Deadline: 31. 12. 2026. "
        "Send a motivation letter and CV to the institute.</div>"
        '<div><b id="HR">HR asistent*ka</b></div><div>Personnel administration.</div>'
    )
    rows = harvest.parse_anchored_sections(html, "https://www.ipp.cas.cz/o-ufp/volna-mista/")
    assert [(row["code"], row["sourceUrl"]) for row in rows] == [
        ("PhdCompass", "https://www.ipp.cas.cz/o-ufp/volna-mista/#PhdCompass")
    ]
    assert "HR" not in rows[0]["_factText"]


def test_accordion_items_skip_the_archive_and_read_to_the_item_end() -> None:
    html = (
        '<h2>Volná místa</h2><ul class="accordion">'
        '<li class="accordion-item" data-accordion-item><a class="accordion-title"><h3 class="title">Doktorand / doktorandka v archeologii</h3></a>'
        "<div><p>Požadujeme:</p><ul><li>Mgr. v oboru archeologie</li></ul>"
        "<p>Přihlášky zasílejte do 31. 12. 2026 na e-mail ústavu.</p></div></li></ul>"
        '<h2>Archiv inzerátů</h2><ul class="accordion">'
        '<li class="accordion-item archive" data-accordion-item><h3 class="title">Postdoktorand / postdoktorandka</h3><div>Old.</div></li></ul>'
    )
    rows = harvest.parse_accordion_items(html, "https://www.arub.cz/o-nas/volna-mista/")
    assert [row["title"] for row in rows] == ["Doktorand / doktorandka v archeologii"]
    assert rows[0]["closesAt"] == "2026-12-31"

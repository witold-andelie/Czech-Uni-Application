from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from harvest_studyin_programmes import (  # noqa: E402
    HarvestIncomplete,
    harvest_catalog,
    parse_listing_card,
    parse_listing_response,
)


def card(
    item_id: str,
    title: str,
    school: str,
    faculty: str,
    *,
    language: str,
    degree: str,
    forms: str,
) -> str:
    return f"""
    <article class="group/program">
      <h3><a href="/plan-your-studies/universities/school/{item_id}">{title}</a></h3>
      <form><input name="itemId" value="{item_id}" /></form>
      <p class="font-semibold">{school} ({faculty})</p>
      <a href="https://www.google.com/maps/search/?query=1,2"><span class="sr-only">Opens in a new window</span>Praha</a>
      <ul>
        <li><span role="tooltip">Study type</span><span class="icon"></span>{degree}</li>
        <li><span role="tooltip">Study form:</span><span class="icon"></span>{forms}</li>
        <li><span role="tooltip">Specialization</span><span class="icon"></span>Computer science</li>
        <li><span role="tooltip">Study language:</span><span class="icon"></span>{language}</li>
        <li><span role="tooltip">Study duration</span><span class="icon"></span>3 years</li>
        <li><span role="tooltip">Credits</span><span class="icon"></span>180 credits</li>
        <li><span role="tooltip">Study fee</span><span class="icon"></span>2,500.00 EUR</li>
      </ul>
    </article>
    """


def response(total: int, cards: list[str], locale: str = "en") -> str:
    label = "Results found" if locale == "en" else "Nalezeno výsledků"
    content = f"<p>{label}: <span>{total}</span></p>" + "".join(cards)
    return json.dumps(
        {
            "version": 1,
            "data": [
                {"content": content, "targetBlock": "#programSearchListContainer", "type": "html"}
            ],
        }
    )


def test_listing_parser_keeps_official_uuid_and_study_form_variants() -> None:
    html = card(
        "11111111-1111-1111-1111-111111111111",
        "Computer Science",
        "Univerzita Test",
        "Fakulta informatiky",
        language="English",
        degree="Bachelor study programme",
        forms="full-time, combined",
    )
    row = parse_listing_card(html, "en")
    assert row["id"] == "11111111-1111-1111-1111-111111111111"
    assert row["studyForms"] == ["full-time", "combined"]
    assert row["studyLanguage"] == "en"
    assert row["degree"] == "b"
    assert row["durationYears"] == 3
    assert row["credits"] == 180
    assert row["tuition"] == {"amount": 2500.0, "currency": "EUR", "period": "unknown"}
    assert row["facultyName"] == "Fakulta informatiky"


def test_response_requires_result_count() -> None:
    payload = json.dumps(
        {"data": [{"content": "<p>no count</p>", "targetBlock": "#programSearchListContainer"}]}
    )
    try:
        parse_listing_response(payload, "en")
    except HarvestIncomplete as exc:
        assert "result count" in str(exc)
    else:
        raise AssertionError("missing count must fail")


def test_full_and_open_catalogues_are_joined_by_uuid() -> None:
    ids = [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]
    english = {
        ids[0]: card(ids[0], "Computer Science", "Test University", "Faculty of Informatics", language="English", degree="Bachelor study programme", forms="full-time"),
        ids[1]: card(ids[1], "Computer Science", "Test University", "Faculty of Informatics", language="English", degree="Bachelor study programme", forms="combined"),
    }
    czech = {
        ids[0]: card(ids[0], "Informatika", "Univerzita Test", "Fakulta informatiky", language="angličtina", degree="bakalářský studijní program", forms="prezenční"),
        ids[1]: card(ids[1], "Informatika", "Univerzita Test", "Fakulta informatiky", language="angličtina", degree="bakalářský studijní program", forms="kombinované"),
    }

    def fetch(url: str) -> tuple[int, str]:
        query = parse_qs(urlparse(url).query)
        locale = query["language"][0]
        page = int(query["page"][0])
        only_open = query.get("openApplicationsOnly") == ["true"]
        if only_open:
            return 200, response(1, [english[ids[1]]], "en")
        rows = english if locale == "en" else czech
        return 200, response(2, [rows[ids[page - 1]]], locale)

    payload = harvest_catalog(
        fetch,
        institutions=[{"id": "msmt-vs_test", "officialName": "Univerzita Test"}],
        page_size=1,
        delay_seconds=0,
    )
    assert payload["counts"] == {
        "programmes": 2,
        "openApplications": 1,
        "institutions": 1,
        "unmappedProgrammes": 0,
    }
    assert [item["directoryReportsApplicationsOpen"] for item in payload["programmes"]] == [False, True]
    assert [item["applicationStatus"] for item in payload["programmes"]] == ["not_reported_open", "directory_open"]
    assert payload["programmes"][0]["studyForms"]["en"] == ["full-time"]
    assert payload["programmes"][1]["studyForms"]["en"] == ["combined"]


def test_partial_page_is_rejected() -> None:
    one = card(
        "11111111-1111-1111-1111-111111111111",
        "Computer Science",
        "Test University",
        "Faculty",
        language="English",
        degree="Bachelor study programme",
        forms="full-time",
    )

    def fetch(_url: str) -> tuple[int, str]:
        return 200, response(2, [one], "en")

    try:
        harvest_catalog(fetch, institutions=[], page_size=2, delay_seconds=0)
    except HarvestIncomplete as exc:
        assert "partial" in str(exc)
    else:
        raise AssertionError("partial catalogue must fail")


def test_repeated_first_page_is_rejected_as_duplicate() -> None:
    one = card(
        "11111111-1111-1111-1111-111111111111",
        "Computer Science",
        "Test University",
        "Faculty",
        language="English",
        degree="Bachelor study programme",
        forms="full-time",
    )

    def fetch(_url: str) -> tuple[int, str]:
        return 200, response(2, [one], "en")

    try:
        harvest_catalog(fetch, institutions=[], page_size=1, delay_seconds=0)
    except HarvestIncomplete as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("repeated first page must fail")

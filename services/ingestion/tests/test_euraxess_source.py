from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import auto_review  # noqa: E402
import euraxess_source as eu  # noqa: E402


def test_search_rows_pages_and_detail_fields() -> None:
    html = (
        '<p>Search results (23) Showing results 1 to 10</p>'
        '<article><h3><a href="/jobs/470018"><span>Research Assistant in Biochemistry (M/F)</span></a></h3></article>'
        '<article><h3><a href="/jobs/469956"><span>Project Researcher I</span></a></h3></article>'
    )
    first = "https://euraxess.ec.europa.eu/jobs/search?f%5B0%5D=job_country%3A747"
    rows = eu.parse_search(html, first)
    assert [row["code"] for row in rows] == ["eu470018", "eu469956"]
    assert rows[0]["sourceUrl"] == "https://euraxess.ec.europa.eu/jobs/470018"
    assert eu.page_urls(html, first) == [f"{first}&page=1", f"{first}&page=2"]
    text = ("Job Information Organisation/Company Charles University, Faculty of Science Research Field Chemistry "
            "Where to apply Website https://natur.cuni.cz/en/x E-mail volnamista@natur.cuni.cz Requirements")
    assert eu.detail_fields(text) == {
        "organisation": "Charles University, Faculty of Science",
        "website": "https://natur.cuni.cz/en/x",
        "email": "volnamista@natur.cuni.cz",
    }


def test_employers_resolve_to_universities_only() -> None:
    assert eu.resolve_employer("Charles University, Faculty of Science") == "msmt-vs_11000"
    assert eu.resolve_employer("CEITEC MU") == "msmt-vs_14000"
    assert eu.resolve_employer("VSCHT Praha") == "msmt-vs_22000"
    assert eu.resolve_employer("Czech Technical University in Prague") == "msmt-vs_21000"
    assert eu.resolve_employer("Institute of Physics of the Czech Academy of Sciences") is None
    assert eu.resolve_employer("Faculty of Electrical Engineering") is None


def test_application_target_is_on_the_employers_own_domain() -> None:
    html = ('<a href="https://www.resaver.eu/">x</a><a href="https://euraxess.ec.europa.eu/jobs/1">y</a>'
            '<a href="https://natur.cuni.cz/en/faculty/official-board/selection-procedures">z</a>')
    assert eu.official_application_url(html, "", None, {"cuni.cz"}) == (
        "https://natur.cuni.cz/en/faculty/official-board/selection-procedures")
    assert eu.official_application_url('<a href="https://jobrxiv.org/job/1">j</a>', "", "https://jobrxiv.org/job/1", {"cuni.cz"}) is None


def test_euraxess_records_need_an_official_target_and_are_not_published_twice() -> None:
    base = {
        "id": "job-11000-eu1", "employerId": "msmt-vs_11000", "discoverySourceId": "euraxess-cz-jobs",
        "originalText": "Research Assistant in Biochemistry (M/F)", "track": "assistant",
        "catalogueScopeStatus": "included", "lifecycleStatus": "unknown", "sourceHash": "sha256:" + "c" * 64,
        "sourceUrl": "https://euraxess.ec.europa.eu/jobs/470018",
    }
    direct = {"id": "job-11000-direct", "employerId": "msmt-vs_11000", "originalText": "Research Assistant in Biochemistry (M/F)"}
    blockers = auto_review.gate_blockers({**base, "applicationUrl": base["sourceUrl"]}, [], date(2026, 10, 3), [direct])
    assert "no-official-application-target" in blockers
    assert "duplicate-of-direct-source:job-11000-direct" in blockers
    other = {"id": "job-11000-other", "employerId": "msmt-vs_11000", "originalText": "Head of the Department of Law"}
    assert auto_review.gate_blockers(
        {**base, "applicationUrl": "https://natur.cuni.cz/x"}, [], date(2026, 10, 3), [other]) == []

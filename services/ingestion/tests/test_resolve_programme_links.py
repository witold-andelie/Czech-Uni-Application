from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import resolve_programme_links as rpl  # noqa: E402


def row(institution_id: str, title: str, degree: str, language: str, faculty: str = "Fakulta") -> rpl.Row:
    return rpl.Row(
        ident=rpl.row_id(institution_id, title, "bachelor" if degree == "b" else "master", language, faculty),
        institution_id=institution_id,
        title=title,
        degree=degree,
        language=language,
        faculty=faculty,
    )


def candidate(url: str, title: str, degree: str, language: str, matched_by: str = "school_catalogue_anchor") -> rpl.Candidate:
    return rpl.Candidate(
        url=url,
        title=title,
        degree=degree,
        language=language,
        source_url="https://school.cz/programmes",
        matched_by=matched_by,
        observed_at="2026-09-27T00:00:00Z",
    )


def school_target(domain: str = "school.cz") -> dict:
    return {
        "id": "msmt-vs_00000",
        "name": "Test School",
        "officialUrl": f"https://www.{domain}",
        "entryUrls": [],
        # Any subdomain of a domain the school owns may be read.
        "allowedDomains": [domain],
    }


class FakeFetch:
    """A site that answers only what the test states.

    ``default`` models the rest of the school's own site: discovery tests use an
    empty page so a follow-up catalogue hop succeeds without inventing content.
    """

    def __init__(self, responses: dict[str, tuple[int, str]], default: tuple[int, str] = (404, "")):
        self.responses = responses
        self.calls: list[str] = []
        self.default = default

    def __call__(self, url: str) -> tuple[int, str]:
        self.calls.append(url)
        return self.responses.get(url, self.default)


def test_normalise_is_conservative() -> None:
    assert rpl.normalise("Česká zemědělská") == rpl.normalise("ceska zemedelska")
    assert rpl.normalise("Agriculture-and-Food") == rpl.normalise("Agriculture and food")
    # Curly apostrophes collapse to word boundaries, the same way the browser's
    # foldKey() collapses them, so a title and its slug variant share one key.
    assert rpl.normalise("ČZU’s  Programme") == "czu s programme"


def test_the_schools_own_programme_code_is_not_part_of_the_name() -> None:
    """A code beside the name names the school's record, not the programme.

    BUT's catalogue writes "Architektura a urbanismus (N_A+U)" where the MšMT
    register row is "Architektura a urbanismus", so 147 of its 199 rows had no
    candidate page while the school already published one for each. Only a
    parenthetical shaped like a code is removed: a number in parentheses is the
    page's own id, and a parenthetical the register itself carries stays.
    """
    assert rpl.stated_title("Architektura a urbanismus (N_A+U)") == "architektura a urbanismus"
    assert rpl.stated_title("Studijní program - Sportovní technologie (9937) – VUT") == rpl.normalise(
        "Studijní program - Sportovní technologie (9937) – VUT"
    )
    # A parenthetical that is not code-shaped is part of the name.
    assert rpl.stated_title("Chemie (obor Učitelství)") == "chemie obor ucitelstvi"
    assert rpl.stated_title("Kynologie") == "kynologie"
    assert rpl.stated_title("Architektura a urbanismus (N_A+U)") != rpl.normalise("Architektura a urbanismus (N_A+U)")


def test_a_code_beside_the_name_binds_the_register_row() -> None:
    """The anchor's name binds normally - on its own, not on the code."""
    target = school_target("www.school.cz")
    target["entryUrls"] = ["https://www.school.cz/studenti/programy"]
    rows = [
        row("msmt-vs_00000", "Architektura a urbanismus", "m", "cs"),
        row("msmt-vs_00000", "Architektura a rozvoj sídel", "m", "cs"),
    ]
    listing = (
        "<html><body><ul>"
        '<li><a href="/studenti/programy/program/9714">Architektura a urbanismus (N_A+U)</a></li>'
        '<li><a href="/studenti/programy/program/9751">Architektura a rozvoj sídel (NPC-ARS)</a></li>'
        "</ul></body></html>"
    )
    fetch = FakeFetch({"https://www.school.cz/studenti/programy": (200, listing)})
    match = rpl.Match(rows)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    links, unresolved, _multiple, notes = rpl.resolve_school(
        target, match, [], throttled, rpl.Limits(), rpl.Budget(60), live=True
    )
    assert notes == []
    assert links[rows[0].ident].url == "https://www.school.cz/studenti/programy/program/9714"
    assert links[rows[0].ident].matched_title == "architektura a urbanismus"
    assert links[rows[1].ident].url == "https://www.school.cz/studenti/programy/program/9751"
    assert unresolved == {}


def test_a_code_never_takes_the_place_of_a_name_the_register_holds() -> None:
    """Stripping a code must not open a row the anchor did not name."""
    target = school_target("www.school.cz")
    target["entryUrls"] = ["https://www.school.cz/studenti/programy"]
    rows = [row("msmt-vs_00000", "Architektura", "b", "cs")]
    listing = (
        "<html><body><ul>"
        '<li><a href="/studenti/programy/program/9714">Architektura a urbanismus (N_A+U)</a></li>'
        "</ul></body></html>"
    )
    fetch = FakeFetch({"https://www.school.cz/studenti/programy": (200, listing)})
    match = rpl.Match(rows)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    links, unresolved, _multiple, _notes = rpl.resolve_school(
        target, match, [], throttled, rpl.Limits(), rpl.Budget(60), live=True
    )
    assert links == {}
    assert unresolved == {rows[0].ident: "no_candidate_page"}


def test_registrable_host_allows_school_subdomains() -> None:
    assert rpl.registrable_host("https://study.czu.cz/programmes/x/") == "czu.cz"
    assert rpl.registrable_host("https://studuj.czu.cz") == "czu.cz"
    assert rpl.registrable_host("https://www.cuni.cz") == "cuni.cz"
    assert rpl.registrable_host("damu.cz") == "damu.cz"
    assert rpl.registrable_host("www.umprum.cz") == "umprum.cz"


def test_school_domains_include_configured_extra_hosts() -> None:
    domains = rpl.school_domains(
        {"id": "msmt-vs_51000", "officialUrl": "https://www.amu.cz", "webHost": "www.amu.cz"},
        {"extraDomains": ["damu.cz", "famu.cz", "hamu.cz"]},
    )
    assert domains == {"amu.cz", "damu.cz", "famu.cz", "hamu.cz"}


def test_exact_match_binds_only_an_equal_title_and_degree() -> None:
    match = rpl.Match([row("msmt-vs_1", "Kynologie", "b", "cs"), row("msmt-vs_1", "Kynologie", "m", "cs")])
    bound = match.bind(candidate("https://school.cz/p/kynologie/", "Kynologie", "b", "cs"))
    assert not bound.reason
    assert [item.degree for item in bound.rows] == ["b"]

    other_degree = match.bind(candidate("https://school.cz/p/kynologie-m/", "Kynologie", "m", "cs"))
    assert [item.degree for item in other_degree.rows] == ["m"]


def test_the_level_a_page_states_is_the_only_one_used() -> None:
    assert rpl.degree_stated("Kynologie (Bc.)") == "b"
    assert rpl.degree_stated("Kynologie - master") == "m"
    assert rpl.degree_stated("Doctoral study", "https://school.cz/phd/kynologie") == "d"
    assert rpl.degree_stated("Kynologie") == rpl.UNKNOWN_DEGREE
    assert rpl.degree_stated("Kynologie", "https://school.cz/obory/kynologie") == rpl.UNKNOWN_DEGREE
    # Two levels in one link name nothing decided: the level stays unstated.
    assert rpl.degree_stated("Bachelor and master programmes") == rpl.UNKNOWN_DEGREE


def test_an_unstated_level_binds_only_a_title_that_names_one_row() -> None:
    """A catalogue anchor rarely states the level next to the programme name."""
    unique = rpl.Match([row("msmt-vs_1", "Zahradnictví", "b", "cs")])
    bound = unique.bind(candidate("https://school.cz/p/zahradnictvi/", "Zahradnictví", rpl.UNKNOWN_DEGREE, ""))
    assert not bound.reason
    assert [item.degree for item in bound.rows] == ["b"]

    # The same title at two levels cannot be attributed to one of them, so both
    # keep the university-site fallback.
    shared = rpl.Match([row("msmt-vs_1", "Zahradnictví", "b", "cs"), row("msmt-vs_1", "Zahradnictví", "m", "cs")])
    binding = shared.bind(candidate("https://school.cz/p/zahradnictvi/", "Zahradnictví", rpl.UNKNOWN_DEGREE, ""))
    assert binding.reason == "ambiguous_register_rows"
    assert len(binding.rows) == 2


def test_partial_title_never_matches() -> None:
    """A shorter name must not take over a longer programme's page."""
    match = rpl.Match([row("msmt-vs_1", "Chemie se zaměřením na vzdělávání", "b", "cs")])
    assert not match.bind(candidate("https://school.cz/p/chemie/", "Chemie", "b", "cs")).rows
    exact = match.bind(candidate("https://school.cz/p/chemie-vzdelavani/", "Chemie se zaměřením na vzdělávání", "b", "cs"))
    assert not exact.reason
    assert len(exact.rows) == 1


def test_cross_language_candidate_needs_a_unique_row() -> None:
    """A Czech-named page may serve an English-taught programme."""
    unique = rpl.Match([row("msmt-vs_1", "Zahradnictví", "b", "cs")])
    bound = unique.bind(candidate("https://school.cz/p/zahradnictvi/", "Zahradnictví", "b", "en"))
    assert not bound.reason
    assert bound.rows[0].language == "cs"

    # Two faculties both carry this title and degree: the page cannot be
    # attributed to one of them, so both keep the university-site fallback.
    shared = [
        row("msmt-vs_1", "Zahradnictví", "b", "cs", "Fakulta 1"),
        row("msmt-vs_1", "Zahradnictví", "b", "cs", "Fakulta 2"),
    ]
    ambiguous = rpl.Match(shared)
    binding = ambiguous.bind(candidate("https://school.cz/p/zahradnictvi/", "Zahradnictví", "b", "cs"))
    assert binding.reason == "ambiguous_register_rows"
    assert len(binding.rows) == 2


def test_verify_links_drops_404_and_keeps_access_control() -> None:
    links = {
        "inv-a": rpl.Link(
            url="https://school.cz/p/a/",
            row_id="inv-a",
            institution_id="msmt-vs_1",
            degree="b",
            language="cs",
            matched_title="A",
            row_title="A",
            source_url="https://school.cz/programmes",
            matched_by="school_catalogue_anchor",
            reachability="unverified",
            matched_at="2026-09-27T00:00:00Z",
        ),
        "inv-b": rpl.Link(
            url="https://school.cz/p/b/",
            row_id="inv-b",
            institution_id="msmt-vs_1",
            degree="b",
            language="cs",
            matched_title="B",
            row_title="B",
            source_url="https://school.cz/programmes",
            matched_by="school_catalogue_anchor",
            reachability="unverified",
            matched_at="2026-09-27T00:00:00Z",
        ),
    }
    fetch = FakeFetch(
        {
            "https://school.cz/p/a/": (404, ""),
            "https://school.cz/p/b/": (403, "<html>denied</html>"),
        }
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    outcomes = rpl.verify_links(links, throttled, rpl.Limits(), rpl.Budget(60))
    assert outcomes["https://school.cz/p/a/"] == "dropped_404"
    # 403 is not evidence the page is gone.
    assert outcomes["https://school.cz/p/b/"] == "unverified_access_control"
    assert links["inv-b"].reachability == "access_control"


def test_verify_links_drops_a_page_that_states_another_level() -> None:
    """The name matches exactly; the page's own words say it is the other one."""
    link = rpl.Link(
        url="https://school.cz/p/kynologie/",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="b",
        language="cs",
        matched_title="Kynologie",
        row_title="Kynologie",
        source_url="https://school.cz/programmes",
        matched_by="school_catalogue_anchor",
        reachability="unverified",
        matched_at="2026-09-27T00:00:00Z",
    )
    fetch = FakeFetch(
        {
            "https://school.cz/p/kynologie/": (
                200,
                "<html><head><title>Kynologie – magisterské studium | school</title></head>"
                "<body><h1>Kynologie – magisterské studium</h1></body></html>",
            )
        }
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    outcomes = rpl.verify_links({"inv-a": link}, throttled, rpl.Limits(), rpl.Budget(60))
    assert outcomes["https://school.cz/p/kynologie/"] == "dropped_level_mismatch"
    assert rpl.DROP_REASONS["dropped_level_mismatch"] == "page_states_another_level"


def test_a_schools_redirect_stub_is_not_the_programme_page() -> None:
    """The school answers with an empty document that names nothing.

    The catalogue link named the register row exactly, and the page it points at
    opens 200 - so the binding was sound when it was made. The page itself is a
    meta-refresh stub, and the programme it means takes a second read this
    resolver never makes, so a visitor would land on an empty document. The link
    is dropped and the row goes back to the university site.
    """
    link = rpl.Link(
        url="https://is.school.cz/program/1484/pediatrie/",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="b",
        language="cs",
        matched_title="Pediatrie",
        row_title="Pediatrie",
        source_url="https://school.cz/programmes",
        matched_by="school_catalogue_anchor",
        reachability="unverified",
        matched_at="2026-09-27T00:00:00Z",
    )
    stub = "<!DOCTYPE HTML>\n<html>\n<head>\n<title></title>\n" '<meta http-equiv="refresh" content="1">\n</head>\n<body>\n</body>\n</html>\n'
    throttled = rpl.ThrottledFetch(
        FakeFetch({"https://is.school.cz/program/1484/pediatrie/": (200, stub)}),
        sleep=lambda _seconds: None,
    )
    outcomes = rpl.verify_links({"inv-a": link}, throttled, rpl.Limits(), rpl.Budget(60))
    assert outcomes["https://is.school.cz/program/1484/pediatrie/"] == "dropped_stub_page"
    assert rpl.DROP_REASONS["dropped_stub_page"] == "page_states_nothing"


def test_an_empty_answer_is_not_evidence_against_a_page() -> None:
    """A body that never arrived says nothing, so the link is kept unverified.

    Dropping on an empty answer would let one failed read remove a link the
    school still publishes, which is the same mistake as reading a timeout as a
    closure.
    """
    link = rpl.Link(
        url="https://school.cz/p/kynologie/",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="b",
        language="cs",
        matched_title="Kynologie",
        row_title="Kynologie",
        source_url="https://school.cz/programmes",
        matched_by="school_catalogue_anchor",
        reachability="unverified",
        matched_at="2026-09-27T00:00:00Z",
    )
    throttled = rpl.ThrottledFetch(
        FakeFetch({"https://school.cz/p/kynologie/": (200, "")}), sleep=lambda _seconds: None
    )
    outcomes = rpl.verify_links({"inv-a": link}, throttled, rpl.Limits(), rpl.Budget(60))
    assert outcomes["https://school.cz/p/kynologie/"] == "http_200_title_not_confirmed"


def test_a_page_that_states_no_level_is_kept() -> None:
    link = rpl.Link(
        url="https://school.cz/p/kynologie/",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="b",
        language="cs",
        matched_title="Kynologie",
        row_title="Kynologie",
        source_url="https://school.cz/programmes",
        matched_by="school_catalogue_anchor",
        reachability="unverified",
        matched_at="2026-09-27T00:00:00Z",
    )
    body = (
        "<html><head><title>Kynologie | Fakulta</title></head>"
        "<body><h1>Kynologie</h1></body></html>"
    )
    throttled = rpl.ThrottledFetch(
        FakeFetch({"https://school.cz/p/kynologie/": (200, body)}), sleep=lambda _seconds: None
    )
    outcomes = rpl.verify_links({"inv-a": link}, throttled, rpl.Limits(), rpl.Budget(60))
    assert outcomes["https://school.cz/p/kynologie/"] == "verified"


def test_a_large_document_without_headings_is_not_a_stub() -> None:
    """A study-plan attachment is kilobytes of document and states nothing read.

    Size is what separates a stub from a document the heading rules cannot read:
    an attachment is not dropped, because it is still the school's own file for
    the programme.
    """
    link = rpl.Link(
        url="https://school.cz/plany/PZ.docx",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="m",
        language="cs",
        matched_title="Kynologie",
        row_title="Kynologie",
        source_url="https://school.cz/programmes",
        matched_by="school_catalogue_anchor",
        reachability="unverified",
        matched_at="2026-09-27T00:00:00Z",
    )
    throttled = rpl.ThrottledFetch(
        FakeFetch({"https://school.cz/plany/PZ.docx": (200, "PK".join(["x" * 50_000]))}),
        sleep=lambda _seconds: None,
    )
    outcomes = rpl.verify_links({"inv-a": link}, throttled, rpl.Limits(), rpl.Budget(60))
    assert outcomes["https://school.cz/plany/PZ.docx"] == "http_200_title_not_confirmed"


def test_the_level_probe_separates_a_title_the_register_holds_twice() -> None:
    """A catalogue link names no level; the page it points at does."""
    match = rpl.Match(
        [row("msmt-vs_1", "Zahradnictví", "b", "cs"), row("msmt-vs_1", "Zahradnictví", "m", "cs")]
    )
    unresolved = {
        row.ident: "ambiguous_register_rows" for row in match.rows
    }
    candidate = rpl.Candidate(
        url="https://school.cz/p/zahradnictvi/",
        title="Zahradnictví",
        degree=rpl.UNKNOWN_DEGREE,
        language="",
        source_url="https://school.cz/programmes",
        matched_by="school_catalogue_anchor",
        observed_at="2026-09-27T00:00:00Z",
    )
    body = (
        "<html><head><title>Zahradnictví – bakalářské studium | school</title></head>"
        "<body><h1>Zahradnictví – bakalářské studium</h1></body></html>"
    )
    throttled = rpl.ThrottledFetch(
        FakeFetch({"https://school.cz/p/zahradnictvi/": (200, body)}), sleep=lambda _seconds: None
    )
    probed, notes = rpl.probe_levels(
        match,
        unresolved,
        {rpl.normalise("Zahradnictví"): [candidate]},
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
    )
    assert notes == []
    assert [item[0].url for item in probed[match.rows[0].ident]] == [candidate.url]
    assert match.rows[1].ident not in probed
    assert match.rows[1].ident in unresolved


def test_the_level_probe_reads_nothing_when_no_page_states_a_level() -> None:
    match = rpl.Match(
        [row("msmt-vs_1", "Zahradnictví", "b", "cs"), row("msmt-vs_1", "Zahradnictví", "m", "cs")]
    )
    unresolved = {row.ident: "ambiguous_register_rows" for row in match.rows}
    candidate = rpl.Candidate(
        url="https://school.cz/p/zahradnictvi/",
        title="Zahradnictví",
        degree=rpl.UNKNOWN_DEGREE,
        language="",
        source_url="https://school.cz/programmes",
        matched_by="school_catalogue_anchor",
        observed_at="2026-09-27T00:00:00Z",
    )
    body = (
        "<html><head><title>Bakalářské a magisterské studium | school</title></head>"
        "<body><h1>Zahradnictví</h1></body></html>"
    )
    throttled = rpl.ThrottledFetch(
        FakeFetch({"https://school.cz/p/zahradnictvi/": (200, body)}), sleep=lambda _seconds: None
    )
    probed, _notes = rpl.probe_levels(
        match,
        unresolved,
        {rpl.normalise("Zahradnictví"): [candidate]},
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
    )
    assert probed == {}
    assert unresolved == {row.ident: "ambiguous_register_rows" for row in match.rows}


def test_the_awarded_title_field_states_the_level_the_title_line_omits() -> None:
    """Mendel University titles a programme by name and states its level in a field."""
    match = rpl.Match(
        [row("msmt-vs_1", "Krajinné inženýrství", "b", "cs"), row("msmt-vs_1", "Krajinné inženýrství", "m", "cs")]
    )
    unresolved = {row.ident: "ambiguous_register_rows" for row in match.rows}
    page = candidate("https://www.school.cz/studijni-programy/krajinne-inzenyrstvi/", "Krajinné inženýrství", "u", "")
    body = (
        "<html><head><title>Krajinné inženýrství - MENDELU</title></head><body>"
        "<h1>Krajinné inženýrství</h1>"
        "<div class='info-row'><span class='label'>Titul:</span> Magisterský (Ing.)</div>"
        "<div class='info-row'><span class='label'>Fakulta:</span> Zahradnická fakulta</div>"
        "</body></html>"
    )
    throttled = rpl.ThrottledFetch(
        FakeFetch({page.url: (200, body)}), sleep=lambda _seconds: None
    )
    probed, notes = rpl.probe_levels(
        match,
        unresolved,
        {rpl.normalise("Krajinné inženýrství"): [page]},
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
    )
    assert notes == []
    assert [item[0].url for item in probed[match.rows[1].ident]] == [page.url]
    assert match.rows[0].ident not in probed
    assert match.rows[0].ident in unresolved


def test_prose_about_the_other_level_decides_nothing() -> None:
    """Admissions prose names both levels; only a field or the title line decides."""
    match = rpl.Match(
        [row("msmt-vs_1", "Krajinné inženýrství", "b", "cs"), row("msmt-vs_1", "Krajinné inženýrství", "m", "cs")]
    )
    unresolved = {row.ident: "ambiguous_register_rows" for row in match.rows}
    page = candidate("https://www.school.cz/studijni-programy/krajinne-inzenyrstvi/", "Krajinné inženýrství", "u", "")
    body = (
        "<html><head><title>Krajinné inženýrství - MENDELU</title></head><body><h1>Krajinné inženýrství</h1>"
        "<p>Uchazeči budou do navazujícího magisterského studia přijati na základě vykonání "
        "příjímací zkoušky z předmětů státní závěrečné zkoušky bakalářského studijního programu.</p>"
        "</body></html>"
    )
    throttled = rpl.ThrottledFetch(
        FakeFetch({page.url: (200, body)}), sleep=lambda _seconds: None
    )
    probed, _notes = rpl.probe_levels(
        match,
        unresolved,
        {rpl.normalise("Krajinné inženýrství"): [page]},
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
    )
    assert probed == {}
    assert unresolved == {row.ident: "ambiguous_register_rows" for row in match.rows}


def test_two_stated_levels_on_one_page_decide_nothing() -> None:
    """A page listing other programmes' degrees must not bind a row to one of them."""
    match = rpl.Match(
        [row("msmt-vs_1", "Lesní inženýrství", "b", "cs"), row("msmt-vs_1", "Lesní inženýrství", "m", "cs")]
    )
    unresolved = {row.ident: "ambiguous_register_rows" for row in match.rows}
    page = candidate("https://www.school.cz/studijni-programy/lesni-inzenyrstvi/", "Lesní inženýrství", "u", "")
    body = (
        "<html><head><title>Lesní inženýrství - MENDELU</title></head><body><h1>Lesní inženýrství</h1>"
        "<div class='info-row'><span class='label'>Titul:</span> Magisterský (Ing.)</div>"
        "<aside><h3>Související programy</h3>"
        "<p>Lesní inženýrství - specializace Lovectví a myslivost</p>"
        "<p><span class='label'>Titul:</span> Bakalářský (Bc.)</p></aside>"
        "</body></html>"
    )
    throttled = rpl.ThrottledFetch(
        FakeFetch({page.url: (200, body)}), sleep=lambda _seconds: None
    )
    probed, _notes = rpl.probe_levels(
        match,
        unresolved,
        {rpl.normalise("Lesní inženýrství"): [page]},
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
    )
    assert probed == {}
    assert unresolved == {row.ident: "ambiguous_register_rows" for row in match.rows}



    payload = rpl.build_links(
        fetch=None,
        now=datetime(2026, 9, 27, tzinfo=timezone.utc),
        config={"harvestedSources": [], "schools": []},
        institutions=[{"id": "msmt-vs_1", "officialName": "Test School", "officialUrl": "https://www.school.cz"}],
        rows_by_institution={"msmt-vs_1": [row("msmt-vs_1", "Kynologie", "b", "cs")]},
    )
    assert payload["links"] == {}
    assert payload["counts"]["linked"] == 0
    assert [item["reason"] for item in payload["unresolved"]] == ["no_candidate_page"]
    assert payload["coverage"]["schools"][0]["unresolved"] == 1


def test_link_outside_the_school_domain_is_rejected(tmp_path: Path) -> None:
    """A one-school run must not point rows at another organisation's page."""
    harvest = tmp_path / "foreign.json"
    harvest.write_text(
        json.dumps(
            {
                "programmes": [
                    {
                        "degree": "b",
                        "studyLanguage": "cs",
                        "titles": {"cs": "Kynologie"},
                        "url": "https://other.example.org/programmes/kynologie/",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload = rpl.build_links(
        fetch=None,
        now=datetime(2026, 9, 27, tzinfo=timezone.utc),
        config={
            "harvestedSources": [{"path": str(harvest), "urlField": "url"}],
            "schools": [],
        },
        institutions=[{"id": "msmt-vs_1", "officialName": "Test School", "officialUrl": "https://www.school.cz"}],
        rows_by_institution={"msmt-vs_1": [row("msmt-vs_1", "Kynologie", "b", "cs")]},
    )
    assert payload["counts"]["linked"] == 0
    assert [item["reason"] for item in payload["unresolved"]] == ["no_candidate_page"]


def test_discovery_only_reads_links_from_the_school_domain() -> None:
    target = school_target()
    homepage = """
    <html><body>
      <a href="/en/programmes/">Programmes</a>
      <a href="https://ads.example.com/x/">Partner</a>
    </body></html>
    """
    catalogue = """
    <html><body>
      <a href="/en/programmes/kynologie/">Kynologie</a>
      <a href="https://other.cz/programmes/kynologie/">Kynologie elsewhere</a>
      <a href="mailto:info@school.cz">Mail</a>
    </body></html>
    """
    fetch = FakeFetch(
        {
            # catalogue_entries() normalises entries without a trailing slash.
            "https://www.school.cz": (200, homepage),
            "https://www.school.cz/en/programmes": (200, catalogue),
        },
        default=(200, "<html><body></body></html>"),
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    candidates, notes = rpl.discover_candidates(target, throttled, rpl.Limits(), rpl.Budget(60))
    assert [item.url for item in candidates] == ["https://www.school.cz/en/programmes/kynologie/"]
    assert notes == []


def test_discovery_reads_the_schools_own_subdomains() -> None:
    """A faculty names its programmes on its own subdomain (is.muni.cz, ...).

    Only a domain the school owns is read, so widening to subdomains never
    reaches another organisation; the exact title match still decides whether a
    page belongs to a register row.
    """
    target = school_target()
    homepage = """
    <html><body>
      <a href="/en/programmes/">Programmes</a>
    </body></html>
    """
    catalogue = """
    <html><body>
      <a href="https://fi.school.cz/en/programmes/kynologie/">Kynologie</a>
      <a href="https://unrelated.cz/en/programmes/kynologie/">Kynologie elsewhere</a>
    </body></html>
    """
    fetch = FakeFetch(
        {
            "https://www.school.cz": (200, homepage),
            "https://www.school.cz/en/programmes": (200, catalogue),
        },
        default=(200, "<html><body></body></html>"),
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    candidates, notes = rpl.discover_candidates(target, throttled, rpl.Limits(), rpl.Budget(60))
    assert [item.url for item in candidates] == ["https://fi.school.cz/en/programmes/kynologie/"]
    assert notes == []


def test_catalogue_walk_takes_one_hop_past_the_first_catalogue() -> None:
    """A homepage links to a catalogue, the catalogue to a faculty.

    Real faculties rarely name their programmes on the first catalogue page, so
    the walk reads one further level of catalogue pages. A catalogue page is a
    candidate source like any other - the exact-match rule in ``resolve_school``
    discards it when no register title equals it - and each page is read at most
    once per school.
    """
    target = school_target()
    homepage = """
    <html><body>
      <a href="/en/programmes/">Study programmes</a>
    </body></html>
    """
    catalogue = """
    <html><body>
      <a href="/en/faculty-of-ecology/programmes/">Faculty programme catalogue</a>
    </body></html>
    """
    faculty = """
    <html><body>
      <a href="/en/programmes/kynologie/">Kynologie</a>
    </body></html>
    """
    fetch = FakeFetch(
        {
            "https://www.school.cz": (200, homepage),
            "https://www.school.cz/en/programmes": (200, catalogue),
            "https://www.school.cz/en/faculty-of-ecology/programmes": (200, faculty),
        },
        default=(200, "<html><body></body></html>"),
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    candidates, notes = rpl.discover_candidates(target, throttled, rpl.Limits(), rpl.Budget(60))
    assert "https://www.school.cz/en/programmes/kynologie/" in [item.url for item in candidates]
    assert notes == []
    # Every page is read once: the faculty page is not fetched twice, and neither
    # is the programme page it names.
    assert fetch.calls.count("https://www.school.cz/en/faculty-of-ecology/programmes") == 1
    assert fetch.calls.count("https://www.school.cz/en/programmes/kynologie") <= 1

    match = rpl.Match([row("msmt-vs_00000", "Kynologie", "b", "cs")])
    links, unresolved, multiple, _notes = rpl.resolve_school(
        target, match, candidates, throttled, rpl.Limits(), rpl.Budget(60), live=False
    )
    assert links[match.rows[0].ident].url == "https://www.school.cz/en/programmes/kynologie/"
    assert unresolved == {}


def test_catalogue_walk_stays_bounded_per_school() -> None:
    target = school_target()
    anchors = "\n".join(
        f'<a href="/catalogue/{index}/">Programme catalogue {index}</a>' for index in range(40)
    )
    links = anchors.join(("\n", "\n"))
    page = f"<html><body>{links}</body></html>"
    fetch = FakeFetch(
        {
            # catalogue_entries() normalises entries without a trailing slash.
            f"https://www.school.cz/catalogue/{index}": (200, page)
            for index in range(40)
        }
    )
    fetch.responses["https://www.school.cz"] = (200, page)
    limits = rpl.Limits(max_catalogue_entries=5)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    candidates, _notes = rpl.discover_candidates(target, throttled, limits, rpl.Budget(600))
    catalogue_calls = [url for url in fetch.calls if url.startswith("https://www.school.cz/catalogue/")]
    assert len(catalogue_calls) <= 5
    assert candidates  # every page still contributes its anchors


def test_a_paginated_catalogue_is_read_to_its_end() -> None:
    """A listing's own pages are read before the programme pages it named.

    Charles University's SIS catalogue states fifty programmes per page and
    links to the next thirty-three pages with the same path and a different
    query. Read in document order the walk spent its sixty entries on the fifty
    programme pages the listing had just named - each already a candidate - and
    never reached page 2, so 56 of 912 rows resolved. The listing's siblings are
    therefore queued ahead of the pages they lead to.
    """
    target = school_target("is.school.cz")
    target["entryUrls"] = ["https://is.school.cz/study-programs/program"]
    rows = [row("msmt-vs_00000", f"Programme {index}", "b", "cs") for index in range(4)]

    def listing(page: int) -> str:
        items = "\n".join(
            f'<a href="/study-programs/program/accreditation/{index}">'
            f"Programme {index if page == 1 else page * 10 + index}</a>"
            for index in range(4)
        )
        # The next page is linked with the same path and a different query.
        return (
            f"<html><body>{items}"
            f'<a href="/study-programs/program?page={page + 1}">{page + 1}</a>'
            "</body></html>"
        )

    fetch = FakeFetch(
        {
            "https://is.school.cz/study-programs/program": (200, listing(1)),
            "https://is.school.cz/study-programs/program?page=2": (200, listing(2)),
            "https://is.school.cz/study-programs/program?page=3": (200, listing(3)),
        },
        default=(200, "<html><body></body></html>"),
    )
    limits = rpl.Limits(max_catalogue_entries=2)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    match = rpl.Match(rows)
    candidates, _notes = rpl.discover_candidates(
        target,
        throttled,
        limits,
        rpl.Budget(60),
        interesting=lambda key: key in match.by_title,
    )
    # Both listing pages were read inside the two-entry budget...
    assert fetch.calls.count("https://is.school.cz/study-programs/program?page=2") == 1
    # ...and neither spent a read on a programme page the listing had named.
    assert not [url for url in fetch.calls if "/accreditation/" in url]
    # The names on both listings are candidates.
    assert len(candidates) == 4
    assert {item.title for item in candidates} == {
        "programme 0", "programme 1", "programme 2", "programme 3"
    }


def test_the_level_written_beside_the_name_separates_a_title_held_at_two_levels() -> None:
    """A catalogue is a table whose row states the level; the link names none.

    Charles University's SIS catalogue writes a faculty, "Typ studia" and the
    programme name into one row, so the text beside the link says "doktorské"
    while the link itself only says "Optika a optometrie". The register holds
    that title once as a bachelor and once as a master programme; without the
    row both stay ambiguous and both rows keep the university site.
    """
    target = school_target("is.school.cz")
    target["entryUrls"] = ["https://is.school.cz/study-programs/program"]
    rows = [
        row("msmt-vs_00000", "Optika a optometrie", "b", "cs"),
        row("msmt-vs_00000", "Optika a optometrie", "m", "cs"),
    ]
    listing = (
        "<html><body><table><tbody>"
        '<tr class="row"><td>Přírodovědecká fakulta</td><td>bakalářské</td>'
        '<td><a href="/study-programs/program/accreditation/1">Optika a optometrie</a></td></tr>'
        '<tr class="row"><td>Přírodovědecká fakulta</td><td>magisterské</td>'
        '<td><a href="/study-programs/program/accreditation/2">Optika a optometrie</a></td></tr>'
        "</tbody></table></body></html>"
    )
    fetch = FakeFetch({"https://is.school.cz/study-programs/program": (200, listing)})
    match = rpl.Match(rows)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    links, unresolved, _multiple, notes = rpl.resolve_school(
        target, match, [], throttled, rpl.Limits(), rpl.Budget(60), live=True
    )
    assert notes == []
    assert links[rows[0].ident].url == "https://is.school.cz/study-programs/program/accreditation/1"
    assert links[rows[1].ident].url == "https://is.school.cz/study-programs/program/accreditation/2"
    assert unresolved == {}


def test_the_heading_over_a_list_states_the_level_of_every_row() -> None:
    """A level written once above a list belongs to the whole list.

    VŠB-TUO's catalogue writes `<h2>Bakalářské programy</h2>` and then one `<li>`
    per programme, each holding only the name and the faculty - so the level is
    beside the first row's link and nowhere near the second one's. Reading only
    the text on a link's own row leaves the second row ambiguous, which is how
    104 of VŠB-TUO's 293 rows stayed unresolved while the page already said which
    list each programme was in.
    """
    target = school_target("www.school.cz")
    target["entryUrls"] = ["https://www.school.cz/uchazec/studijni-programy"]
    rows = [
        row("msmt-vs_00000", "Aplikovaná elektronika", "b", "cs"),
        row("msmt-vs_00000", "Kybernetika", "m", "cs"),
        row("msmt-vs_00000", "Tělesná výchova a sport", "d", "cs"),
    ]
    listing = (
        "<html><body><div class='study-programmes'>"
        "<h2 id='bachelor'>Bakalářské programy</h2><div><ul>"
        "<li><a href='.?programmeId=764'>Aplikovaná elektronika</a><span>(FEI)</span></li>"
        "<li><a href='.?programmeId=765'>Kybernetika</a><span>(FEI)</span></li>"
        "</ul></div>"
        "<h2 id='master'>Magisterské programy</h2><div><ul>"
        "<li><a href='.?programmeId=800'>Tělesná výchova a sport</a><span>(FSI)</span></li>"
        "</ul></div>"
        "</div></body></html>"
    )
    fetch = FakeFetch(
        {"https://www.school.cz/uchazec/studijni-programy": (200, listing)},
        default=(200, "<html><body></body></html>"),
    )
    match = rpl.Match(rows)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    links, unresolved, _multiple, notes = rpl.resolve_school(
        target, match, [], throttled, rpl.Limits(), rpl.Budget(60), live=True
    )
    assert notes == []
    # Every row of a list takes the level that list's heading states, so the
    # master's row is not bound to the bachelor page that shares its name.
    assert links[rows[0].ident].url == "https://www.school.cz/uchazec/?programmeId=764"
    assert links[rows[1].ident].url == "https://www.school.cz/uchazec/?programmeId=765"
    assert links[rows[2].ident].url == "https://www.school.cz/uchazec/?programmeId=800"
    assert unresolved == {}


def test_a_heading_stating_two_levels_states_none() -> None:
    """A page that states two levels on one list states none.

    Only a level the school's own page states is used. A heading and a row that
    disagree, or a list under both a bachelor and a doctoral heading, is read as
    the page having said nothing, so the row keeps the university site instead of
    having a level chosen for it.
    """
    target = school_target("www.school.cz")
    target["entryUrls"] = ["https://www.school.cz/uchazec/studijni-programy"]
    rows = [
        row("msmt-vs_00000", "Kybernetika", "b", "cs"),
        row("msmt-vs_00000", "Kybernetika", "m", "cs"),
    ]
    listing = (
        "<html><body>"
        "<h2>Bakalářské a magisterské programy</h2>"
        "<ul><li><a href='.?programmeId=764'>Kybernetika</a></li></ul>"
        "</body></html>"
    )
    fetch = FakeFetch(
        {"https://www.school.cz/uchazec/studijni-programy": (200, listing)},
        default=(200, "<html><body></body></html>"),
    )
    match = rpl.Match(rows)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    links, unresolved, _multiple, _notes = rpl.resolve_school(
        target, match, [], throttled, rpl.Limits(), rpl.Budget(60), live=True
    )
    assert links == {}
    assert set(unresolved.values()) == {"ambiguous_register_rows"}


def test_the_level_written_after_the_name_states_the_rows_level() -> None:
    """A school that writes the level under the name is read just the same.

    Ostrava's catalogue has no row opener inside a programme's own cells: the
    name sits in a `<div>`, the faculty in the next, and the level
    ("navazující magisterské") in the last one below it. The filter sidebar above
    it names both a bachelor and a master level, so the text before the link
    states two and therefore none - which is why 51 of Ostrava's 169 rows stayed
    ambiguous while the page said which was which under every name.
    """
    target = school_target("www.school.cz")
    target["entryUrls"] = ["https://www.school.cz/studijniobory"]
    rows = [
        row("msmt-vs_00000", "Anglická filologie", "b", "cs"),
        row("msmt-vs_00000", "Anglická filologie", "m", "cs"),
        row("msmt-vs_00000", "Český jazyk a literatura", "b", "cs"),
        row("msmt-vs_00000", "Český jazyk a literatura", "m", "cs"),
    ]
    listing = (
        "<html><body><div class='filter'><ul>"
        "<li>bakalářské</li><li>magisterské</li><li>navazující</li>"
        "</ul></div>"
        "<div class='w100 bb'><div class='w70 lfloat'><div class='w100 pb1'>"
        "<a href='./?specializaceid=1001' title='detail'>Anglická filologie</a></div>"
        "<div class='w100'>(Anglická filologie)</div></div>"
        "<div class='w20 lfloat'>Filozofická fakulta</div>"
        "<div class='w15 rfloat'>navazující magisterské</div></div>"
        "<div class='w100 bb'><div class='w70 lfloat'><div class='w100 pb1'>"
        "<a href='./?specializaceid=1002' title='detail'>Anglická filologie</a></div>"
        "<div class='w100'>(Anglická filologie)</div></div>"
        "<div class='w20 lfloat'>Filozofická fakulta</div>"
        "<div class='w15 rfloat'>bakalářské studium</div></div>"
        "<div class='w100 bb'><div class='w70 lfloat'><div class='w100 pb1'>"
        "<a href='./?specializaceid=1003' title='detail'>Český jazyk a literatura</a></div>"
        "<div class='w100'>(Český jazyk a literatura)</div></div>"
        "<div class='w20 lfloat'>Filozofická fakulta</div>"
        "<div class='w15 rfloat'>bakalářské a navazující magisterské</div></div>"
        "</div></body></html>"
    )
    fetch = FakeFetch(
        {"https://www.school.cz/studijniobory": (200, listing)},
        default=(200, "<html><body></body></html>"),
    )
    match = rpl.Match(rows)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    links, unresolved, _multiple, notes = rpl.resolve_school(
        target, match, [], throttled, rpl.Limits(), rpl.Budget(60), live=True
    )
    assert notes == []
    # Each row takes the level written under its own name, and the row whose
    # own cells state both levels keeps the university site.
    assert links[rows[0].ident].url == "https://www.school.cz/?specializaceid=1002"
    assert links[rows[1].ident].url == "https://www.school.cz/?specializaceid=1001"
    assert set(unresolved) == {rows[2].ident, rows[3].ident}
    assert set(unresolved.values()) == {"ambiguous_register_rows"}


def test_the_level_after_a_name_never_comes_from_the_next_programme() -> None:
    """The text after a link stops at the next link on the page.

    A row that names two programmes must not lend the second one's level to the
    first: the window ends at the next anchor, so a level that belongs to the
    programme named after it is never read as this one's.
    """
    target = school_target("www.school.cz")
    target["entryUrls"] = ["https://www.school.cz/studijniobory"]
    rows = [
        row("msmt-vs_00000", "Anglická filologie", "b", "cs"),
        row("msmt-vs_00000", "Anglická filologie", "m", "cs"),
    ]
    listing = (
        "<html><body><table><tbody>"
        "<tr><td>Filozofická fakulta</td>"
        "<td><a href='?id=1'>Anglická filologie</a> "
        "<a href='?id=2'>Anglická filologie</a></td>"
        "<td>navazující magisterské</td></tr>"
        "</tbody></table></body></html>"
    )
    fetch = FakeFetch(
        {"https://www.school.cz/studijniobory": (200, listing)},
        default=(200, "<html><body></body></html>"),
    )
    match = rpl.Match(rows)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    links, unresolved, _multiple, _notes = rpl.resolve_school(
        target, match, [], throttled, rpl.Limits(), rpl.Budget(60), live=True
    )
    # Only the second name reaches the level cell, so only the master's row is
    # bound; the bachelor's page on the same row states no level of its own.
    assert links[rows[1].ident].url == "https://www.school.cz/studijniobory?id=2"
    assert set(unresolved) == {rows[0].ident}
    assert unresolved[rows[0].ident] == "ambiguous_register_rows"


def test_one_listing_is_read_once_whatever_its_query() -> None:
    """A presentation toggle is not a listing the walk has not read.

    Charles University's catalogue offers the same listing again as
    "?setDeviceType=mobile&page=2" and as "?page=2", and both spellings sit in
    the listing's own pagination. Read in document order the walk spent 11 of
    its 60 entries on device twins of pages it had already read.
    """
    target = school_target("is.school.cz")
    target["entryUrls"] = ["https://is.school.cz/program"]
    listing = (
        "<html><body>"
        '<a href="/program?page=2">2</a>'
        '<a href="/program?setDeviceType=mobile&amp;page=2">2</a>'
        '<a href="/program?page=1">1</a>'
        "</body></html>"
    )
    fetch = FakeFetch(
        {
            "https://is.school.cz/program": (200, listing),
            "https://is.school.cz/program?page=2": (200, listing),
            "https://is.school.cz/program?setDeviceType=mobile&page=2": (200, listing),
        },
        default=(200, "<html><body></body></html>"),
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    _candidates, _notes = rpl.discover_candidates(
        target,
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
        # The pagination's own numbers name no register row, so they are not
        # candidates: only the listings they name are read.
        interesting=lambda key: False,
    )
    assert fetch.calls.count("https://is.school.cz/program?page=2") == 1
    assert not [url for url in fetch.calls if "setDeviceType" in url]


def test_a_programme_page_is_not_walked_as_further_catalogue() -> None:
    """A catalogue's rows link programme pages, not more listings.

    Charles University's SIS catalogue carries "/program/accreditation/1372" in
    the row after the listing that named it, with the same tokens as the
    catalogue itself. Walked as catalogue it names only the one programme it
    is - and the anchor on the listing already named it - so the walk spent 31
    of its 60 entries on programme pages and stopped at 9 of the 34 listings.
    The page is still a candidate: it just costs no read of its own.
    """
    target = school_target("is.school.cz")
    target["entryUrls"] = ["https://is.school.cz/study-programs/program"]
    listing = (
        "<html><body>"
        '<a href="/study-programs/program?page=2">2</a>'
        '<a href="/study-programs/program/accreditation/1372">Optika a optometrie</a>'
        '<a href="/study-programs/program/accreditation/1373">Kybernetika</a>'
        "</body></html>"
    )
    fetch = FakeFetch(
        {
            "https://is.school.cz/study-programs/program": (200, listing),
            "https://is.school.cz/study-programs/program?page=2": (200, "<html><body></body></html>"),
        },
        default=(200, "<html><body></body></html>"),
    )
    rows = [row("msmt-vs_00000", "Optika a optometrie", "b", "cs"), row("msmt-vs_00000", "Kybernetika", "b", "cs")]
    match = rpl.Match(rows)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    candidates, _notes = rpl.discover_candidates(
        target,
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
        interesting=lambda key: key in match.by_title,
    )
    assert [item.url for item in candidates] == [
        "https://is.school.cz/study-programs/program/accreditation/1372",
        "https://is.school.cz/study-programs/program/accreditation/1373",
    ]
    assert not [url for url in fetch.calls if "/accreditation/" in url]


def test_a_link_that_names_no_register_row_is_not_a_candidate() -> None:
    """Ostrava lists 4,776 links for 169 register rows.

    Keeping every one of them filled the candidate list in document order and
    lost the rest, so a link is only carried when its own text names a title the
    register holds. Nothing is guessed at: a title the school writes differently
    is simply not bound, and the row keeps the university site.
    """
    target = school_target()
    homepage = """
    <html><body>
      <a href="/programmes/">Studijní programy</a>
    </body></html>
    """
    catalogue = """
    <html><body>
      <a href="/programmes/kynologie/">Kynologie</a>
      <a href="/programmes/sportovni-lekarstvi/">Sportovní lékařství</a>
    </body></html>
    """
    fetch = FakeFetch(
        {
            "https://www.school.cz": (200, homepage),
            "https://www.school.cz/programmes": (200, catalogue),
        }
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    match = rpl.Match([row("msmt-vs_00000", "Kynologie", "b", "cs")])
    candidates, _notes = rpl.discover_candidates(
        target,
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
        interesting=lambda key: key in match.by_title,
    )
    assert [item.url for item in candidates] == ["https://www.school.cz/programmes/kynologie/"]


def test_the_page_budget_is_counted_per_school() -> None:
    """A second school in one run starts with its own page budget.

    Counted run-wide, the first school's pages starved every school after it:
    at a run-wide 240 the walk left Charles University, CVUT and Palacky at 0
    resolved rows with "budget_exhausted", because one school had already spent
    the whole run. The counter therefore resets per school, while the run-wide
    total is still reported so a tick's cost stays visible.
    """
    anchors = "\n".join(
        f'<a href="/catalogue/{index}/">Programme catalogue {index}</a>' for index in range(40)
    )
    page = f"<html><body>{anchors}</body></html>"
    responses: dict[str, tuple[int, str]] = {}
    for domain in ("school.cz", "other.cz"):
        responses[f"https://www.{domain}"] = (200, page)
        for index in range(40):
            # catalogue_entries() normalises entries without a trailing slash.
            responses[f"https://www.{domain}/catalogue/{index}"] = (200, page)
    fetch = FakeFetch(responses)
    limits = rpl.Limits(max_page_fetches=2)
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)

    _first, first_notes = rpl.discover_candidates(
        school_target("school.cz"), throttled, limits, rpl.Budget(600)
    )
    assert len([url for url in fetch.calls if "www.school.cz" in url]) == 2
    assert any("budget_exhausted" in note for note in first_notes)

    throttled.begin_school()
    second, _second_notes = rpl.discover_candidates(
        school_target("other.cz"), throttled, limits, rpl.Budget(600)
    )
    # The second school reads its own two pages although the run has now spent
    # four, which a run-wide counter would have forbidden.
    assert len([url for url in fetch.calls if "www.other.cz" in url]) == 2
    assert second
    assert throttled.requests == 4


def test_ranking_prefers_the_page_whose_slug_restates_the_programme() -> None:
    match = rpl.Match([row("msmt-vs_1", "Natural resources and environment", "m", "en")])
    good = candidate("https://school.cz/programmes/natural-resources-and-environment/", "Natural resources and environment", "m", "en")
    test_page = candidate("https://school.cz/programmes/testovaci-program-3/", "Natural resources and environment", "m", "en")
    assert rpl.candidate_rank(good, match.rows[0]) < rpl.candidate_rank(test_page, match.rows[0])

    target = school_target()
    throttled = rpl.ThrottledFetch(FakeFetch({}), sleep=lambda _seconds: None)
    links, unresolved, multiple, _notes = rpl.resolve_school(
        target,
        match,
        [test_page, good],
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
        live=False,
    )
    assert list(links.values())[0].url == good.url
    assert multiple == 1
    assert unresolved == {}


def test_a_page_read_inside_the_window_is_not_displaced_by_an_unread_one() -> None:
    """The proven page outranks a page nobody has read yet.

    Measured 2026-09-28 on AMU: the walk bound two rows to other DAMU addresses
    that answered 404, and the two pages proven the day before left the index
    with them. Coverage may only rise, so the address a live read already
    confirmed keeps the row.
    """
    match = rpl.Match([row("msmt-vs_1", "Alternativní a loutkové divadlo", "b", "cs")])
    proven = candidate(
        "https://school.cz/en/department/department-of-alternative-and-puppet-theatre/",
        "Alternativní a loutkové divadlo",
        "b",
        "cs",
        matched_by="previous_run",
    )
    proven.checked_at = "2026-09-28T20:30:00Z"
    discovered = candidate(
        "https://school.cz/cs/katedry-programy/katedra/alternativni-a-loutkove-divadlo-184/",
        "Alternativní a loutkové divadlo",
        "b",
        "cs",
        matched_by="school_sitemap_slug",
    )
    target = school_target()
    throttled = rpl.ThrottledFetch(FakeFetch({}), sleep=lambda _seconds: None)
    links, unresolved, _multiple, _notes = rpl.resolve_school(
        target,
        match,
        [discovered, proven],
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
        live=False,
        kept_pages={match.rows[0].ident: proven.url},
    )
    assert links[match.rows[0].ident].url == proven.url
    assert unresolved == {}


def test_a_stale_previous_page_loses_to_the_better_discovered_one() -> None:
    """Outside the refresh window the school is walked again, and may improve."""
    match = rpl.Match([row("msmt-vs_1", "Natural resources and environment", "m", "en")])
    proven = candidate(
        "https://school.cz/programmes/12345/",
        "Natural resources and environment",
        "m",
        "en",
        matched_by="previous_run",
    )
    good = candidate("https://school.cz/programmes/natural-resources-and-environment/", "Natural resources and environment", "m", "en")
    target = school_target()
    throttled = rpl.ThrottledFetch(FakeFetch({}), sleep=lambda _seconds: None)
    links, _unresolved, _multiple, _notes = rpl.resolve_school(
        target,
        match,
        [proven, good],
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
        live=False,
        kept_pages={},
    )
    assert links[match.rows[0].ident].url == good.url


def test_a_404_is_read_again_before_it_drops_the_link() -> None:
    """One 404 is not proof the page is gone.

    DAMU answered 404 for its English department page inside a run and 200 on
    every read after it. Dropping on the first answer cost that row its link, so
    the address is read once more and only a 404 that stays a 404 drops it.
    """
    link = rpl.Link(
        url="https://school.cz/p/a/",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="b",
        language="cs",
        matched_title="A",
        row_title="A",
        source_url="https://school.cz/programmes",
        matched_by="school_catalogue_anchor",
        reachability="unverified",
        matched_at="2026-09-27T00:00:00Z",
    )

    class Flaky(FakeFetch):
        """One 404, then the page as the school serves it."""

        def __init__(self) -> None:
            super().__init__(
                {
                    "https://school.cz/p/a/": (
                        200,
                        "<html><head><title>A | school</title></head><body><h1>A</h1></body></html>",
                    )
                }
            )

        def __call__(self, url: str) -> tuple[int, str]:
            self.calls.append(url)
            if len(self.calls) == 1:
                return 404, ""
            return self.responses.get(url, self.default)

    fetch = Flaky()
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    outcomes = rpl.verify_links({"inv-a": link}, throttled, rpl.Limits(), rpl.Budget(60))
    assert outcomes["https://school.cz/p/a/"] == "verified"
    assert fetch.calls == ["https://school.cz/p/a/", "https://school.cz/p/a/"]


def test_a_404_that_stays_a_404_still_drops_the_link() -> None:
    """The confirmation read only buys one more answer, not a reprieve."""
    link = rpl.Link(
        url="https://school.cz/p/gone/",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="b",
        language="cs",
        matched_title="A",
        row_title="A",
        source_url="https://school.cz/programmes",
        matched_by="school_catalogue_anchor",
        reachability="unverified",
        matched_at="2026-09-27T00:00:00Z",
    )
    fetch = FakeFetch({"https://school.cz/p/gone/": (404, "")})
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    outcomes = rpl.verify_links({"inv-a": link}, throttled, rpl.Limits(), rpl.Budget(60))
    assert outcomes["https://school.cz/p/gone/"] == "dropped_404"
    assert fetch.calls == ["https://school.cz/p/gone/", "https://school.cz/p/gone/"]


def test_several_school_keeps_one_page_per_programme() -> None:
    match = rpl.Match([row("msmt-vs_1", "Agriculture and Food", "b", "en")])
    on_study = candidate("https://study.school.cz/programmes/agriculture-and-food/", "Agriculture and Food", "b", "en")
    on_studuj = candidate("https://studuj.school.cz/programmes/agriculture-and-food/", "Agriculture and Food", "b", "en")
    target = school_target()
    throttled = rpl.ThrottledFetch(FakeFetch({}), sleep=lambda _seconds: None)
    links, unresolved, multiple, _notes = rpl.resolve_school(
        target, match, [on_study, on_studuj], throttled, rpl.Limits(), rpl.Budget(60), live=False
    )
    # Both catalogues are the school's own pages, so the row keeps one of them,
    # chosen deterministically, instead of losing the link.
    assert len(links) == 1
    assert links[match.rows[0].ident].url == min(on_study.url, on_studuj.url)
    assert multiple == 1
    assert unresolved == {}


def test_homepage_failure_is_reported_not_guessed() -> None:
    target = school_target()
    throttled = rpl.ThrottledFetch(FakeFetch({"https://www.school.cz": (503, "")}), sleep=lambda _seconds: None)
    candidates, notes = rpl.discover_candidates(target, throttled, rpl.Limits(), rpl.Budget(60))
    assert candidates == []
    assert notes == ["homepage_unreachable_http_503"]


def test_payload_rows_with_several_pages_are_counted(tmp_path: Path) -> None:
    previous = rpl.load_previous(tmp_path / "missing.json")
    assert previous == {}
    payload = {
        "links": {
            "inv-x": {
                "url": "https://school.cz/p/x/",
                "reachability": "verified",
                "checkedAt": "2026-09-27T00:00:00Z",
            }
        },
        "unresolved": [{"rowId": "inv-y", "reason": "no_candidate_page"}],
        "coverage": {"schools": [{"institutionId": "msmt-vs_9", "offerings": 2, "resolved": 1, "notes": []}]},
    }
    links = {}
    unresolved = {"inv-y": "no_candidate_page"}
    merged_links, merged_reasons, merged_schools = rpl.merge_previous(payload, links, unresolved, [])
    assert "inv-x" in merged_links
    assert merged_reasons["inv-y"] == "no_candidate_page"
    assert merged_schools[0]["institutionId"] == "msmt-vs_9"
    assert "carried_from_previous_run" in merged_schools[0]["notes"]


class DrivenClock:
    """A run budget the test drives, so the run stops where it stops.

    The production budget is wall clock, which a test cannot steer. What needs
    testing is a run that is cut short, so this clock runs out once ``limit``
    pages have been spent. ``budget()`` stands in for
    ``resolve_programme_links.Budget``: ``build_links`` builds its own budget
    object, so the run's budget has to read this one clock.
    """

    def __init__(self, limit: int):
        self.limit = limit
        self.spent = 0

    @property
    def expired(self) -> bool:
        return self.spent > self.limit

    def budget(self):
        clock = self

        class RunBudget:
            @property
            def expired(self) -> bool:
                return clock.expired

        return RunBudget()


class ClockedFetch:
    """Answers a site and charges every page it serves to the run's budget."""

    def __init__(self, responses: dict[str, tuple[int, str]], clock: DrivenClock):
        self.responses = responses
        self.clock = clock
        self.calls: list[str] = []

    def __call__(self, url: str) -> tuple[int, str]:
        self.calls.append(url)
        self.clock.spent += 1
        return self.responses.get(url, (404, ""))


def test_a_run_the_budget_cuts_short_keeps_the_whole_index(monkeypatch) -> None:
    """Two schools, a budget that reaches one, and an index that still holds both.

    The rotation exists because one run cannot read every school (measured
    2026-09-27: about 330 seconds per school, so a 600-second run walks two of
    53). The school the run read keeps the link it found; the school it never
    reached keeps the link and the numbers an earlier run proved, with that
    run's resolvedAt, and is marked as not read this time. Nothing the run did
    not read is reported as unresolved, and the run never presents its two
    schools as the whole index.
    """
    walked = row("msmt-vs_1", "Kynologie", "b", "cs")
    not_reached = row("msmt-vs_2", "Zoologie", "b", "cs")
    previous = {
        "links": {
            not_reached.ident: {
                "url": "https://www.other.cz/programmes/zoologie/",
                "institutionId": "msmt-vs_2",
                "degree": "b",
                "language": "cs",
                "matchedTitle": "Zoologie",
                "rowTitle": "Zoologie",
                "matchedBy": "school_catalogue_anchor",
                "reachability": "verified",
                "matchedAt": "2026-08-01T00:00:00Z",
                "checkedAt": "2026-08-01T00:00:00Z",
            }
        },
        "unresolved": [],
        "coverage": {
            "schools": [
                {
                    "institutionId": "msmt-vs_2",
                    "name": "Read Long Ago",
                    "offerings": 1,
                    "resolved": 1,
                    "unresolved": 0,
                    "unresolvedReasons": {},
                    "resolvedAt": "2026-08-01T00:00:00Z",
                    "notes": [],
                }
            ]
        },
    }
    institutions = [
        {"id": "msmt-vs_1", "officialName": "Never Read", "officialUrl": "https://www.school.cz"},
        {"id": "msmt-vs_2", "officialName": "Read Long Ago", "officialUrl": "https://www.other.cz"},
    ]
    clock = DrivenClock(3)
    fetch = ClockedFetch(
        {
            "https://www.school.cz": (
                200,
                '<html><body><a href="/programmes/kynologie/">Kynologie</a></body></html>',
            ),
            # The catalogue walk reads the page without its trailing slash, the
            # check reads the link as the school's own anchor spelled it.
            "https://www.school.cz/programmes/kynologie": (200, "<html><body></body></html>"),
            "https://www.school.cz/programmes/kynologie/": (
                200,
                "<html><body><h1>Kynologie</h1></body></html>",
            ),
            "https://www.school.cz/sitemap.xml": (
                200,
                "<urlset><url><loc>https://www.school.cz/programmes/kynologie/</loc></url></urlset>",
            ),
        },
        clock,
    )
    monkeypatch.setattr(rpl, "Budget", lambda _seconds: clock.budget())
    monkeypatch.setattr(rpl, "PER_HOST_SLEEP_SECONDS", 0.0)
    payload = rpl.build_links(
        fetch=fetch,
        now=datetime(2026, 9, 27, tzinfo=timezone.utc),
        budget_seconds=3.0,
        config={"harvestedSources": [], "schools": []},
        previous=previous,
        # The never-read school is walked first; the budget then runs out.
        institutions=rpl.rotation_order(institutions, previous),
        rows_by_institution={"msmt-vs_1": [walked], "msmt-vs_2": [not_reached]},
    )

    # The school the run read: its row is linked to the page its own site names,
    # and the check confirmed the page still carries the programme name.
    assert payload["links"][walked.ident]["url"] == "https://www.school.cz/programmes/kynologie/"
    assert payload["links"][walked.ident]["reachability"] == "verified"
    # The school the budget never reached keeps what the earlier run proved.
    assert payload["links"][not_reached.ident]["url"] == "https://www.other.cz/programmes/zoologie/"
    assert payload["links"][not_reached.ident]["reachability"] == "verified"
    assert payload["counts"]["linked"] == 2
    # No row is reported unresolved by a run that never read its school, and the
    # school that was not read says so instead of reporting empty numbers.
    assert payload["unresolved"] == []
    assert rpl.NOT_ATTEMPTED not in {item["reason"] for item in payload["unresolved"]}
    by_school = {item["institutionId"]: item for item in payload["coverage"]["schools"]}
    assert by_school["msmt-vs_1"]["resolvedAt"] == "2026-09-27T00:00:00Z"
    assert by_school["msmt-vs_1"]["resolved"] == 1
    assert by_school["msmt-vs_2"]["resolvedAt"] == "2026-08-01T00:00:00Z"
    assert by_school["msmt-vs_2"]["resolved"] == 1
    assert "not_attempted_this_run" in by_school["msmt-vs_2"]["notes"]


def test_rotation_reads_the_least_recently_read_school_first() -> None:
    """A run that can only read two schools must not re-read the same two.

    At the configured depth a school costs about 330 wall-clock seconds, so a
    600-second run walks two of the 53 schools. Without a rotation the walk
    always starts at the head of the list, which is how Charles University, CVUT
    and Palacky stayed at zero resolved programme pages: nothing ever reached
    them. A school that has never been read goes first of all, then the one
    read longest ago.
    """
    never_read = {"id": "msmt-vs_10000", "officialName": "Never read"}
    read_today = {"id": "msmt-vs_20000", "officialName": "Read today"}
    read_long_ago = {"id": "msmt-vs_30000", "officialName": "Read long ago"}
    schools = [read_today, read_long_ago, never_read]
    previous = {
        "coverage": {
            "schools": [
                {"institutionId": "msmt-vs_20000", "resolvedAt": "2026-09-27T00:00:00Z"},
                {"institutionId": "msmt-vs_30000", "resolvedAt": "2026-08-01T00:00:00Z"},
            ]
        }
    }
    assert [item["id"] for item in rpl.rotation_order(schools, previous)] == [
        "msmt-vs_10000",
        "msmt-vs_30000",
        "msmt-vs_20000",
    ]
    # No previous run yet: every school has never been read, so the order is
    # stable and the first schools in the index are walked first.
    assert [item["id"] for item in rpl.rotation_order(schools, {})] == [
        "msmt-vs_10000",
        "msmt-vs_20000",
        "msmt-vs_30000",
    ]


def test_a_school_the_run_never_reached_keeps_its_proven_link() -> None:
    """The rotation leaves most schools unread; they must not lose their links.

    A school the budget never reached gives this run nothing to say about its
    own pages, so the last run that did read it answers instead: the row keeps
    its proven link and its reason, and the school keeps that run's numbers and
    resolvedAt, marked as not read this time. A two-school run must not report
    the other fifty-one schools as having no programme page at all.
    """
    previous = {
        "links": {
            "inv-a": {
                "url": "https://www.school.cz/programmes/kynologie/",
                "institutionId": "msmt-vs_9",
                "degree": "b",
                "language": "cs",
                "matchedTitle": "Kynologie",
                "rowTitle": "Kynologie",
                "matchedBy": "school_catalogue_anchor",
                "reachability": "verified",
                "matchedAt": "2026-09-20T00:00:00Z",
                "checkedAt": "2026-09-20T00:00:00Z",
            }
        },
        "unresolved": [{"rowId": "inv-b", "reason": "no_candidate_page"}],
        "coverage": {
            "schools": [
                {
                    "institutionId": "msmt-vs_9",
                    "offerings": 2,
                    "resolved": 1,
                    "unresolved": 1,
                    "unresolvedReasons": {"no_candidate_page": 1},
                    "resolvedAt": "2026-09-20T00:00:00Z",
                    "notes": [],
                }
            ]
        },
    }
    links, unresolved, schools = rpl.merge_previous(
        previous,
        {},
        {"inv-a": rpl.NOT_ATTEMPTED, "inv-b": rpl.NOT_ATTEMPTED},
        [
            {
                "institutionId": "msmt-vs_9",
                "offerings": 2,
                "resolved": 0,
                "unresolved": 2,
                "unresolvedReasons": {rpl.NOT_ATTEMPTED: 2},
                "notes": ["budget_exhausted_before_school"],
            }
        ],
    )
    # The link survives, and no row is called unresolved by a run that never
    # read it: the previous run that did read it keeps the reason it proved.
    assert links["inv-a"].url == "https://www.school.cz/programmes/kynologie/"
    assert links["inv-a"].reachability == "verified"
    assert unresolved == {"inv-b": "no_candidate_page"}
    # The school keeps the numbers of the run that read it, and that run's
    # resolvedAt, so the next rotation knows when it was last walked.
    assert schools[0]["resolved"] == 1
    assert schools[0]["resolvedAt"] == "2026-09-20T00:00:00Z"
    assert schools[0]["notes"] == ["not_attempted_this_run"]


def test_a_plain_http_page_the_school_also_serves_over_https_is_promoted() -> None:
    """The school's own page, reached over http, is not dropped for its scheme.

    UJEP's faculty site links its programme brochures over http and serves them
    over https too. The published inventory accepts only https addresses, so the
    twin is read once and replaces the address when it still names this row.
    """
    link = rpl.Link(
        url="http://ff.school.cz/studijni-brozura?view=article&id=12211",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="b",
        language="cs",
        matched_title="Archivní věda",
        row_title="Archivní věda",
        source_url="http://ff.school.cz/studium",
        matched_by="school_catalogue_anchor",
        reachability="unverified",
        matched_at="2026-09-27T00:00:00Z",
    )
    body = (
        "<html><head><title>Archivní věda | Filozofická fakulta</title></head>"
        "<body><h1>Archivní věda</h1></body></html>"
    )
    fetch = FakeFetch(
        {"https://ff.school.cz/studijni-brozura?view=article&id=12211": (200, body)}
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    links = {"inv-a": link}
    notes = rpl.promote_https(links, throttled, rpl.Limits(), rpl.Budget(60))
    assert notes == ["promoted_to_https: 1"]
    promoted = links["inv-a"]
    assert promoted.url == "https://ff.school.cz/studijni-brozura?view=article&id=12211"
    assert promoted.reachability == "verified"
    assert promoted.page_title == "Archivní věda"
    assert promoted.checked_at
    # The binding itself is untouched: only the published address changes.
    assert promoted.matched_by == "school_catalogue_anchor"
    assert promoted.matched_at == "2026-09-27T00:00:00Z"
    # Only the twin is read: the plain-http address is never fetched again.
    assert fetch.calls == ["https://ff.school.cz/studijni-brozura?view=article&id=12211"]


def test_promotion_leaves_the_link_alone_when_the_school_serves_no_https() -> None:
    link = rpl.Link(
        url="http://ff.school.cz/studijni-brozura?view=article&id=9824",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="b",
        language="cs",
        matched_title="Archivnictví",
        row_title="Archivnictví",
        source_url="http://ff.school.cz/studium",
        matched_by="school_catalogue_anchor",
        reachability="verified",
        matched_at="2026-09-27T00:00:00Z",
        checked_at="2026-09-27T00:00:00Z",
    )
    fetch = FakeFetch({}, default=(404, ""))
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    assert rpl.promote_https({"inv-a": link}, throttled, rpl.Limits(), rpl.Budget(60)) == []
    assert link.url.startswith("http://")


def test_promotion_refuses_a_twin_that_states_another_level() -> None:
    """The https twin of an http page is still checked for whose page it is."""
    link = rpl.Link(
        url="http://ff.school.cz/studijni-brozura?view=article&id=9855",
        row_id="inv-a",
        institution_id="msmt-vs_1",
        degree="b",
        language="cs",
        matched_title="Filosofie",
        row_title="Filosofie",
        source_url="http://ff.school.cz/studium",
        matched_by="school_catalogue_anchor",
        reachability="verified",
        matched_at="2026-09-27T00:00:00Z",
        checked_at="2026-09-27T00:00:00Z",
    )
    body = (
        "<html><head><title>Filosofie – doktorské studium | Fakulta</title></head>"
        "<body><h1>Filosofie – doktorské studium</h1></body></html>"
    )
    fetch = FakeFetch(
        {"https://ff.school.cz/studijni-brozura?view=article&id=9855": (200, body)}
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    assert rpl.promote_https({"inv-a": link}, throttled, rpl.Limits(), rpl.Budget(60)) == []
    assert link.url.startswith("http://")


def test_a_folded_http_link_is_promoted_before_the_previous_index_is_merged() -> None:
    """A later run that never reads a school must not lose its http page."""
    previous = {
        "links": {
            "inv-a": {
                "url": "http://www.fbmi.cvut.cz/cs/student/asistivni-technologie",
                "institutionId": "msmt-vs_1",
                "degree": "b",
                "language": "cs",
                "matchedTitle": "Asistivní technologie",
                "rowTitle": "Asistivní technologie",
                "matchedBy": "school_catalogue_anchor",
                "reachability": "verified",
                "matchedAt": "2026-09-27T00:00:00Z",
                "checkedAt": "2026-09-27T00:00:00Z",
            }
        }
    }
    body = (
        "<html><head><title>Asistivní technologie | FBMI</title></head>"
        "<body><h1>Asistivní technologie</h1></body></html>"
    )
    fetch = FakeFetch(
        {"https://www.fbmi.cvut.cz/cs/student/asistivni-technologie": (200, body)}
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    promoted = rpl.promote_previous_https(previous, throttled, rpl.Limits(), rpl.Budget(60))
    assert promoted["links"]["inv-a"]["url"] == "https://www.fbmi.cvut.cz/cs/student/asistivni-technologie"
    assert promoted["links"]["inv-a"]["reachability"] == "verified"
    assert promoted["links"]["inv-a"]["checkedAt"]
    # The payload the run was given is left as it was.
    assert previous["links"]["inv-a"]["url"].startswith("http://")
    links, _unresolved, _schools = rpl.merge_previous(
        promoted, {}, {"inv-a": rpl.NOT_ATTEMPTED}, []
    )
    assert links["inv-a"].url == "https://www.fbmi.cvut.cz/cs/student/asistivni-technologie"


def test_write_payload_round_trips(tmp_path: Path) -> None:
    payload = {"generatedAt": "2026-09-27T00:00:00Z", "links": {}}
    path = rpl.write_payload(payload, tmp_path / "links.json")
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_a_sitemap_slug_ends_with_the_schools_own_programme_code() -> None:
    """The code names the school's record, not the programme.

    FAMU publishes /pro-uchazece/animovana-tvorba-232/ where the register row is
    "Animovaná tvorba", and DAMU publishes /studijni-programy/scenografie-259/ for
    "Scenografie". Read as written, the slug names nothing the register holds and
    the school's real page is never read.
    """
    titles = {"animovana tvorba", "scenografie", "photography"}
    names_row = lambda key: key in titles  # noqa: E731

    assert (
        rpl.slug_names_row("https://www.famu.cz/cs/katedry/katedra-kamery/pro-uchazece/animovana-tvorba-232/", names_row)
        == "animovana tvorba"
    )
    assert (
        rpl.slug_names_row(
            "https://www.damu.cz/cs/katedry-programy/katedra-scenografie/studijni-programy/scenografie-259/",
            names_row,
        )
        == "scenografie"
    )
    # A slug that already names a row is read exactly as the school wrote it.
    assert rpl.slug_names_row("https://www.famu.cz/en/photography-249/", names_row) == "photography"


def test_a_slug_the_register_does_end_with_a_number_is_not_shortened() -> None:
    """The code-free reading is only used when the school's own one names nothing.

    The register holds no title ending in a two-to-four digit number today, but a
    school that writes one must keep the page for it: shortening the slug first
    would read a real row's page as naming a row that does not exist.
    """
    names_row = lambda key: key == "divadlo 21"  # noqa: E731
    assert (
        rpl.slug_names_row("https://www.school.cz/programy/divadlo-21/", names_row) == "divadlo 21"
    )
    # Neither reading names a register row, so the page is not a candidate.
    nothing = lambda _key: False  # noqa: E731
    assert rpl.slug_names_row("https://www.school.cz/programy/neco-jineho-232/", nothing) == ""
    # A purely numeric segment still names nothing at all.
    assert rpl.slug_names_row("https://www.school.cz/programy/232/", names_row) == ""


def test_a_faculty_sitemap_binds_the_rows_the_catalogue_never_named() -> None:
    """AMU's faculty sitemaps list every programme page, code and all.

    The DAMU admission catalogue the school was configured with names a handful of
    programmes; famu.cz/sitemap-programs.xml, hamu.cz/sitemap-programs.xml and
    damu.cz/sitemap-programs.xml together list 277 programme pages, each with the
    school's own code at the end of its slug and a Czech and an English twin. None
    of them was a candidate before, because the slug was read with the code still
    attached and so named no register row at all.
    """
    target = school_target("amu.cz")
    target["extraDomains"] = ["amu.cz", "damu.cz", "famu.cz", "hamu.cz"]
    target["allowedDomains"] = ["amu.cz", "damu.cz", "famu.cz", "hamu.cz"]
    target["entryUrls"] = ["https://www.damu.cz/sitemap-programs.xml"]
    rows = [
        row("msmt-vs_00000", "Animovaná tvorba", "b", "cs"),
        row("msmt-vs_00000", "Animovaná tvorba", "m", "cs"),
    ]

    def sitemap(host: str, path: str, code: str) -> str:
        return (
            "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"
            f"<url><loc>https://{host}{path}-{code}/</loc></url>"
            "</urlset>"
        )

    body = (
        sitemap("www.damu.cz", "/cs/katedry-programy/katedra-kamery/studijni-programy/animovana-tvorba", "232")
        + sitemap("www.damu.cz", "/en/department/x/study-programs/animated-film", "232")
        + sitemap("www.damu.cz", "/cs/katedry-programy/katedra-zvuku/studijni-programy/neznamy-program", "999")
    )
    fetch = FakeFetch(
        {"https://www.damu.cz/sitemap-programs.xml": (200, body)},
        default=(200, "<html><body></body></html>"),
    )
    throttled = rpl.ThrottledFetch(fetch, sleep=lambda _seconds: None)
    match = rpl.Match(rows)
    candidates, _notes = rpl.discover_candidates(
        target,
        throttled,
        rpl.Limits(),
        rpl.Budget(60),
        interesting=lambda key: key in match.by_title,
    )
    by_title = {candidate.title: candidate for candidate in candidates}
    # The Czech slug names the register row once its code is removed; the English
    # twin names a row the register does not carry and stays out.
    assert "animovana tvorba" in by_title
    assert (
        by_title["animovana tvorba"].url
        == "https://www.damu.cz/cs/katedry-programy/katedra-kamery/studijni-programy/animovana-tvorba-232/"
    )
    assert "animated film" not in by_title
    assert all(candidate.matched_by == "school_catalogue_sitemap" for candidate in candidates)

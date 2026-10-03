from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import programme_catalogues as pc  # noqa: E402
import resolve_programme_links as resolver  # noqa: E402

MUNI_CS = (
    "<title>Fyzika – bakalářské studium | Masarykova univerzita | MUNI</title>"
    "<main><h1>Fyzika</h1><p>Informace o studiu</p><dl><dt>Zajišťuje</dt><dd>Přírodovědecká fakulta</dd>"
    "<dt>Typ studia</dt><dd>bakalářský</dd><dt>Forma</dt><dd>prezenční ano kombinovaná ne distanční ne</dd>"
    "<dt>Doba studia</dt><dd>3 roky</dd><dt>Vyučovací jazyk</dt><dd>čeština</dd></dl></main>"
)
MUNI_EN = (
    "<title>Finance – master's studies | Masaryk University | MUNI</title>"
    "<p>Provided by Faculty of Economics and Administration Type of studies Follow-up master's "
    "Mode full-time Yes combined No distance No Standard length of studies 2 years "
    "Language of instruction English Tuition fees The studies are subject to tuition, fees are paid "
    "per academic year 120,000 CZK Find out more</p>"
)


def test_muni_programme_pages_state_level_faculty_and_language() -> None:
    cs = pc.parse_muni_programme(MUNI_CS, "https://www.muni.cz/bakalarske-a-magisterske-studijni-programy/23626-fyzika")
    assert cs["titles"] == {"cs": "Fyzika"}
    assert (cs["degree"], cs["studyLanguage"], cs["faculty"]) == ("bachelor", "cs", "Přírodovědecká fakulta")
    assert cs["studyForms"] == ["full-time"] and cs["standardYears"] == "3"
    en = pc.parse_muni_programme(MUNI_EN, "https://www.muni.cz/en/bachelors-and-masters-study-programmes/23071-finance")
    assert en["titles"] == {"en": "Finance"}
    assert (en["degree"], en["studyLanguage"], en["faculty"]) == ("master", "en", "Ekonomicko-správní fakulta")
    assert en["tuitionText"].endswith("120,000 CZK")
    assert pc.parse_muni_programme("<title>Study programme | Masaryk University</title>", "https://www.muni.cz/x/1-y") is None


def test_muni_listing_links_stay_inside_their_catalogue() -> None:
    html = (
        '<a href="/bakalarske-a-magisterske-studijni-programy/matematika-a-fyzika">cat</a>'
        '<a href="/bakalarske-a-magisterske-studijni-programy/23452-matematika">p</a>'
        '<a href="/uchazeci/doktorske-studium/vyberte-si-program/23434-vnitrni-lekarstvi">other catalogue</a>'
        '<a href="https://example.org/bakalarske-a-magisterske-studijni-programy/1234-x">foreign</a>'
    )
    programmes, categories = pc.muni_listing_links(html, "https://www.muni.cz/bakalarske-a-magisterske-studijni-programy")
    assert programmes == ["https://www.muni.cz/bakalarske-a-magisterske-studijni-programy/23452-matematika"]
    assert categories == ["https://www.muni.cz/bakalarske-a-magisterske-studijni-programy/matematika-a-fyzika"]


def test_cvut_bila_kniha_lists_programmes_under_level_headings() -> None:
    html = (
        "<h1>Fakulta dopravní - Děčín</h1><p><em>Bakalářské:</em></p><ul>"
        '<li><a href="program1.html">Dopravní systémy</a></li>'
        '<li><a href="program2.html">Smart Cities</a> (výuka v&nbsp;angličtině)</li></ul>'
        "<p><em>Doktorské:</em></p><ul><li><a href=\"program3.html\">Inženýrská informatika</a></li></ul>"
    )
    rows = pc.parse_cvut_faculty(html, "https://bilakniha.cvut.cz/cs/f6d.html")
    assert [(r["titles"]["original"], r["degree"], r["studyLanguage"]) for r in rows] == [
        ("Dopravní systémy", "bachelor", "cs"),
        ("Smart Cities", "bachelor", "en"),
        ("Inženýrská informatika", "doctorate", "cs"),
    ]
    assert rows[0]["faculty"] == "Fakulta dopravní"
    assert rows[0]["officialProgrammeUrl"] == "https://bilakniha.cvut.cz/cs/program1.html"


def test_slu_finder_variants_carry_level_and_faculty() -> None:
    html = (
        '<div class="panel-group"><h2><div style="display: inline;" title="Studijní obor/plán">Historie</div></h2>'
        '<a id="issu-N-P" class="link2issu" title="Fakulta: FPF&lt;br&gt;Program: HISTORIE" data-toggle="tooltip" '
        'href="https://is.slu.cz/program/1082?lang=cs">Magisterské studium (prezenční)</a>'
        '<a id="issu-B-K" class="link2issu" title="Fakulta: FPF" href="https://is.slu.cz/program/1083?lang=cs">B</a></div>'
    )
    rows = pc.parse_slu_finder(html, "cs")
    assert {(r["officialProgrammeUrl"], r["degree"]) for r in rows} == {
        ("https://is.slu.cz/program/1082?lang=cs", "master"),
        ("https://is.slu.cz/program/1083?lang=cs", "bachelor"),
    }
    assert all(r["faculty"] == "Filozoficko-přírodovědecká fakulta v Opavě" for r in rows)


def test_stag_records_keep_currently_accredited_programmes_only() -> None:
    programmes = [
        {"stprIdno": 1, "nazev": "Food Safety", "typ": "Bakalářský", "jazyk": "Angličtina", "fakulta": "FVH", "neplatnyOd": None, "kod": "B1"},
        {"stprIdno": 2, "nazev": "Old", "typ": "Navazující", "jazyk": "Čeština", "fakulta": "FVH", "neplatnyOd": "2024"},
        {"stprIdno": 3, "nazev": "Lost", "typ": "Doktorský", "jazyk": "Čeština", "fakulta": "FVH", "akreditaceZtracenaOdDate": {"value": "1.1.2025"}},
        {"stprIdno": 4, "nazev": "Ochrana", "typ": "Celoživotní", "jazyk": "Čeština", "fakulta": "REK"},
        {"stprIdno": 5, "nazev": "Životní prostředí", "typ": "Doktorský", "jazyk": "Čeština", "fakulta": "FŽP", "neplatnyOd": "2029"},
    ]
    rows = pc.stag_records(programmes, {"FVH": "Fakulta veterinární hygieny"}, "https://stagweb.vfu.cz/ects", 2026)
    assert [r["officialProgrammeUrl"] for r in rows] == [
        "https://stagweb.vfu.cz/ects/browser/FVH/1?lang=en",
        "https://stagweb.vfu.cz/ects/browser/F%C5%BDP/5?lang=cs",
    ]
    assert rows[0]["faculty"] == "Fakulta veterinární hygieny" and rows[0]["degree"] == "bachelor"


def test_a_stated_faculty_separates_same_titled_register_rows() -> None:
    rows = [
        resolver.Row("r1", "s", "Sociální práce", "b", "cs", "Filozofická fakulta"),
        resolver.Row("r2", "s", "Sociální práce", "b", "cs", "Cyrilometodějská teologická fakulta"),
    ]
    match = resolver.Match(rows)
    plain = resolver.Candidate(url="https://x.cz/a", title="Sociální práce", degree="b", language="cs")
    assert match.bind(plain).reason == "ambiguous_register_rows"
    stated = resolver.Candidate(url="https://x.cz/a", title="Sociální práce", degree="b", language="cs", faculty="Filozofická fakulta")
    assert [row.ident for row in match.bind(stated).rows] == ["r1"]


def test_uis_level_page_rows_carry_code_language_and_info_page() -> None:
    html = (
        '<table><tr><td class="odsazena">Fakulta: </td><td class="odsazena">Agronomická fakulta</td></tr>'
        '<tr><td class="odsazena">Typ studia: </td><td class="odsazena">Magisterský navazující</td></tr></table>'
        "<b>Výběr studijního programu</b><table><thead><tr><th>Kód</th></tr></thead><tbody >"
        '<tr class=" uis-hl-table lbn" ><td>N0811A370020</td><td>N-AEG Agroekologie</td><td>Čeština</td>'
        '<td><a href="/katalog/plany.pl?fakulta=14;poc_obdobi=824;typ_studia=4;program=2077;info=1;lang=cz">i</a></td></tr>'
        '<tr><td>N0811A370016</td><td>N-GAE General Agriculture</td><td>Angličtina</td>'
        '<td><a href="/katalog/plany.pl?fakulta=14;poc_obdobi=824;typ_studia=4;program=2070;info=1;lang=cz">i</a></td></tr>'
        "</tbody></table>"
    )
    rows = pc.uis_programmes(html, "https://is.mendelu.cz/katalog/plany.pl?fakulta=14;poc_obdobi=824;typ_studia=4;lang=cz")
    assert [(r["titles"]["original"], r["degree"], r["studyLanguage"], r["programmeCode"]) for r in rows] == [
        ("Agroekologie", "master", "cs", "N0811A370020"),
        ("General Agriculture", "master", "en", "N0811A370016"),
    ]
    assert rows[0]["faculty"] == "Agronomická fakulta"
    assert rows[0]["officialProgrammeUrl"].startswith("https://is.mendelu.cz/katalog/plany.pl?fakulta=14;")


def test_uis_periods_of_the_current_academic_year_only() -> None:
    html = (
        '<tr><td><b>ZS 2026/2027</b></td><td><a href="/katalog/plany.pl?fakulta=14;poc_obdobi=824;lang=cz">x</a></td></tr>'
        '<tr><td>2026/2027 - doktorská studia</td><td><a href="/katalog/plany.pl?fakulta=14;poc_obdobi=825;lang=cz">x</a></td></tr>'
        '<tr><td>ZS 2025/2026</td><td><a href="/katalog/plany.pl?fakulta=14;poc_obdobi=700;lang=cz">x</a></td></tr>'
    )
    links = pc.uis_period_links(html, "https://is.mendelu.cz/katalog/plany.pl?fakulta=14;;lang=cz", 2026)
    assert [link.split("poc_obdobi=")[1][:3] for link in links] == ["824", "825"]


def test_faculty_probe_binds_the_row_the_page_says_provides_it() -> None:
    rows = [
        resolver.Row("lf1", "s", "General Medicine", "m", "en", "1. lékařská fakulta"),
        resolver.Row("lf3", "s", "General Medicine", "m", "en", "3. lékařská fakulta"),
    ]
    match = resolver.Match(rows)
    pages = {
        "https://is.cuni.cz/a/1": "<p>Související akreditace Fakulta Název 3. lékařská fakulta</p><p>Zajištění výuky Fakulta: 1. lékařská fakulta (1LF)</p>",
        "https://is.cuni.cz/a/2": "<p>Fakulta Název 1. lékařská fakulta 3. lékařská fakulta</p>",
    }
    candidates = [resolver.Candidate(url=url, title="General Medicine", language="en") for url in pages]
    unresolved = {"lf1": "ambiguous_register_rows", "lf3": "ambiguous_register_rows"}
    fetch = resolver.ThrottledFetch(lambda url: (200, pages[url]), sleep=lambda _s: None)
    probed, _notes = resolver.probe_faculties(
        match, unresolved, {resolver.normalise("General Medicine"): candidates}, fetch, resolver.Limits(), resolver.Budget(60)
    )
    assert list(probed) == ["lf1"]
    assert probed["lf1"][0][0].url == "https://is.cuni.cz/a/1"
    assert unresolved == {"lf3": "ambiguous_register_rows"}


def test_a_page_on_another_faculty_site_is_not_bound() -> None:
    rows = {
        "a": resolver.Row("a", "s", "Pediatrie", "d", "cs", "2. lékařská fakulta"),
        "b": resolver.Row("b", "s", "Radiologie", "d", "cs", "2. lékařská fakulta"),
        "c": resolver.Row("c", "s", "Historie", "b", "cs", "Filozofická fakulta"),
    }
    page = lambda url: resolver.Candidate(url=url, title="x")
    grouped = {
        "a": [(page("https://www.lf2.cuni.cz/uchazeci/pediatrie"), "cs")],
        "b": [(page("https://www.lf2.cuni.cz/uchazeci/radiologie"), "cs")],
        "c": [(page("https://www.lf2.cuni.cz/fakulta/o-fakulte/historie"), "cs")],
    }
    assert resolver.faculty_sites(grouped, rows) == {"www.lf2.cuni.cz": "2. lékařská fakulta"}
    # A university-wide catalogue with several rows of several faculties is nobody's.
    central = {key: [(page(f"https://is.cuni.cz/{key}"), "cs")] for key in rows}
    central["d"] = [(page("https://is.cuni.cz/d"), "cs")]
    rows["d"] = resolver.Row("d", "s", "Archeologie", "b", "cs", "Filozofická fakulta")
    assert resolver.faculty_sites(central, rows) == {}


def test_a_refresh_stub_is_read_again_in_its_cookie_session() -> None:
    from engine.transport import fetch_official_page, is_refresh_stub

    stub = '<!DOCTYPE HTML><html><head><title></title><meta http-equiv="refresh" content="1"></head><body></body></html>'
    page = "<html><head><title>Historie</title></head><body><h1>Historie</h1>" + "x" * 3000 + "</body></html>"
    assert is_refresh_stub(stub) and not is_refresh_stub(page)
    result = fetch_official_page(
        "https://is.slu.cz/program/1082?lang=cs",
        ordinary=lambda url: (200, stub),
        cookie_get=lambda url: (200, page),
        allow_browser=False,
    )
    assert result.body == page


def test_stag_page_must_name_its_programme() -> None:
    assert pc.stag_page_names("<h1>Studijní plány: Bezpečnost a kvalita potravin</h1>", "Bezpečnost a kvalita potravin")
    assert not pc.stag_page_names("<html><body></body></html>", "Bezpečnost a kvalita potravin")


def test_amu_programme_page_states_name_and_level() -> None:
    html = '<section class="school-program-detail"><h1 id="nazev">Bicí nástroje</h1> <p id="typ_programu"><i>Bakalářský</i></p></section>'
    row = pc.parse_amu_programme(html, "https://www.hamu.cz/cs/katedry-programy/katedra-bicich-nastroju/studijni-programy/bici-nastroje-206/")
    assert (row["titles"]["original"], row["degree"], row["faculty"]) == ("Bicí nástroje", "bachelor", "Hudební a taneční fakulta")
    assert pc.parse_amu_programme("<h1>Kontakt</h1>", "https://www.hamu.cz/cs/kontakt/") is None


def test_vsb_lists_carry_level_language_and_faculty() -> None:
    cs = (
        "<h2>Bakalářské programy</h2><ul><li><a class='show-tooltip' href='.?programmeId=764&academicYearId=66&studyLanguageIds=1'>"
        "<span class='text'>Aplikovaná elektronika</span></a><span class='faculty show-tooltip'>&nbsp;(FEI)&nbsp;</span></li></ul>"
        "<h2>Doktorské programy</h2><ul><li><a href='.?programmeId=900&academicYearId=66&studyLanguageIds=1'>"
        "<span class='text'>Informatika</span></a><span class='faculty show-tooltip'>&nbsp;(FEI)&nbsp;</span></li></ul>"
    )
    rows = pc.parse_vsb_cs(cs, pc.VSB_LIST_CS)
    assert [(r["titles"]["original"], r["degree"], r["faculty"]) for r in rows] == [
        ("Aplikovaná elektronika", "bachelor", "Fakulta elektrotechniky a informatiky"),
        ("Informatika", "doctorate", "Fakulta elektrotechniky a informatiky"),
    ]
    assert rows[0]["officialProgrammeUrl"] == "https://www.vsb.cz/cs/uchazec/studijni-programy/?programmeId=764&academicYearId=66&studyLanguageIds=1"
    en = (
        "<h2>Faculty of Mining and Geology</h2><div><ul><li><a href='/en/study/degree-students/degree-studies/bachelor-degree/"
        "bachelor-degree-detail/?programmeId=1126'><span class='text'>Applied  Geology</span></a></li></ul></div>"
    )
    row = pc.parse_vsb_en(en, pc.VSB_LISTS_EN["bachelor"], "bachelor")[0]
    assert (row["titles"]["original"], row["studyLanguage"], row["faculty"]) == ("Applied Geology", "en", "Hornicko-geologická fakulta")


def test_vscht_level_comes_from_the_programme_code() -> None:
    assert pc.vscht_level("B") == "bachelor" and pc.vscht_level("an") == "master" and pc.vscht_level("D") is None
    assert pc.vscht_title("<title>Fuel Cells and Hydrogen Engineering AN110 - Study at UCT Prague</title>", "en") == "Fuel Cells and Hydrogen Engineering"
    assert pc.vscht_title("<title>Program | Studuj VŠCHT</title><h1>\n Chemie \n</h1>", "cs") == "Chemie"

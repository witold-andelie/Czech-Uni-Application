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

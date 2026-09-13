from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from harvest_hei_coordinates import clean_seat, match_row, parse_point, postcodes_match, seat_variants  # noqa: E402


def test_clean_seat_drops_po_box() -> None:
    assert "P.O.Box" not in clean_seat("Lhotecká 559/7 P.O.Box 54 Kamýk 143 01 Praha 4")
    assert clean_seat("Zemědělská 1/1665, 613 00 Brno") == "Zemědělská 1/1665, 613 00 Brno"


def test_postcode_rejects_other_prague_district() -> None:
    seat = "Vinohradská 1597/14, Vinohrady, 130 00 Praha 3"
    assert postcodes_match(seat, "130 00")
    assert postcodes_match(seat, "13000")
    assert not postcodes_match(seat, "120 00")


def test_seat_variants_split_czech_house_numbers() -> None:
    variants = seat_variants("Zemědělská 1/1665, 613 00 Brno")
    assert "Zemědělská 1665, 613 00 Brno" in variants
    assert "Zemědělská 1, 613 00 Brno" in variants
    vsb = seat_variants("17. listopadu 15/2172 708 33 Ostrava-Poruba")
    assert "17. listopadu 2172 708 33 Ostrava-Poruba" in vsb
    adi = seat_variants("Vinohradská 1597/14, Vinohrady, 130 00 Praha 3")
    assert any("vinohradska 14" in row and "vinohrady" not in row for row in adi)
    vsfs = seat_variants("Estonská 500 Vršovice 101 00 Praha 10")
    assert any(row.startswith("estonska 500") and "vrsovice" not in row for row in vsfs)


def test_parse_point_keeps_czechia_and_drops_out_of_range() -> None:
    assert parse_point("Point(14.42076 50.08781)") == (50.08781, 14.42076)
    assert parse_point("Point(13.4 52.5)") is None
    assert parse_point("") is None


def test_match_prefers_ico_and_does_not_guess_ambiguous_names() -> None:
    rows = [
        {
            "qid": "Q31519",
            "url": "https://www.wikidata.org/wiki/Q31519",
            "labelCs": "Univerzita Karlova",
            "labelEn": "Charles University",
            "ico": "00216208",
            "website": "https://www.cuni.cz",
            "lat": 50.087,
            "lon": 14.421,
        },
        {
            "qid": "Q1",
            "url": "https://www.wikidata.org/wiki/Q1",
            "labelCs": "Univerzita Karlova",
            "labelEn": "Other",
            "ico": "999",
            "website": "",
            "lat": 50.1,
            "lon": 14.4,
        },
    ]
    hit = match_row({"officialName": "Univerzita Karlova", "ico": "00216208"}, rows)
    assert hit is not None
    assert hit["match"] == "ico"
    assert hit["qid"] == "Q31519"
    ambiguous = match_row({"officialName": "Univerzita Karlova", "ico": ""}, rows)
    assert ambiguous is None
    host_hit = match_row(
        {"officialName": "Other", "ico": "", "officialUrl": "https://www.cuni.cz"},
        rows,
    )
    assert host_hit is not None
    assert host_hit["match"] == "website"

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from build_nine_hei_inventory import build_compact, compact_row, row_id, years_of  # noqa: E402


def test_stable_id_and_years() -> None:
    ident = row_id("msmt-vs_11000", "Computer Science", "bachelor", "en", "Matematicko-fyzikální fakulta")
    assert ident.startswith("inv-")
    assert len(ident) == 16
    assert years_of("3") == 3
    assert years_of("2,5") == 2.5
    assert years_of("3.5") == 3.5
    assert years_of("4, 1") is None
    assert years_of("") is None


def test_compact_row_keeps_original_title() -> None:
    row = compact_row(
        "msmt-vs_11000",
        {
            "titleOriginal": "Computer Science",
            "degree": "bachelor",
            "facultyName": "Matematicko-fyzikální fakulta",
            "standardYears": "3",
            "teachingLanguage": "en",
            "iscedF": "0613",
        },
    )
    assert row is not None
    assert row[1] == "Computer Science"
    assert row[2] == "b"
    assert row[5] == "en"


def test_compact_payload_is_inventory_not_admissions() -> None:
    payload = build_compact(
        [
            {
                "id": "msmt-vs_11000",
                "rows": [
                    [
                        "inv-test",
                        "Computer Science",
                        "b",
                        "Matematicko-fyzikální fakulta",
                        3,
                        "en",
                        "0613",
                    ]
                ],
            }
        ],
        generated_at="2026-09-06T00:00:00Z",
    )
    assert payload["dataClass"] == "official_register_extract"
    assert payload["catalogKind"] == "browse_with_inventory"
    assert payload["academicYear"] == "register"
    assert payload["counts"]["programmes"] == 1
    dumped = json.dumps(payload["schools"])
    assert "opensAt" not in dumped
    assert "tuition" not in dumped


def test_programme_link_must_sit_on_the_row_owners_domain(tmp_path: Path, monkeypatch) -> None:
    """An index entry's own institutionId does not choose the allowed domains.

    Both publication gates bind a link to the school that owns the row; the
    build must do the same, so a mis-attributed link is dropped and counted
    here rather than blocking the whole snapshot later.
    """
    import build_nine_hei_inventory as inventory
    import resolve_programme_links

    index = tmp_path / "programme-links.json"
    index.write_text(
        json.dumps(
            {
                "generatedAt": "2026-09-29T00:00:00Z",
                "links": {
                    "inv-cuni-own": {
                        "url": "https://www.mff.cuni.cz/en/admissions/informatics",
                        "institutionId": "msmt-vs_11000",
                        "reachability": "verified",
                    },
                    # Row belongs to Charles University, but the entry claims
                    # Masaryk University and points at a muni.cz page.
                    "inv-cuni-misattributed": {
                        "url": "https://www.muni.cz/en/bachelors-degree-programmes/informatics",
                        "institutionId": "msmt-vs_14000",
                        "reachability": "verified",
                    },
                    "inv-not-a-row": {
                        "url": "https://www.cuni.cz/programme",
                        "institutionId": "msmt-vs_11000",
                        "reachability": "verified",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(inventory, "PROGRAMME_LINKS", index)
    monkeypatch.setattr(
        resolve_programme_links,
        "allowed_domains_by_institution",
        lambda: {"msmt-vs_11000": {"cuni.cz"}, "msmt-vs_14000": {"muni.cz"}},
    )
    row = ["", "Informatics", "b", "MFF", 3, "en", "0613"]
    payload = {
        "schools": [
            {"id": "msmt-vs_11000", "rows": [["inv-cuni-own", *row[1:]], ["inv-cuni-misattributed", *row[1:]]]},
            {"id": "msmt-vs_14000", "rows": []},
        ],
        "counts": {},
    }
    stamped, report = inventory.stamp_programme_links(payload)

    assert set(stamped["programmeLinks"]) == {"inv-cuni-own"}
    assert stamped["counts"]["linkedProgrammes"] == 1
    assert report["droppedForeignDomain"] == 1
    assert report["droppedUnknownRow"] == 1


def test_a_programme_the_portal_lists_twice_keeps_the_page_it_was_matched_to() -> None:
    """2026-10-10: studyin.gov.cz gave 78 programmes a second page (most of them
    Charles University's, under an English address); "exactly one match"
    dropped their facts. The page proven before still decides, if it is one of
    the matches; a page the portal removed is not kept, and nothing is guessed."""
    from build_nine_hei_inventory import STUDYIN_PREFIX, programme_details

    schools = [{"id": "msmt-vs_11000", "rows": [
        ["inv-geo", "Aplikovaná geografie", "b", "Přírodovědecká fakulta", 3, "cs", "0532"],
        ["inv-gone", "Geologie", "b", "Přírodovědecká fakulta", 3, "cs", "0532"],
    ]}]

    def record(slug: str, title: str, forms: list[str]) -> dict:
        return {"institutionId": "msmt-vs_11000", "degree": "b", "studyLanguage": "cs", "titles": {"cs": title},
                "facultyNames": {"cs": "Přírodovědecká fakulta"}, "city": "Praha", "studyForms": {"en": forms},
                "officialDirectoryUrl": f"{STUDYIN_PREFIX}charles-university/{slug}"}

    studyin = {"programmes": [
        record("aplikovana-geografie", "Aplikovaná geografie", ["full-time"]),
        record("applied-geography", "Aplikovaná geografie", ["full-time", "combined"]),
        record("geologie-1", "Geologie", []),
        record("geology", "Geologie", ["full-time"]),
    ]}
    previous = {
        "inv-geo": ["Praha", "P", None, None, None, "charles-university/aplikovana-geografie"],
        "inv-gone": ["Praha", "P", None, None, None, "charles-university/geologie"],
    }
    assert programme_details(schools, studyin) == {}
    details = programme_details(schools, studyin, previous)
    assert list(details) == ["inv-geo"]
    assert details["inv-geo"][5] == "charles-university/aplikovana-geografie"

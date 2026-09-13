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

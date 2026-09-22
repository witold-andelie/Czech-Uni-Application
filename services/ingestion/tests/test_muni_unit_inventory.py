from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "data" / "sources" / "coverage" / "muni-unit-inventory.json"
REGISTRY = ROOT / "data" / "sources" / "registry.json"
FACULTIES = ROOT / "data" / "sources" / "msmt-faculties.json"

REQUIRED_MSMT_FACULTIES = {
    "Právnická fakulta",
    "Lékařská fakulta",
    "Přírodovědecká fakulta",
    "Filozofická fakulta",
    "Pedagogická fakulta",
    "Farmaceutická fakulta",
    "Ekonomicko-správní fakulta",
    "Fakulta informatiky",
    "Fakulta sociálních studií",
    "Fakulta sportovních studií",
}

STRUCTURE_UNITS = {
    "Archiv Masarykovy univerzity",
    "Centrum jazykového vzdělávání",
    "Centrum pro transfer technologií",
    "Centrum rozvoje pedagogických kompetencí",
    "Centrum zahraniční spolupráce",
    "Kariérní centrum",
    "Kulturní centrum",
    "Mendelovo muzeum",
    "Nakladatelství Munipress",
    "Rektorát",
    "Správa kolejí a menz",
    "Správa Univerzitního kampusu Bohunice",
    "Středisko pro pomoc studentům se specifickými nároky",
    "Středoevropský technologický institut CEITEC",
    "Univerzitní centrum Telč",
    "Ústav výpočetní techniky",
}


def test_muni_unit_inventory_does_not_claim_institution_wide_jobs() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    faculties = json.loads(FACULTIES.read_text(encoding="utf-8"))
    muni_jobs = next(item for item in registry if item.get("id") == "muni-careers")
    raw_msmt = [
        item["officialName"]
        for item in faculties["faculties"]
        if item.get("institutionId") == "msmt-vs_14000" and item["officialName"] != "Celoškolská pracoviště"
    ]
    msmt_names = set(raw_msmt)

    assert payload["institutionId"] == "msmt-vs_14000"
    assert payload["centralJobsSource"]["sourceCoverageClaim"] == "not_asserted"
    assert payload["centralJobsSource"]["institutionWideClaimFound"] is False
    assert muni_jobs["sourceCoverageClaim"] == "not_asserted"
    assert muni_jobs["unitInventory"] == "data/sources/coverage/muni-unit-inventory.json"

    names = {item["officialName"] for item in payload["units"]}
    assert REQUIRED_MSMT_FACULTIES <= names
    # The only MŠMT duplicate is Farmaceutická fakulta (rid 14160).
    assert len(raw_msmt) == len(msmt_names) + 1
    assert msmt_names == REQUIRED_MSMT_FACULTIES
    assert STRUCTURE_UNITS <= names
    assert "Celoškolská pracoviště" in names
    assert all(item["centralJobsSourceIncludesClaim"] is False for item in payload["units"])

    # Every named unit maps to the correct MŠMT bucket.
    muni_units = {item["officialName"]: item for item in payload["units"]}
    assert len(muni_units) == 27
    for name in STRUCTURE_UNITS:
        assert muni_units[name]["msmtFacultyRid"] == "14900"

    # A unit named on the structure page but omitted from the central filter
    # keeps the central source from being institution-wide by construction.
    assert "Kulturní centrum" in names
    assert payload["centralJobsSource"]["claimEvidence"]
    assert payload["unresolved"]
    assert payload["counts"]["officialStructureUnits"] == 26
    assert payload["counts"]["centralCareersFilterUnits"] == 25
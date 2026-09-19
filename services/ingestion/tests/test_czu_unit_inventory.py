from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "data" / "sources" / "coverage" / "czu-unit-inventory.json"
REGISTRY = ROOT / "data" / "sources" / "registry.json"
FACULTIES = ROOT / "data" / "sources" / "msmt-faculties.json"

REQUIRED_MSMT_FACULTIES = {
    "Provozně ekonomická fakulta",
    "Fakulta agrobiologie, potravinových a přírodních zdrojů",
    "Technická fakulta",
    "Fakulta lesnická a dřevařská",
    "Fakulta životního prostředí",
    "Fakulta tropického zemědělství",
}


def test_czu_unit_inventory_does_not_claim_institution_wide_jobs() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    faculties = json.loads(FACULTIES.read_text(encoding="utf-8"))
    czu_jobs = next(item for item in registry if item.get("id") == "czu-central-jobs")
    msmt_names = {
        item["officialName"]
        for item in faculties["faculties"]
        if item.get("institutionId") == "msmt-vs_41000" and item["officialName"] != "Celoškolská pracoviště"
    }

    assert payload["institutionId"] == "msmt-vs_41000"
    assert payload["centralJobsSource"]["sourceCoverageClaim"] == "not_asserted"
    assert payload["centralJobsSource"]["institutionWideClaimFound"] is False
    assert czu_jobs["sourceCoverageClaim"] == "not_asserted"
    assert czu_jobs["unitInventory"] == "data/sources/coverage/czu-unit-inventory.json"

    names = {item["officialName"] for item in payload["units"]}
    assert REQUIRED_MSMT_FACULTIES <= names
    assert msmt_names == REQUIRED_MSMT_FACULTIES
    assert "Institut vzdělávání a poradenství" in names
    assert payload["counts"]["unitsWithSeparateVacancySource"] == 0
    assert all(item["centralJobsSourceIncludesClaim"] is False for item in payload["units"])
    assert all(item.get("separateVacancySourceId") is None for item in payload["units"])
    assert payload["unresolved"]
    observed = [item for item in payload["units"] if item.get("currentVacancyObservedOnCentralPortal")]
    assert {item["officialName"] for item in observed} == {"Technická fakulta"}

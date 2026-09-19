from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "data" / "sources" / "coverage" / "cuni-unit-inventory.json"
REGISTRY = ROOT / "data" / "sources" / "registry.json"
FACULTIES = ROOT / "data" / "sources" / "msmt-faculties.json"

REQUIRED_MSMT_FACULTIES = {
    "1. lékařská fakulta",
    "2. lékařská fakulta",
    "3. lékařská fakulta",
    "Evangelická teologická fakulta",
    "Fakulta sociálních věd",
    "Fakulta tělesné výchovy a sportu",
    "Farmaceutická fakulta v Hradci Králové",
    "Filozofická fakulta",
    "Husitská teologická fakulta",
    "Katolická teologická fakulta",
    "Lékařská fakulta v Hradci Králové",
    "Lékařská fakulta v Plzni",
    "Matematicko-fyzikální fakulta",
    "Pedagogická fakulta",
    "Právnická fakulta",
    "Přírodovědecká fakulta",
}


def test_cuni_unit_inventory_does_not_claim_institution_wide_jobs() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    faculties = json.loads(FACULTIES.read_text(encoding="utf-8"))
    cuni_jobs = next(item for item in registry if item.get("id") == "cuni-central-open-positions")
    msmt_names = {
        item["officialName"]
        for item in faculties["faculties"]
        if item.get("institutionId") == "msmt-vs_11000" and item["officialName"] not in {"", "Celoškolská pracoviště"}
    }

    assert payload["institutionId"] == "msmt-vs_11000"
    assert payload["centralJobsSource"]["sourceCoverageClaim"] == "not_asserted"
    assert payload["centralJobsSource"]["institutionWideClaimFound"] is False
    assert cuni_jobs["sourceCoverageClaim"] == "not_asserted"
    assert cuni_jobs["unitInventory"] == "data/sources/coverage/cuni-unit-inventory.json"

    names = {item["officialName"] for item in payload["units"]}
    assert REQUIRED_MSMT_FACULTIES <= names
    assert msmt_names == REQUIRED_MSMT_FACULTIES
    assert "Fakulta humanitních studií" in names
    assert all(item["centralJobsSourceIncludesClaim"] is False for item in payload["units"])
    assert payload["unresolved"]
    observed = {item["officialName"] for item in payload["units"] if item.get("currentVacancyObservedOnCentralPortal")}
    assert observed == {
        "Matematicko-fyzikální fakulta",
        "Přírodovědecká fakulta",
        "Filozofická fakulta",
        "Lékařská fakulta v Plzni",
    }
    mff = next(item for item in payload["units"] if item["officialName"] == "Matematicko-fyzikální fakulta")
    assert mff["separateVacancySourceId"] == "mff-job-opportunities"

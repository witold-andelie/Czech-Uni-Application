from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from parse_muni_fi import build

def test_muni_tracer_invariants():
    snapshot = build()
    assert snapshot["catalogKind"] == "tracer_not_published"
    assert snapshot["institutionId"] == "msmt-vs_14000"
    en = next(item for item in snapshot["offerings"] if item["id"] == "muni-fi-vi-en-2026")
    cs = next(item for item in snapshot["offerings"] if item["id"] == "muni-fi-inf-cs-2026")
    assert en["teachingLanguages"] == ["en"]
    assert en["degree"] == "master"
    assert cs["teachingLanguages"] == ["cs"]
    assert cs["degree"] == "bachelor"
    assert {item["id"] for item in en["windows"]} == {
        "win-muni-fi-vi-en-sep-2026",
        "win-muni-fi-vi-en-feb-2027",
    }
    assert en["windows"][0]["opensAt"] == "2025-12-15"
    assert en["windows"][0]["closesAt"] == "2026-04-15"
    assert en["windows"][1]["opensAt"] == "2026-06-15"
    assert en["windows"][1]["closesAt"] == "2026-10-15"
    assert en["windows"][0]["roundNumber"] is None
    assert cs["window"]["opensAt"] == "2025-11-01"
    assert cs["window"]["closesAt"] == "2026-02-28"
    assert en["tuition"]["published"] is True
    assert en["tuition"]["amount"] == 4500
    assert cs["tuition"]["published"] is True
    assert cs["tuition"]["amount"] == 0
    assert en["applicationFee"]["amount"] is None
    assert cs["applicationFee"]["amount"] is None
    assert en["applicationFee"]["isNotTuition"] is True
    assert "prihlaska" in en["applicationUrl"]
    assert "prihlaska" in cs["applicationUrl"]


if __name__ == "__main__":
    test_muni_tracer_invariants()
    print("ok")

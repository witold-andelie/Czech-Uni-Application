from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from apply_cscse_list import LISTED, UNMATCHED, apply, listed_by_code

BASELINE = Path(__file__).resolve().parents[3] / "data" / "sources" / "msmt-hei-baseline.json"


def test_explicit_map_has_unique_codes():
    codes = [item["msmtCode"] for item in LISTED]
    assert len(codes) == 24
    assert len(set(codes)) == 24
    assert UNMATCHED[0]["msmtCode"] is None
    assert "VS_11000" in listed_by_code()


def test_apply_marks_listed_and_not_found():
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    before = {item["id"]: item["officialName"] for item in payload["institutions"]}
    applied = apply(json.loads(json.dumps(payload)))
    charles = next(item for item in applied["institutions"] if item["msmtCode"] == "VS_11000")
    defence = next(item for item in applied["institutions"] if item["msmtCode"] == "VS_95000")
    jamu = next(item for item in applied["institutions"] if item["msmtCode"] == "VS_54000")
    assert charles["cscseLookupStatus"] == "unverified"
    assert charles["cscseReference"]["lookupStatus"] == "unverified"
    assert charles["cscseReference"]["operatorListStatus"] == "listed"
    assert charles["cscseReference"]["evidenceKind"] == "operator_supplied_list"
    assert charles["cscseReference"]["listedNameZh"] == "查理大学"
    assert charles["cscseReference"]["matchConfidence"] == "exact"
    assert charles["cscseReference"]["checkedAt"] is None
    assert defence["cscseLookupStatus"] == "unverified"
    assert defence["cscseReference"]["operatorListStatus"] == "absent"
    assert jamu["cscseReference"]["listedNameEn"] == "Janáčkova akademie múzických umění v Brně"
    assert applied["cscseApply"]["matchedListed"] == 24
    assert applied["cscseApply"]["registerNotOnList"] == 30
    assert applied["cscseUnmatched"][0]["n"] == 25
    after = {item["id"]: item["officialName"] for item in applied["institutions"]}
    assert after == before


if __name__ == "__main__":
    test_explicit_map_has_unique_codes()
    test_apply_marks_listed_and_not_found()
    print("ok")

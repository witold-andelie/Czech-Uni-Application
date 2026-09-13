from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from parse_cuni_sis import build, parse_mff_costs, parse_sis

RAW = Path(__file__).resolve().parents[3] / "work" / "raw" / "2026-09-06"
EN = (RAW / "cuni-sis-cs-bachelor-en.html").read_text(encoding="utf-8")
CS = (RAW / "cuni-sis-cs-bachelor-cs.html").read_text(encoding="utf-8")
COSTS = (RAW / "cuni-mff-costs.html").read_text(encoding="utf-8")


def test_english_sis_has_close_dual_tuition_and_cannot_apply():
    parsed = parse_sis(EN, "https://is.cuni.cz/studium/eng/prijimacky/index.php?do=detail_obor&id_obor=34738", "en")
    assert parsed["sisIdObor"] == "34738"
    assert parsed["titleOriginal"] == "Computer Science"
    assert parsed["languageOriginal"] == "English"
    assert parsed["degreeOriginal"] == "Bachelor's"
    assert parsed["submissionDateIso"] == "2026-04-30"
    assert parsed["cannotApplyNow"] is True
    assert parsed["tuitionOriginal"] == "7100 EUR / year"
    assert "4200 EUR" in (parsed["tuitionNoteOriginal"] or "")
    assert parsed["applicationFeeOnlineOriginal"] == "1500 CZK"
    assert parsed["applicationFeeOnlineOriginal"] != parsed["tuitionOriginal"]


def test_czech_sis_is_current_informatika_without_tuition():
    parsed = parse_sis(CS, "https://is.cuni.cz/studium/prijimacky/index.php?do=detail_obor&id_obor=34456", "cs")
    assert parsed["sisIdObor"] == "34456"
    assert parsed["titleOriginal"] == "Informatika"
    assert parsed["languageOriginal"] == "čeština"
    assert "bakalář" in parsed["degreeOriginal"]
    assert parsed["submissionDateIso"] == "2026-03-31"
    assert parsed["cannotApplyNow"] is True
    assert parsed["hasTuitionField"] is False
    assert parsed["tuitionOriginal"] is None
    assert parsed["applicationFeeOnlineOriginal"] == "940 Kč"
    year = int(parsed["submissionDateIso"][:4])
    assert year >= 2026


def test_mff_costs_month_open_is_not_a_calendar_start():
    costs = parse_mff_costs(COSTS)
    assert costs["applicationServerOpensOriginal"] == "December 2025"
    assert costs["opensAtNotInferred"] is True
    assert costs["opensAtPrecisionIfUsed"] == "month"
    assert costs["applicationDeadlineIso"] == "2026-04-30"
    assert costs["applicationUrl"] == "https://is.cuni.cz/studium/eng/prihlaska/"


def test_tracer_snapshot_keeps_product_invariants():
    snapshot = build()
    assert snapshot["catalogKind"] == "tracer_not_published"
    assert snapshot["dataClass"] == "official_admissions_extract"
    assert snapshot["institutionId"] == "msmt-vs_11000"
    languages = {item["teachingLanguages"][0] for item in snapshot["offerings"]}
    assert languages == {"en", "cs"}
    en = next(item for item in snapshot["offerings"] if item["id"] == "cuni-mff-cs-en-2026")
    cs = next(item for item in snapshot["offerings"] if item["id"] == "cuni-mff-cs-cs-2026")
    assert en["window"]["opensAt"] is None
    assert cs["window"]["opensAt"] is None
    assert en["window"]["roundNumber"] is None
    assert cs["window"]["roundNumber"] is None
    assert en["window"]["closesAt"] == "2026-04-30"
    assert cs["window"]["closesAt"] == "2026-03-31"
    assert en["window"]["datePrecision"] == "date"
    assert en["window"]["timezone"] == "Europe/Prague"
    assert en["tuition"]["published"] is True
    assert en["tuition"]["amount"] is None
    amounts = {item["amount"] for item in en["tuition"]["variants"]}
    assert amounts == {7100, 4200}
    assert cs["tuition"]["published"] is False
    assert cs["tuition"]["amount"] is None
    assert cs["applicationFee"]["isNotTuition"] is True
    assert cs["applicationFee"]["amount"] == 940
    assert "eprihlaska" in cs["applicationUrl"]
    assert snapshot["offerings"][0]["dataClass"] != "published"


if __name__ == "__main__":
    test_english_sis_has_close_dual_tuition_and_cannot_apply()
    test_czech_sis_is_current_informatika_without_tuition()
    test_mff_costs_month_open_is_not_a_calendar_start()
    test_tracer_snapshot_keeps_product_invariants()
    print("ok")

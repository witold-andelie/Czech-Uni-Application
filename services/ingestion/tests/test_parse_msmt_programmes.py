from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from parse_msmt_programmes import parse, parse_csv

RAW_DIR = Path(__file__).resolve().parents[3] / "work" / "raw" / "2026-09-06"
RAW = RAW_DIR / "msmt-programmes-charles.html"
CSV = RAW_DIR / "msmt-programmes-charles.csv.txt"


def test_first_page_has_language_split():
    html = RAW.read_text(encoding="utf-8")
    records = parse(html)
    assert len(records) == 20
    assert any(item["teachingLanguage"] == "en" for item in records)
    assert any(item["teachingLanguage"] == "cs" for item in records)
    assert all(item["institutionName"] == "Univerzita Karlova" for item in records)
    assert all(item["msmtProgrammeCode"].startswith("SP_") for item in records)
    addictology = next(item for item in records if item["titleOriginal"] == "Addictology")
    assert addictology["teachingLanguage"] == "en"
    assert addictology["degree"] == "master"


def test_charles_csv_keeps_language_and_degree_counts():
    records = parse_csv(CSV.read_bytes().decode("cp1250"))
    assert len(records) == 925
    assert sum(item["teachingLanguage"] == "en" for item in records) == 320
    assert sum(item["teachingLanguage"] == "cs" for item in records) == 587
    assert sum(item["degree"] == "doctorate" for item in records) == 399


if __name__ == "__main__":
    test_first_page_has_language_split()
    test_charles_csv_keeps_language_and_degree_counts()
    print("ok")

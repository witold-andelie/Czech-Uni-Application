from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from parse_msmt_detail import parse_detail

RAW = Path(__file__).resolve().parent / "fixtures" / "raw-2026-09-06"


def test_charles_english_name():
    html = (RAW / "msmt-detail-charles-university.html").read_text(encoding="utf-8")
    parsed = parse_detail(html)
    assert parsed["msmtCode"] == "VS_11000"
    assert parsed["officialName"] == "Univerzita Karlova"
    assert parsed["officialNameEn"] == "Charles University"
    assert parsed["officialUrl"] == "http://www.cuni.cz"
    assert parsed["ico"] == "00216208"


def test_ambis_private_website():
    html = (RAW / "msmt-detail-ambis-private.html").read_text(encoding="utf-8")
    parsed = parse_detail(html)
    assert parsed["msmtCode"] == "VS_61000"
    assert parsed["officialNameEn"] == "AMBIS University"
    assert parsed["officialUrl"] == "http://www.ambis.cz"


if __name__ == "__main__":
    test_charles_english_name()
    test_ambis_private_website()
    print("ok")

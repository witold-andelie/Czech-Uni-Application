from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from parse_msmt_csv import parse_faculties, parse_institutions


def test_institution_csv_covers_wrapped_rows():
    records = parse_institutions()
    by_code = {item["msmtCode"]: item for item in records}
    assert len(records) == 54
    assert "VS_UNIVERZITNÍ" not in by_code
    vet = by_code["VS_16000"]
    assert vet["officialName"] == "Veterinární univerzita Brno"
    assert vet["officialUrl"] == "https://www.vfu.cz"
    assert vet["ico"] == "62157124"
    utb = by_code["VS_28000"]
    assert utb["officialName"] == "Univerzita Tomáše Bati ve Zlíně"
    assert utb["officialUrl"] == "https://www.utb.cz"
    vsaps = by_code["VS_7N000"]
    assert "aplikované psychologie" in vsaps["officialName"]
    assert vsaps["officialUrl"] == "https://www.vsaps.cz"
    mendel = by_code["VS_43000"]
    assert mendel["officialUrl"] == "https://www.mendelu.cz"
    assert all(item["officialUrl"] for item in records)


def test_faculty_csv_skips_whole_school_units():
    faculties = parse_faculties()
    assert len(faculties) >= 100
    assert all(not item["officialName"].casefold().startswith("celoškolské") for item in faculties)
    charles = [item for item in faculties if item["institutionRid"] == "11000"]
    assert any(item["officialName"].startswith("1. lékařská") for item in charles)


if __name__ == "__main__":
    test_institution_csv_covers_wrapped_rows()
    test_faculty_csv_skips_whole_school_units()
    print("ok")

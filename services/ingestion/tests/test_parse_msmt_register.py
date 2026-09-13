from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from parse_msmt_register import parse

RAW = Path(__file__).resolve().parents[3] / "work" / "raw" / "2026-09-06" / "msmt-cvslist.html"


def test_parse_counts_and_fields():
    html = RAW.read_text(encoding="utf-8")
    records = parse(html)
    assert len(records) == 54
    public = [item for item in records if item["ownership"] == "public"]
    private = [item for item in records if item["ownership"] == "private"]
    state = [item for item in records if item["ownership"] == "state"]
    assert len(public) == 26
    assert len(private) == 26
    assert len(state) == 2
    charles = next(item for item in records if item["msmtCode"] == "VS_11000")
    assert charles["officialName"] == "Univerzita Karlova"
    assert charles["ownership"] == "public"
    assert charles["legalType"] == "university"
    assert charles["cscseLookupStatus"] == "unverified"
    assert charles["officialUrl"] is None
    defence = next(item for item in records if item["msmtCode"] == "VS_95000")
    assert defence["officialName"] == "Univerzita obrany"
    assert defence["ownership"] == "state"
    ids = [item["id"] for item in records]
    assert len(ids) == len(set(ids))
    assert all(item["country"] == "CZ" for item in records)


if __name__ == "__main__":
    test_parse_counts_and_fields()
    print("ok")

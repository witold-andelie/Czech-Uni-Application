"""The scheduler imports harvest_one without running the CLI initializer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import harvest_cscse24_programmes as harvest


def test_imported_harvester_creates_evidence_directory(tmp_path, monkeypatch):
    raw = tmp_path / "absent" / "raw"
    monkeypatch.setattr(harvest, "RAW", raw)
    monkeypatch.setattr(harvest.time, "sleep", lambda _: None)
    monkeypatch.setattr(harvest, "opener", lambda: object())
    monkeypatch.setattr(harvest, "request", lambda *a, **k: (
        200, {}, b'<input name="__VIEWSTATE" value="test">'))
    monkeypatch.setattr(harvest, "post", lambda *a, **k: (503, {}, b"unavailable"))
    result = harvest.harvest_one({"msmtCode": "VS_TEST", "officialName": "Test"}, True)
    assert result["status"] == "detail_failed"
    assert (raw / "msmt-detail-vs_test.html").read_bytes() == b"unavailable"

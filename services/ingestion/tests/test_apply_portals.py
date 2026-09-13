from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
PORTALS = ROOT / "data" / "sources" / "admissions" / "apply-portals.json"
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
JUNK = (".css", ".js", ".png", "wp-content/plugins")


def test_every_register_hei_has_a_row_and_no_404_assets():
    portals = json.loads(PORTALS.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert portals["catalogKind"] == "tracer_not_published"
    rows = portals["institutions"]
    assert len(rows) == len(baseline["institutions"]) == 54
    ids = {row["institutionId"] for row in rows}
    assert ids == {item["id"] for item in baseline["institutions"]}
    for row in rows:
        for key in ("applyUrl", "applyUrlEn", "admissionsUrl", "admissionsUrlEn"):
            url = row.get(key)
            if not url:
                continue
            low = url.lower()
            assert not any(part in low for part in JUNK), url
            assert url.startswith("http://") or url.startswith("https://")
        if row["kind"] == "missing":
            assert row["applyUrl"] is None
        elif row["kind"] == "e_application":
            assert row["applyUrl"]
            assert any(token in row["applyUrl"].lower() for token in ("prihlask", "eprihlask", "apply", "application", "form"))
        else:
            assert row["admissionsUrl"] or row["admissionsUrlEn"]


def test_charles_and_masaryk_keep_live_e_application_hosts():
    portals = json.loads(PORTALS.read_text(encoding="utf-8"))
    by_id = {row["institutionId"]: row for row in portals["institutions"]}
    assert "is.cuni.cz" in (by_id["msmt-vs_11000"]["applyUrl"] or "")
    assert "is.muni.cz" in (by_id["msmt-vs_14000"]["applyUrl"] or "")
    police = by_id["msmt-vs_94000"]
    assert police["kind"] == "missing"
    assert police["applyUrl"] is None


if __name__ == "__main__":
    test_every_register_hei_has_a_row_and_no_404_assets()
    test_charles_and_masaryk_keep_live_e_application_hosts()
    print("ok")

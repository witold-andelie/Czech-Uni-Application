"""CZU programme tracer: offline evidence → stable programme identities.

These tests exercise the full engine path against the harvested evidence files
under data/sources/admissions/ without any network I/O. They pin the declared-
scope gates, the per-catalogue counts, the season/tuition/window passthrough
rules (nothing invented), the EN/CS separation, and idempotent re-runs.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adapters.programmes import programme_adapter_for  # noqa: E402
from adapters.programmes.evidences import (  # noqa: E402
    evidence_context,
    gate_declared_scope,
    load_payload,
    parse_programme_rows,
)
from engine.run_source import run_source  # noqa: E402
from harvest_nine_hei_jobs import load_registered_programme_sources  # noqa: E402
from storage.memory import MemoryStore  # noqa: E402

ALL_SOURCES = ("studyin", "czu-study-english-programmes", "czu-studuj-bachelor-master-programmes", "czu-doctoral-faculty-admissions")

EXPECTED_RECORD_COUNTS = {
    "studyin": 5137,
    "czu-study-english-programmes": 36,
    "czu-studuj-bachelor-master-programmes": 129,
    "czu-doctoral-faculty-admissions": 60,
}


def _source(source_id: str) -> dict:
    item = next(item for item in load_registered_programme_sources() if item["id"] == source_id)
    assert programme_adapter_for(item) is not None
    return item


def _run(source_id: str, store: MemoryStore, *, payload: dict | None = None):
    ctx, gate = evidence_context(source_id, payload=payload or load_payload(source_id))
    return run_source(programme_adapter_for(_source(source_id)), _source(source_id), ctx, store=store), gate


def _payload(source_id: str) -> dict:
    return load_payload(source_id)


def test_all_registered_sources_have_declared_scope_gates() -> None:
    for source_id in ALL_SOURCES:
        reasons = gate_declared_scope(source_id, _payload(source_id))
        assert reasons == [], f"{source_id}: {reasons}"


def test_parse_rows_counts_match_the_evidence() -> None:
    for source_id, expected in EXPECTED_RECORD_COUNTS.items():
        rows = parse_programme_rows(source_id, _payload(source_id))
        assert len(rows) == expected, source_id


def test_full_pipeline_ingests_each_evidence_file() -> None:
    for source_id, expected in EXPECTED_RECORD_COUNTS.items():
        store = MemoryStore()
        outcome, gate = _run(source_id, store)
        assert gate == []
        assert outcome["completeness"].ok, source_id
        assert outcome["completeness"].listed_count == expected
        assert len(store.programmes) == expected
        row = next(iter(store.programmes.values()))
        assert row["visibility"] == "private"
        version = next(v for v in store.versions if v.get("prog_id") == row["id"])
        assert version["facts"]["catalogue"]


def test_czu_doctoral_offerings_carry_asserted_season_windows_and_apply_portal() -> None:
    source_id = "czu-doctoral-faculty-admissions"
    store = MemoryStore()
    outcome, _ = _run(source_id, store)
    assert outcome["completeness"].ok
    versions = [v for v in store.versions if v.get("prog_id")]
    assert len(versions) == 60
    for version in versions:
        assert version["facts"]["academic_year"] == "2026/2027"
        assert version["facts"]["seasonAsserted"] is True
        assert version["facts"]["application_url"].startswith("https://is.czu.cz/prihlaska")
        assert version["facts"]["teaching_languages"] == [version["facts"]["studyLanguage"]]
    windows = sum(len(version["facts"]["applicationWindows"]) for version in versions)
    assert windows == 92
    assert outcome["completeness"].parsed_count == 60


def test_czu_english_passthrough_keeps_tuition_and_does_not_invent_season() -> None:
    source_id = "czu-study-english-programmes"
    store = MemoryStore()
    outcome, _ = _run(source_id, store)
    assert outcome["completeness"].ok
    versions = [v for v in store.versions if v.get("prog_id")]
    assert len(versions) == 36
    hit = next(v for v in versions if v["facts"]["official_code"] == "czu-study-15")
    assert hit["facts"]["tuition"] == {"amount": 2000.0, "currency": "EUR", "period": "year", "displayOriginal": "€ 2,000 per year*"}
    assert hit["facts"]["tuitionEu"]["amount"] == 500.0
    assert hit["facts"]["seasonAsserted"] is False
    assert "academic_year" not in hit["facts"]
    window = hit["facts"]["applicationWindows"][0]
    assert window["start"] == "2026-09-15"
    assert window["end"] == "2027-01-15"
    assert hit["facts"]["application_url"] == ""
    assert hit["facts"]["applicationPortalUrl"] == "https://is.czu.cz/prihlaska/?lang=en"


def test_english_and_czech_catalogues_remain_distinct_identities() -> None:
    store = MemoryStore()
    assert _run("czu-study-english-programmes", store)[0]["completeness"].ok
    assert _run("czu-studuj-bachelor-master-programmes", store)[0]["completeness"].ok
    ids = store.programmes.keys()
    assert any("czu-study-15" in key and key.startswith("czu-study-english-programmes:") for key in ids)
    assert any("czu-studuj-960" in key and key.startswith("czu-studuj-bachelor-master-programmes:") for key in ids)
    assert len({key.split(":", 1)[0] for key in ids}) == 2
    assert len(store.programmes) == 36 + 129
    en = [v for v in store.versions if v.get("prog_id") and v["prog_id"].startswith("czu-study-english-programmes:")]
    cs = [v for v in store.versions if v.get("prog_id") and v["prog_id"].startswith("czu-studuj-bachelor-master-programmes:")]
    en_slugs = {v["facts"]["facultySlug"] for v in en}
    cs_slugs = {v["facts"]["facultySlug"] for v in cs}
    assert {"fappz", "fld", "ftz", "fzp", "pef", "tf"} <= en_slugs
    assert {"fappz", "fld", "ftz", "fzp", "pef", "tf", "ivp"} <= cs_slugs


def test_scope_decline_writes_nothing() -> None:
    payload = load_payload("studyin")
    trimmed = copy.deepcopy(payload)
    trimmed["programmes"] = trimmed["programmes"][:10]
    reasons = gate_declared_scope("studyin", trimmed)
    assert reasons
    store = MemoryStore()
    outcome, gate = _run("studyin", store, payload=trimmed)
    assert gate == reasons
    assert not outcome["completeness"].ok
    assert not store.programmes
    assert outcome["run"]["status"] in {"partial", "failed"}


def test_idempotent_rerun_creates_no_new_versions() -> None:
    source_id = "czu-doctoral-faculty-admissions"
    store = MemoryStore()
    first, _ = _run(source_id, store)
    second, _ = _run(source_id, store)
    assert first["completeness"].ok and second["completeness"].ok
    assert len(store.programmes) == 60
    versions = [v for v in store.versions if v.get("prog_id")]
    assert len(versions) == 60


def test_english_crosscheck_disagreement_is_preserved_not_merged() -> None:
    cs = _payload("czu-studuj-bachelor-master-programmes")
    crosscheck = cs["coverage"].get("englishSourceCrosscheck")
    assert crosscheck and crosscheck.get("status") == "disagrees"
    assert len(crosscheck.get("missingInCzechPortal")) == 3
    assert len(crosscheck.get("extraInCzechPortal")) == 2
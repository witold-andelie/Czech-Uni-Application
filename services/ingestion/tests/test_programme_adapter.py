from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adapters.programmes import programme_adapter_for, programme_sources  # noqa: E402
from engine.run_source import run_source  # noqa: E402
from storage.memory import MemoryStore  # noqa: E402


LISTING = "https://studyin.gov.cz/study-programmes/"


def _fixture_parser(html: str, listing_url: str) -> list[dict]:
    if "unavailable" in html:
        raise RuntimeError("should not be called on unavailable")
    return [
        {
            "title": "Applied Informatics (master)",
            "sourceUrl": "https://study.czu.cz/detail/123",
            "code": "AI-23",
            "degree": "master",
            "academicYear": "2026/2027",
            "campusMode": "full-time",
            "teachingLanguages": ["English"],
            "languageEvidenceUrl": "https://study.czu.cz/languages",
            "applicationUrl": "https://e-prihlaska/ai-23",
        }
    ]


def test_programme_adapter_runs_complete_with_memory_store() -> None:
    source = {
        "id": "studyin",
        "url": LISTING,
        "sourceType": "official_programme_directory",
        "employerId": "msmt-vs_30000",
        "parser": "studyin_directory",
        "entityKind": "programme",
    }
    adapter = programme_adapter_for(source)
    assert adapter is not None
    assert adapter.adapter_key == "studyin_directory"

    def fetch(url: str) -> tuple[int, str]:
        if url == LISTING:
            return 200, "<html>catalogue</html>"
        return 200, "<html>detail body with English-taught programme</html>"

    store = MemoryStore()
    context = {
        "fetch_page": fetch,
        "parse_programme_listing": _fixture_parser,
    }
    outcome = run_source(adapter, source, context, store=store)
    assert outcome["completeness"].ok
    assert outcome["completeness"].listed_count == 1
    assert outcome["candidates"][0].entity_kind == "programme"
    assert store.programmes
    row = store.programmes["msmt-vs_30000:AI-23"]
    assert row["official_detail_url"] == "https://study.czu.cz/detail/123"
    assert row["visibility"] == "private"
    version = next(v for v in store.versions if v.get("prog_id") == row["id"])
    assert version["facts"]["degree"] == "master"
    assert version["facts"]["teaching_languages"] == ["English"]


def test_programme_adapter_incomplete_writes_nothing() -> None:
    source = {
        "id": "czu-study-english",
        "url": LISTING,
        "sourceType": "official_university_programme_catalogue",
        "employerId": "msmt-vs_23000",
        "parser": "czu_programme_catalogue",
        "entityKind": "programme",
    }
    adapter = programme_adapter_for(source)
    store = MemoryStore()
    context = {"fetch_page": lambda url: (404, "")}
    outcome = run_source(adapter, source, context, store=store)
    assert outcome["completeness"].ok is False
    assert outcome["completeness"].listed_count == 0
    assert not store.programmes


def test_studyin_and_czu_programme_sources_are_adaptable() -> None:
    ids = {item["id"] for item in programme_sources()}
    assert "studyin" in ids
    assert "czu-study-english-programmes" in ids
    assert "czu-studuj-bachelor-master-programmes" in ids
    assert "czu-doctoral-faculty-admissions" in ids
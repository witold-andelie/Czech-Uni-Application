from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.jobs import adapter_for  # noqa: E402
from engine.run_source import run_source  # noqa: E402
from harvest_nine_hei_jobs import load_registered_job_sources  # noqa: E402
from storage.memory import MemoryStore  # noqa: E402
import worker  # noqa: E402

LISTING = "https://www.muni.cz/en/about-us/careers"
DETAIL = "https://www.muni.cz/en/about-us/careers/vacancies/98765-new"


def _muni_source() -> dict:
    return {
        "id": "muni-careers",
        "url": LISTING,
        "baseUrl": "https://www.muni.cz",
        "sourceType": "official_job_listing",
        "employerId": "msmt-vs_14000",
        "parser": "muni_vacancies",
        "followDetails": True,
    }


def _fetch(url: str) -> tuple[int, str]:
    if url == LISTING:
        return 200, f'<a href="{DETAIL}">Research assistant in AI</a>'
    if url == DETAIL:
        return (
            200,
            "<h1>Research assistant in AI</h1><p>Master degree. Employment contract. "
            "Application deadline: 2026-09-30.</p>",
        )
    return 404, ""


def test_muni_uses_registered_listing_adapter() -> None:
    adapter = adapter_for(_muni_source())
    assert adapter is not None
    assert adapter.adapter_key == "muni_vacancies"
    store = MemoryStore()
    outcome = run_source(adapter, _muni_source(), {"fetch_page": _fetch}, store=store)
    assert outcome["completeness"].ok
    assert len(outcome["candidates"]) == 1
    assert outcome["candidates"][0].official_detail_url == DETAIL
    assert store.jobs


def test_harvest_jobs_routes_muni_through_adapter(tmp_path: Path) -> None:
    target = tmp_path / "jobs.json"
    target.write_text("{}", encoding="utf-8")
    result = worker.harvest_jobs([], fetch_page=_fetch, jobs_path=target, registry=[_muni_source()])
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["complete"] is True
    assert result["discovery"]["completeSourceIds"] == ["muni-careers"]
    assert any(job.get("sourceUrl") == DETAIL for job in payload["jobs"])


def test_every_html_registry_parser_has_an_adapter() -> None:
    missing = []
    for source in load_registered_job_sources():
        if source.get("parser") and adapter_for(source) is None:
            missing.append((source["id"], source.get("parser")))
    assert missing == []

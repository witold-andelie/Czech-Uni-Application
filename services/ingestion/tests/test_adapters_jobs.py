from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.jobs import adapter_for  # noqa: E402
from engine.run_source import run_source  # noqa: E402
from storage.memory import MemoryStore  # noqa: E402

PORTAL = "https://vutbr.jobs.cz/"
ZCU_FEED = "https://dumbledore.zcu.cz/document/data/folder/feed"
TUL_LISTING = "https://www.tul.cz/kariera/probihajici-vyberova-rizeni/"


def _lmc_landing() -> str:
    return (
        "window.__LMC_CAREER_WIDGET__.push("
        '{"apiKey":"k-test","widgetId":"w-1","host":"test.lmc.cz"});'
    )


def _lmc_listing(page: int) -> str:
    ident = "111" if page == 1 else "999"
    title = "Research Assistant in AI" if page == 1 else "Research Assistant in Computer Science"
    return json.dumps(
        {
            "data": {
                "widget": {
                    "jobAdList": {
                        "groupedJobAds": {"jobAds": [{"id": ident, "title": title}], "groups": []},
                        "paginator": {
                            "currentPage": page,
                            "lastPage": 2,
                            "totalNumberOfItems": 2,
                        },
                    }
                }
            }
        }
    )


def _lmc_detail(job_id: str) -> str:
    return json.dumps(
        {
            "data": {
                "widget": {
                    "jobAd": {
                        "id": job_id,
                        "title": f"Research Assistant in Job {job_id}",
                        "languageIso": "en",
                        "validFrom": "2026-09-01",
                        "salary": {"min": 30000, "currency": "CZK"},
                        "parameters": {
                            "requiredEducation": "Master",
                            "employmentTypes": ["Full-time"],
                            "requiredLanguages": [{"language": "English", "skill": "active"}],
                        },
                        "content": {
                            "htmlContent": "<p>Research in distributed systems. "
                            "Employment contract. Application deadline: 2026-10-31.</p>",
                            "sections": [],
                        },
                    }
                }
            }
        }
    )


def _lmc_fetch(url: str) -> tuple[int, str]:
    if url == PORTAL:
        return 200, _lmc_landing()
    return 404, ""


def _lmc_post(url: str, payload: dict, headers: dict[str, str] | None = None) -> tuple[int, str]:
    variables = payload.get("variables") or {}
    if "jobAdId" in variables:
        return 200, _lmc_detail(variables["jobAdId"])
    return 200, _lmc_listing(int(variables.get("page") or 1))


def test_lmc_graphql_adapter_runs_complete() -> None:
    source = {
        "id": "vut-central-careers",
        "url": PORTAL,
        "sourceType": "official_job_listing",
        "employerId": "msmt-vs_26000",
        "parser": "lmc_graphql",
        "followDetails": False,
    }
    adapter = adapter_for(source)
    assert adapter is not None
    assert adapter.adapter_key == "lmc_graphql"
    store = MemoryStore()
    context = {"fetch_page": _lmc_fetch, "post_json": _lmc_post}
    outcome = run_source(adapter, source, context, store=store)
    assert outcome["completeness"].listed_count == 2
    assert outcome["completeness"].parsed_count == 2
    assert outcome["completeness"].ok
    assert len(outcome["candidates"]) == 2
    assert store.jobs
    assert all(
        item["official_detail_url"].startswith(PORTAL) for item in store.jobs.values()
    )


def test_lmc_graphql_incomplete_listing_writes_nothing() -> None:
    source = {
        "id": "vut-central-vacancies",
        "url": PORTAL,
        "sourceType": "official_job_listing",
        "employerId": "msmt-vs_26000",
        "parser": "lmc_graphql",
        "followDetails": False,
    }

    def broken_fetch(url: str) -> tuple[int, str]:
        return 404, "" if url == PORTAL else (404, "")

    adapter = adapter_for(source)
    store = MemoryStore()
    context = {
        "fetch_page": broken_fetch,
        "post_json": lambda *_: (200, _lmc_listing(1)),
    }
    outcome = run_source(adapter, source, context, store=store)
    assert outcome["completeness"].ok is False
    assert outcome["completeness"].listed_count == 0
    assert not store.jobs


_ZCU_FEED_JSON = json.dumps(
    {
        "documents": [],
        "folders": [
            {
                "documents": [
                    {
                        "cmisId": "abc-1;1",
                        "title": "Researcher Assistant in Photonics",
                        "nameNice": "photonics.pdf",
                        "mimeType": {"subtype": "pdf"},
                    }
                ],
                "folders": [],
            }
        ],
    }
)


def _pdf_fetch(url: str) -> tuple[int, str]:
    if url == ZCU_FEED:
        return 200, _ZCU_FEED_JSON
    return 404, ""


def _pdf_attachment(_url: str) -> tuple[int, bytes]:
    return 200, b"%PDF-1.4 fake"


def _pdf_text(_body: bytes) -> str:
    return (
        "Research assistant in laser photonics. Master degree is required. "
        "Employment contract. Application deadline: 2026-11-15."
    )


def test_zcu_document_feed_adapter_runs_complete() -> None:
    source = {
        "id": "zcu-central-vacancies",
        "url": ZCU_FEED,
        "sourceType": "official_job_listing",
        "employerId": "msmt-vs_23000",
        "parser": "zcu_document_feed",
        "detailFormat": "pdf",
        "followDetails": True,
    }
    adapter = adapter_for(source)
    assert adapter is not None
    assert adapter.adapter_key == "zcu_document_feed"
    store = MemoryStore()
    context = {
        "fetch_page": _pdf_fetch,
        "fetch_attachment": _pdf_attachment,
        "pdf_text": _pdf_text,
    }
    outcome = run_source(adapter, source, context, store=store)
    assert outcome["completeness"].ok
    assert outcome["completeness"].listed_count == 1
    assert outcome["completeness"].parsed_count == 1
    assert outcome["candidates"][0].official_detail_url.startswith("https://xdoc.zcu.cz/")
    assert (
        next(iter(store.jobs.values()))["official_detail_url"].startswith("https://xdoc.zcu.cz/")
    )


def test_tul_careers_adapter_runs_complete() -> None:
    listing_html = (
        '<ul class="ridkyseznam">'
        '<li><strong><a href="https://doc.tul.cz/0042">Specialist for research support</a></strong></li>'
        "<li>ignored row without strong heading</li>"
        "</ul>"
    )
    source = {
        "id": "tul-central-careers",
        "url": TUL_LISTING,
        "sourceType": "official_job_listing",
        "employerId": "msmt-vs_24000",
        "parser": "tul_careers",
        "detailFormat": "pdf",
        "followDetails": True,
    }
    adapter = adapter_for(source)
    assert adapter is not None
    assert adapter.adapter_key == "tul_careers"
    store = MemoryStore()

    def fetch(url: str) -> tuple[int, str]:
        if url == TUL_LISTING:
            return 200, listing_html
        return 404, ""

    context = {
        "fetch_page": fetch,
        "fetch_attachment": _pdf_attachment,
        "pdf_text": _pdf_text,
    }
    outcome = run_source(adapter, source, context, store=store)
    assert outcome["completeness"].ok
    assert outcome["candidates"][0].official_detail_url == "https://doc.tul.cz/0042"
    assert next(iter(store.jobs.values()))["remote_id"] == "0042"
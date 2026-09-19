from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.jobs import adapter_sources  # noqa: E402
from cli.ingest_adapters import main, prioritize_sources, run_adapter_pass  # noqa: E402


def test_adapter_pass_stops_when_budget_is_gone() -> None:
    clock = {"now": 0.0}

    def now() -> float:
        return clock["now"]

    def harvest(source, **_kwargs):
        clock["now"] += 50
        return {
            "run": {"status": "succeeded"},
            "complete": True,
            "completeness": SimpleNamespace(listed_count=1, parsed_count=1),
            "candidates": [{}],
            "snapshot": {"jobs": [source["id"]]},
        }

    sources = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    report = run_adapter_pass(
        sources,
        fetch_page=lambda _url: (200, ""),
        previous={},
        budget_seconds=60,
        clock=now,
        harvest=harvest,
    )
    assert [item["sourceId"] for item in report["started"]] == ["a"]
    assert report["deferred"] == ["b", "c"]
    assert report["snapshot"] == {"jobs": ["a"]}


def test_prioritize_sources_puts_deferred_first() -> None:
    sources = [{"id": "cuni-central-open-positions"}, {"id": "muni-careers"}, {"id": "osu-central-careers"}]
    ordered = prioritize_sources(
        sources,
        previous={"deferred": ["osu-central-careers", "muni-careers"]},
    )
    assert [item["id"] for item in ordered] == [
        "osu-central-careers",
        "muni-careers",
        "cuni-central-open-positions",
    ]


def test_ingest_adapters_requires_live_flag() -> None:
    assert main([]) == 2


def test_adapter_sources_include_html_listings() -> None:
    ids = {item["id"] for item in adapter_sources()}
    assert "czu-central-jobs" in ids
    assert "cuni-central-open-positions" in ids
    assert "muni-careers" in ids
    assert "vut-central-careers" not in ids

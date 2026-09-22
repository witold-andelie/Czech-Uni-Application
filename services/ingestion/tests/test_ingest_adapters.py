from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.jobs import adapter_sources  # noqa: E402
from cli.ingest_adapters import (  # noqa: E402
    main,
    prioritize_sources,
    run_adapter_pass,
    slice_timeout,
)


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


def test_slice_timeout_is_bounded() -> None:
    assert slice_timeout(70, source_timeout=300) == 70
    assert slice_timeout(200, source_timeout=90) == 90
    assert slice_timeout(10, source_timeout=90) == 20
    assert slice_timeout(35, source_timeout=90) == 35


def _write_worker_out(out_path: Path, snapshot: dict) -> None:
    out_path.write_text(
        json.dumps(
            {
                "run": {"id": "r", "status": "succeeded"},
                "complete": True,
                "listed": 2,
                "parsed": 2,
                "candidates": 2,
                "snapshot": snapshot,
            }
        ),
        encoding="utf-8",
    )


def test_worker_slice_timeout_keeps_earlier_sources_and_continues() -> None:
    clock = {"now": 0.0}

    def now() -> float:
        return clock["now"]

    calls: list[str] = []

    def fake_run(cmd, *, timeout, env=None, cwd=None):
        ident = cmd[cmd.index("--source-id") + 1]
        out_path = Path(cmd[cmd.index("--out") + 1])
        clock["now"] += 25
        calls.append(ident)
        if ident == "b":
            raise subprocess.TimeoutExpired(cmd, timeout=timeout)
        _write_worker_out(out_path, {"jobs": [ident]})
        return SimpleNamespace(returncode=0)

    report = run_adapter_pass(
        [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        previous={},
        budget_seconds=50,
        clock=now,
        worker_command=["py", "worker.py"],
        run_process=fake_run,
        source_timeout=20,
    )
    assert calls == ["a", "b"]
    started = {item["sourceId"]: item for item in report["started"]}
    assert list(started) == ["a", "b"]
    assert started["a"]["status"] == "succeeded"
    assert started["b"]["status"] == "budget-timeout"
    assert started["b"]["complete"] is False
    assert report["deferred"] == ["c"]
    assert report["snapshot"] == {"jobs": ["a"]}
    assert report["failed"] is True


def test_worker_slice_deferral_when_budget_is_gone() -> None:
    clock = {"now": 0.0}

    def now() -> float:
        return clock["now"]

    def fake_run(cmd, *, timeout, env=None, cwd=None):
        ident = cmd[cmd.index("--source-id") + 1]
        clock["now"] += 60
        _write_worker_out(Path(cmd[cmd.index("--out") + 1]), {"jobs": [ident]})
        return SimpleNamespace(returncode=0)

    report = run_adapter_pass(
        [{"id": "a"}, {"id": "b"}],
        previous={},
        budget_seconds=40,
        clock=now,
        worker_command=["py", "worker.py"],
        run_process=fake_run,
        source_timeout=300,
    )
    assert [item["sourceId"] for item in report["started"]] == ["a"]
    assert report["deferred"] == ["b"]


def test_adapter_sources_include_html_listings() -> None:
    ids = {item["id"] for item in adapter_sources()}
    assert "czu-central-jobs" in ids
    assert "cuni-central-open-positions" in ids
    assert "muni-careers" in ids
    assert "vut-central-careers" not in ids

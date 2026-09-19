"""Harvest every HTML/job adapter source under a time budget.

Use this instead of the 35-minute full refresh when you only need identities
written to Supabase. Fixture mode is the default; pass --live for network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.jobs import adapter_for, adapter_sources  # noqa: E402


def run_adapter_pass(
    sources: list[dict],
    *,
    fetch_page=None,
    fetch_for=None,
    previous: dict,
    store=None,
    budget_seconds: int = 480,
    clock=time.monotonic,
    harvest=None,
) -> dict:
    from engine.adapter_harvest import harvest_adapter_source

    harvest = harvest or harvest_adapter_source
    deadline = clock() + max(30, budget_seconds)
    started = []
    deferred = []
    snapshot = previous
    for source in sources:
        remaining = deadline - clock()
        if remaining < 20:
            deferred.append(source.get("id"))
            continue
        page = fetch_for(source) if fetch_for is not None else fetch_page
        print(f"ingest_adapters: start {source.get('id')} remaining_s={int(remaining)}", flush=True)
        begun = clock()
        result = harvest(source, fetch_page=page, previous=snapshot, store=store)
        snapshot = result.get("snapshot") or snapshot
        elapsed = int(clock() - begun)
        started.append(
            {
                "sourceId": source.get("id"),
                "status": result["run"]["status"],
                "complete": result.get("complete"),
                "listed": result["completeness"].listed_count,
                "parsed": result["completeness"].parsed_count,
                "candidates": len(result.get("candidates") or []),
                "elapsed_s": elapsed,
            }
        )
        print(
            f"ingest_adapters: finish {source.get('id')} elapsed_s={elapsed} "
            f"status={result['run']['status']}",
            flush=True,
        )
    return {
        "started": started,
        "deferred": deferred,
        "snapshot": snapshot,
        "failed": any(item.get("status") != "succeeded" for item in started),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget-seconds", type=int, default=480)
    args = parser.parse_args(argv)
    sources = adapter_sources()
    if not args.live:
        print(
            json.dumps(
                {
                    "error": "live-flag-required-for-network",
                    "adapterSourceCount": len(sources),
                    "sourceIds": [item["id"] for item in sources],
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        return 2
    from engine.adapter_harvest import harvest_adapter_source
    from engine.runtime import require_http_fetcher, write_runtime_report
    from engine.transport import live_fetcher
    from storage.postgres import persist_enabled, store_from_env
    from storage.retention import prune_ingest_history
    from worker import JOBS_OUT, atomic_write, load_json

    os.environ.setdefault("SCRAPLING_REQUIRED", "1")
    os.environ.setdefault("SUPABASE_WRITE", "1")
    runtime = write_runtime_report(ROOT / "work" / "runs" / "scrapling-runtime.json")
    require_http_fetcher(runtime)
    store = store_from_env() if persist_enabled() else None
    previous = load_json(JOBS_OUT)
    try:
        report = run_adapter_pass(
            sources,
            fetch_for=live_fetcher,
            previous=previous,
            store=store,
            budget_seconds=args.budget_seconds,
            harvest=harvest_adapter_source,
        )
        atomic_write(JOBS_OUT, report["snapshot"])
        if store is not None:
            report["retention"] = prune_ingest_history(store)
    finally:
        closer = getattr(store, "close", None)
        if callable(closer):
            closer()
    out = ROOT / "work" / "runs" / "ingest-adapters.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {key: value for key, value in report.items() if key != "snapshot"}
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 1 if report.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())

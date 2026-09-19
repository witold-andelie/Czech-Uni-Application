"""Run one registered source through the adapter engine.

Fixture mode is the default. Pass --live only for an operator-supervised tracer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.jobs import adapter_for  # noqa: E402
from harvest_nine_hei_jobs import load_registered_job_sources  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    sources = {item["id"]: item for item in load_registered_job_sources()}
    source = sources.get(args.source_id)
    if source is None:
        print(json.dumps({"error": "unknown-or-disabled-source", "sourceId": args.source_id}))
        return 2
    adapter = adapter_for(source)
    if adapter is None:
        print(json.dumps({"error": "no-adapter", "parser": source.get("parser")}))
        return 2
    if not args.live:
        print(json.dumps({"error": "live-flag-required-for-network", "sourceId": args.source_id}))
        return 2
    from engine.adapter_harvest import harvest_adapter_source
    from engine.runtime import require_http_fetcher, write_runtime_report
    from engine.transport import live_fetcher
    from worker import JOBS_OUT, atomic_write, load_json

    os.environ.setdefault("SCRAPLING_REQUIRED", "1")
    os.environ.setdefault("SUPABASE_WRITE", "1")
    runtime = write_runtime_report(ROOT / "work" / "runs" / "scrapling-runtime.json")
    require_http_fetcher(runtime)
    fetch_page = live_fetcher(source)
    previous = load_json(JOBS_OUT)
    result = harvest_adapter_source(source, fetch_page=fetch_page, previous=previous)
    store = result.get("store")
    try:
        atomic_write(JOBS_OUT, result["snapshot"])
    finally:
        closer = getattr(store, "close", None)
        if callable(closer):
            closer()
    report = {
        "sourceId": source["id"],
        "status": result["run"]["status"],
        "listed": result["completeness"].listed_count,
        "parsed": result["completeness"].parsed_count,
        "candidates": len(result["candidates"]),
        "reasons": result["completeness"].reasons,
        "complete": result["complete"],
        "supabase": result.get("supabase"),
        "transport": getattr(fetch_page, "attempts", []),
    }
    runs_dir = ROOT / "work" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{source['id']}-tracer.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if result["run"]["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())

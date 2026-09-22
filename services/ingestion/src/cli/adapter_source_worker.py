"""Run one adapter source as a subprocess so the parent can enforce a slice.

The parent ``ingest_adapters`` owns the time budget. A single slow or hanging
source is killed at its slice deadline so earlier committed sources survive and
the rest of the pass still runs. This mirrors ``ci_refresh``'s per-task
subprocess timeout for the adapters pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from engine.adapter_harvest import harvest_adapter_source  # noqa: E402
from engine.transport import live_fetcher  # noqa: E402
from harvest_nine_hei_jobs import load_registered_job_sources  # noqa: E402
from storage.postgres import persist_enabled, store_from_env  # noqa: E402


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--previous", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    by_id = {item["id"]: item for item in load_registered_job_sources()}
    source = by_id.get(args.source_id)
    if source is None:
        print(f"adapter_source_worker: unknown source {args.source_id}", flush=True)
        return 2
    previous_path = Path(args.previous)
    previous: dict[str, Any] = {}
    if previous_path.is_file():
        raw = json.loads(previous_path.read_text(encoding="utf-8"))
        previous = raw if isinstance(raw, dict) else {}
    store = store_from_env() if persist_enabled() else None
    try:
        result = harvest_adapter_source(
            source,
            fetch_page=live_fetcher(source),
            previous=previous,
            store=store,
        )
    finally:
        closer = getattr(store, "close", None)
        if callable(closer):
            closer()
    payload = {
        "run": {"id": result["run"]["id"], "status": result["run"]["status"]},
        "complete": bool(result["complete"]),
        "listed": result["completeness"].listed_count,
        "parsed": result["completeness"].parsed_count,
        "candidates": len(result.get("candidates") or []),
        "discovery": result["discovery"],
        "supabase": result["supabase"],
        "snapshot": result["snapshot"],
    }
    _atomic_json(Path(args.out), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
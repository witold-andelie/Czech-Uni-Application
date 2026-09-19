"""Bound ingest process tables so the free-plan database cannot grow without limit.

Catalog identities and fact versions are kept. Listing observations and old
source runs are trimmed per source. Official HTML bodies are not stored in
Postgres; only SHA-256 metadata is.
"""

from __future__ import annotations

import os
from typing import Any


DEFAULT_KEEP_RUNS = 14


def keep_runs_per_source() -> int:
    raw = os.environ.get("INGEST_KEEP_RUNS", "").strip()
    if not raw:
        return DEFAULT_KEEP_RUNS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_KEEP_RUNS
    return max(1, min(value, 90))


def prune_ingest_history(store: Any, *, keep: int | None = None) -> dict[str, Any]:
    """Drop older source runs and their listing rows. Jobs and versions stay."""
    kept = keep if keep is not None else keep_runs_per_source()
    kept = max(1, kept)
    list_runs = getattr(store, "list_source_runs", None)
    delete_run = getattr(store, "delete_run", None)
    if not callable(list_runs) or not callable(delete_run):
        return {"ok": False, "skipped": "store-missing-retention"}
    runs = list_runs() or []
    by_source: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        source_id = str(run.get("source_id") or "")
        if not source_id:
            continue
        if str(run.get("status") or "") == "running":
            continue
        by_source.setdefault(source_id, []).append(run)
    deleted = 0
    for source_id, rows in by_source.items():
        rows.sort(key=lambda item: item.get("started_at") or item.get("scheduled_for") or "", reverse=True)
        for stale in rows[kept:]:
            run_id = stale.get("id")
            if not run_id:
                continue
            delete_run(str(run_id))
            deleted += 1
    return {
        "ok": True,
        "keepRunsPerSource": kept,
        "sources": len(by_source),
        "deletedRuns": deleted,
        "keptJobs": True,
        "keptVersions": True,
    }

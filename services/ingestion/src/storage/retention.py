"""Bound ingest process tables. Identities and fact versions stay.

Listing observations and old source runs are trimmed per source. Durable
evidence objects are garbage-collected only when nothing current, in-review,
or published still references them, and only after a grace period. `run_id`
being null is not a deletion signal.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from storage.budgets import EVIDENCE_GRACE_DAYS, KEEP_LAST_COMPLETE_RUN

DEFAULT_KEEP_RUNS = 14


def keep_runs_per_source() -> int:
    import os

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
    protected_complete = 0
    for source_id, rows in by_source.items():
        rows.sort(key=lambda item: item.get("started_at") or item.get("scheduled_for") or "", reverse=True)
        complete = next(
            (
                item
                for item in rows
                if str(item.get("status") or "") == "succeeded"
                and item.get("listing_complete") in (True, "true", "t", 1)
            ),
            None,
        )
        for stale in rows[kept:]:
            run_id = stale.get("id")
            if not run_id:
                continue
            if KEEP_LAST_COMPLETE_RUN and complete is not None and str(complete.get("id")) == str(run_id):
                protected_complete += 1
                continue
            delete_run(str(run_id))
            deleted += 1
    return {
        "ok": True,
        "keepRunsPerSource": kept,
        "sources": len(by_source),
        "deletedRuns": deleted,
        "protectedCompleteRuns": protected_complete,
        "keptJobs": True,
        "keptVersions": True,
    }


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        stamp = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            stamp = datetime.fromisoformat(text)
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def _add_digest(keys: set[str], digest: str | None) -> None:
    if not digest:
        return
    keys.add(digest)
    keys.add(f"{digest}.gz")


def _add_path(keys: set[str], path: str | None) -> None:
    if not path:
        return
    name = str(path)
    if "/" in name:
        name = name.split("/", 1)[-1]
    keys.add(name)
    if name.endswith(".gz"):
        keys.add(name[:-3])
    else:
        keys.add(f"{name}.gz")


def collect_referenced_object_keys(store: Any) -> set[str]:
    """Keys still bound to a document row or a catalog version.

    `run_id` being null does not un-reference an object.
    """
    keys: set[str] = set()
    pages = getattr(store, "_get_pages", None)
    if callable(pages):
        for row in pages("ingest_raw_document?select=storage_path,aux_object_path,raw_sha256,sha256"):
            _add_path(keys, row.get("storage_path"))
            _add_path(keys, row.get("aux_object_path"))
            _add_digest(keys, row.get("raw_sha256"))
            _add_digest(keys, row.get("sha256"))
        for table in ("catalog_research_job_version", "catalog_programme_version"):
            try:
                for row in pages(f"{table}?select=evidence_raw_sha256"):
                    _add_digest(keys, row.get("evidence_raw_sha256"))
            except RuntimeError:
                continue
        return keys
    for row in getattr(store, "documents", []) or []:
        _add_path(keys, row.get("storage_path"))
        _add_digest(keys, row.get("raw_sha256"))
        _add_digest(keys, row.get("sha256"))
    for version in getattr(store, "versions", []) or []:
        _add_digest(keys, version.get("evidence_raw_sha256"))
    return keys


def preview_evidence_gc(
    store: Any,
    evidence: Any,
    *,
    grace_days: int = EVIDENCE_GRACE_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """List unreferenced objects older than the grace period. Does not delete."""
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=max(1, grace_days))
    referenced = collect_referenced_object_keys(store)
    objects = evidence.list_objects() if evidence is not None else []
    unreferenced: list[dict[str, Any]] = []
    unreferenced_bytes = 0
    still_in_grace = 0
    for item in objects:
        name = str(item.get("name") or item.get("id") or "")
        if not name or name in referenced:
            continue
        updated = _parse_time(item.get("updated_at") or item.get("created_at"))
        size = int((item.get("metadata") or {}).get("size") or item.get("size") or 0)
        if updated is not None and updated > cutoff:
            still_in_grace += 1
            continue
        unreferenced.append({"key": name, "bytes": size, "updated_at": item.get("updated_at")})
        unreferenced_bytes += size
    return {
        "ok": True,
        "apply": False,
        "graceDays": grace_days,
        "objectCount": len(objects),
        "referencedKeys": len(referenced),
        "unreferenced": unreferenced,
        "unreferencedCount": len(unreferenced),
        "unreferencedBytes": unreferenced_bytes,
        "stillInGrace": still_in_grace,
        "keptJobs": True,
        "keptVersions": True,
    }


def apply_evidence_gc(evidence: Any, preview: dict[str, Any]) -> dict[str, Any]:
    """Delete only the keys listed by a preview. Never empties the bucket blindly."""
    deleted = 0
    failed: list[str] = []
    for item in preview.get("unreferenced") or []:
        key = item.get("key")
        if not key:
            continue
        try:
            evidence.delete(str(key))
            deleted += 1
        except RuntimeError:
            failed.append(str(key))
    return {
        **preview,
        "apply": True,
        "deleted": deleted,
        "failed": failed,
    }

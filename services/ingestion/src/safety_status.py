"""Versioned public safety-status overlay for verified closures.

Candidate rechecks write data/sources/ only. This module publishes a small,
monotonic overlay that public lists, details, saved items and the API apply
without waiting for a full catalogue snapshot. Snapshot rollback cannot reopen
a later verified closure. Network failures never become closed status.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from file_lock import FileMutex, LockUnavailable

ROOT = Path(__file__).resolve().parents[3]
PUBLISHED_DIR = ROOT / "data" / "published"
SAFETY_DIR = PUBLISHED_DIR / "safety"
GENERATIONS_DIR = SAFETY_DIR / "generations"
CURRENT_META = SAFETY_DIR / "current.json"
SAFETY_LOCK = SAFETY_DIR / ".safety.lock"
PUBLIC_COPY = PUBLISHED_DIR / "safety-status.json"

SCHEMA_VERSION = 1
CACHE_MAX_AGE_SECONDS = 60
PROPAGATION_TARGET_SECONDS = 300
GENERATION_RE = re.compile(r"^s\d{4}-\d{2}-\d{2}\.\d+$")

CLOSED_STATUSES = {"closed", "expired"}
UNAVAILABLE_STATUSES = {"unavailable"}
OPEN_STATUSES = {"open", "unknown"}

# Later verified closures win. Reopening requires explicit positive evidence.
_ALLOWED = {
    ("open", "closed"),
    ("open", "expired"),
    ("open", "unavailable"),
    ("unknown", "closed"),
    ("unknown", "expired"),
    ("unknown", "unavailable"),
    ("unavailable", "closed"),
    ("unavailable", "expired"),
    ("unavailable", "unavailable"),
    ("expired", "closed"),
    ("expired", "expired"),
    ("closed", "closed"),
}


class SafetyRejected(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(now: datetime | None = None) -> str:
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def empty_overlay(*, generation_id: str = "s2026-09-12.0", published_at: str | None = None) -> dict[str, Any]:
    stamp = published_at or "2026-09-12T00:00:00Z"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generationId": generation_id,
        "publishedAt": stamp,
        "sourceCheckedAt": None,
        "statusPublishedAt": stamp,
        "cacheMaxAgeSeconds": CACHE_MAX_AGE_SECONDS,
        "propagationTargetSeconds": PROPAGATION_TARGET_SECONDS,
        "entities": [],
    }


def entity_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    window_id = record.get("windowId")
    return (
        str(record.get("entityType") or "research_job"),
        str(record.get("entityId") or ""),
        str(record.get("scope") or "whole_opportunity"),
        str(window_id or ""),
    )


def _status_of(record: dict[str, Any] | None) -> str:
    if not record:
        return "open"
    value = str(record.get("status") or "open")
    return value


def transition_allowed(previous: dict[str, Any] | None, incoming: dict[str, Any]) -> bool:
    before = _status_of(previous)
    after = _status_of(incoming)
    if previous is None:
        return after in CLOSED_STATUSES | UNAVAILABLE_STATUSES | OPEN_STATUSES
    if before == after:
        prev_gen = int(previous.get("generation") or 0)
        next_gen = int(incoming.get("generation") or 0)
        return next_gen >= prev_gen
    if before in CLOSED_STATUSES and after in OPEN_STATUSES:
        return bool(incoming.get("reopenEvidenceId"))
    return (before, after) in _ALLOWED


def merge_entities(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], generation: int) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in existing:
        if isinstance(item, dict) and item.get("entityId"):
            merged[entity_key(item)] = dict(item)
    for item in incoming:
        if not isinstance(item, dict) or not item.get("entityId"):
            continue
        record = dict(item)
        record["generation"] = int(record.get("generation") or generation)
        key = entity_key(record)
        previous = merged.get(key)
        if not transition_allowed(previous, record):
            continue
        if previous and int(previous.get("generation") or 0) > int(record["generation"]):
            continue
        merged[key] = record
    whole_closed = {
        (key[0], key[1])
        for key, record in merged.items()
        if key[2] == "whole_opportunity" and _status_of(record) in CLOSED_STATUSES
    }
    for key, record in list(merged.items()):
        identity = (key[0], key[1])
        if identity in whole_closed and key[2] == "window" and _status_of(record) in OPEN_STATUSES:
            closed = dict(record)
            closed["status"] = "closed"
            closed["reason"] = closed.get("reason") or "whole_opportunity_closed"
            merged[key] = closed
    return [merged[key] for key in sorted(merged)]


def generate_generation_id(generations_dir: Path, now: datetime | None = None) -> str:
    current = now or utc_now()
    base = f"s{current.strftime('%Y-%m-%d')}"
    generations_dir.mkdir(parents=True, exist_ok=True)
    increments: list[int] = []
    for item in generations_dir.iterdir():
        name = item.stem if item.suffix == ".json" else item.name
        if GENERATION_RE.fullmatch(name) and name.startswith(f"{base}."):
            try:
                increments.append(int(name.rsplit(".", 1)[1]))
            except ValueError:
                continue
    return f"{base}.{max(increments, default=0) + 1}"


def load_overlay(safety_dir: Path = SAFETY_DIR) -> dict[str, Any]:
    pointer_path = safety_dir / "current.json"
    if not pointer_path.is_file():
        return empty_overlay()
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_overlay()
    relative = pointer.get("generationDir")
    generation_id = pointer.get("activeGeneration")
    if not isinstance(generation_id, str) or not GENERATION_RE.fullmatch(generation_id):
        return empty_overlay()
    expected = f"generations/{generation_id}.json"
    if relative != expected:
        return empty_overlay()
    path = safety_dir / Path(relative)
    if not path.is_file():
        return empty_overlay()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_overlay()
    if not isinstance(payload, dict):
        return empty_overlay()
    payload.setdefault("entities", [])
    return payload


def apply_overlay_to_job(job: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    updated = dict(job)
    job_id = updated.get("id")
    if not isinstance(job_id, str):
        return updated
    for record in overlay.get("entities") or []:
        if not isinstance(record, dict):
            continue
        if record.get("entityType") not in {None, "research_job"}:
            continue
        if record.get("entityId") != job_id:
            continue
        status = _status_of(record)
        if record.get("scope") == "whole_opportunity" and status in CLOSED_STATUSES | UNAVAILABLE_STATUSES:
            if status in CLOSED_STATUSES:
                updated["wholeOpportunityClosed"] = True
                updated["lifecycleStatus"] = "closed" if status == "closed" else "expired"
            else:
                updated["lifecycleStatus"] = "unavailable"
            updated["closureReason"] = record.get("reason")
            updated["closedAt"] = record.get("closedAt")
            updated["safetyGeneration"] = overlay.get("generationId")
            updated["safetyStatusPublishedAt"] = overlay.get("statusPublishedAt")
    return updated


def apply_overlay_to_window(window: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    updated = dict(window)
    owner_id = updated.get("ownerId")
    window_id = updated.get("id")
    whole_closed = False
    window_closed = False
    reason = None
    closed_at = None
    for record in overlay.get("entities") or []:
        if not isinstance(record, dict) or record.get("entityId") != owner_id:
            continue
        status = _status_of(record)
        if record.get("scope") == "whole_opportunity" and status in CLOSED_STATUSES:
            whole_closed = True
            reason = record.get("reason")
            closed_at = record.get("closedAt")
        if record.get("scope") == "window" and record.get("windowId") == window_id and status in CLOSED_STATUSES:
            window_closed = True
            reason = record.get("reason") or reason
            closed_at = record.get("closedAt") or closed_at
    if whole_closed or window_closed:
        updated["status"] = "closed"
        if reason:
            updated["closedReason"] = reason
        if closed_at:
            updated["closedAt"] = closed_at
    return updated


def apply_overlay_to_catalog(catalog: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, Any]:
    if not overlay:
        return catalog
    updated = dict(catalog)
    updated["jobs"] = [apply_overlay_to_job(item, overlay) for item in catalog.get("jobs") or [] if isinstance(item, dict)]
    updated["windows"] = [
        apply_overlay_to_window(item, overlay) for item in catalog.get("windows") or [] if isinstance(item, dict)
    ]
    updated["safetyGeneration"] = overlay.get("generationId")
    updated["safetyStatusPublishedAt"] = overlay.get("statusPublishedAt")
    return updated


def job_is_public(job: dict[str, Any], windows: list[dict[str, Any]] | None = None) -> bool:
    if job.get("wholeOpportunityClosed") or job.get("lifecycleStatus") in {"closed", "expired"}:
        return False
    if job.get("visibility") not in {None, "public"}:
        return False
    return True


def closures_from_recheck(previous: dict[str, Any], updated: dict[str, Any], now_text: str) -> list[dict[str, Any]]:
    """Collect verified status changes. HTTP/network failures are ignored."""
    previous_jobs = {
        item.get("id"): item
        for item in previous.get("jobs") or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    previous_windows: dict[str, dict[str, Any]] = {}
    for item in previous.get("windows") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            previous_windows[item["id"]] = item

    records: list[dict[str, Any]] = []
    for job in updated.get("jobs") or []:
        if not isinstance(job, dict) or not isinstance(job.get("id"), str):
            continue
        attempt = str(job.get("lastAttemptReason") or "")
        if attempt.startswith("recheck_http_") or attempt.startswith("recheck_error_") or attempt == "recheck_missing_source_url":
            continue
        old = previous_jobs.get(job["id"], {})
        evidence_url = job.get("sourceUrl") if isinstance(job.get("sourceUrl"), str) else None
        source_hash = job.get("sourceHash") if isinstance(job.get("sourceHash"), str) else None
        if job.get("wholeOpportunityClosed") and not old.get("wholeOpportunityClosed"):
            records.append(
                {
                    "entityType": "research_job",
                    "entityId": job["id"],
                    "status": "closed",
                    "scope": "whole_opportunity",
                    "windowId": None,
                    "observedSourceHash": source_hash,
                    "observedAt": now_text,
                    "closedAt": job.get("closedAt") or now_text,
                    "datePrecision": "datetime",
                    "reason": job.get("closureReason") or "page_announced_closure",
                    "evidenceUrl": evidence_url,
                    "reopenEvidenceId": None,
                }
            )
        elif job.get("lifecycleStatus") in {"closed", "expired", "unavailable"} and old.get("lifecycleStatus") not in {
            "closed",
            "expired",
            "unavailable",
        }:
            status = "unavailable" if job.get("lifecycleStatus") == "unavailable" else "closed"
            if job.get("lifecycleStatus") == "expired":
                status = "expired"
            records.append(
                {
                    "entityType": "research_job",
                    "entityId": job["id"],
                    "status": status,
                    "scope": "whole_opportunity",
                    "windowId": None,
                    "observedSourceHash": source_hash,
                    "observedAt": now_text,
                    "closedAt": job.get("closedAt") or job.get("unavailableAt") or now_text,
                    "datePrecision": "datetime",
                    "reason": job.get("closureReason") or job.get("lastAttemptReason") or job.get("lifecycleStatus"),
                    "evidenceUrl": evidence_url,
                    "reopenEvidenceId": None,
                }
            )

    for window in updated.get("windows") or []:
        if not isinstance(window, dict) or not isinstance(window.get("id"), str):
            continue
        if window.get("status") != "closed":
            continue
        old_window = previous_windows.get(window["id"], {})
        if old_window.get("status") == "closed":
            continue
        reason = str(window.get("closedReason") or "")
        if reason.startswith("recheck_http"):
            continue
        records.append(
            {
                "entityType": "research_job",
                "entityId": window.get("ownerId"),
                "status": "closed",
                "scope": "window",
                "windowId": window["id"],
                "observedSourceHash": None,
                "observedAt": now_text,
                "closedAt": window.get("closedAt") or now_text,
                "datePrecision": window.get("datePrecision") or "date",
                "reason": reason or "deadline_expired",
                "evidenceUrl": window.get("applicationUrl"),
                "reopenEvidenceId": None,
            }
        )
    return [item for item in records if item.get("entityId")]


def _next_entity_generation(overlay: dict[str, Any]) -> int:
    current = 0
    for item in overlay.get("entities") or []:
        if isinstance(item, dict):
            current = max(current, int(item.get("generation") or 0))
    return current + 1


def activate_safety_overlay(
    incoming: list[dict[str, Any]],
    *,
    safety_dir: Path = SAFETY_DIR,
    source_checked_at: str | None = None,
    now: datetime | None = None,
    public_copy: Path | None = PUBLIC_COPY,
) -> dict[str, Any]:
    """Merge verified records into a new immutable generation and switch the pointer."""
    if not incoming:
        return load_overlay(safety_dir)
    stamp = utc_stamp(now)
    lock_path = safety_dir / ".safety.lock"
    try:
        with FileMutex(lock_path, {"operation": "safety-status"}):
            current = load_overlay(safety_dir)
            generation_number = _next_entity_generation(current)
            stamped = []
            for item in incoming:
                record = dict(item)
                record["generation"] = generation_number
                stamped.append(record)
            merged_entities = merge_entities(list(current.get("entities") or []), stamped, generation_number)
            if merged_entities == list(current.get("entities") or []):
                return current
            generations_dir = safety_dir / "generations"
            generation_id = generate_generation_id(generations_dir, now)
            payload = {
                "schemaVersion": SCHEMA_VERSION,
                "generationId": generation_id,
                "publishedAt": stamp,
                "sourceCheckedAt": source_checked_at or stamp,
                "statusPublishedAt": stamp,
                "cacheMaxAgeSeconds": CACHE_MAX_AGE_SECONDS,
                "propagationTargetSeconds": PROPAGATION_TARGET_SECONDS,
                "entities": merged_entities,
            }
            atomic_write_json(generations_dir / f"{generation_id}.json", payload)
            pointer = {
                "schemaVersion": SCHEMA_VERSION,
                "activeGeneration": generation_id,
                "generationDir": f"generations/{generation_id}.json",
                "publishedAt": stamp,
                "activatedAt": stamp,
                "sourceCheckedAt": source_checked_at or stamp,
            }
            atomic_write_json(safety_dir / "current.json", pointer)
            if public_copy is not None:
                atomic_write_json(public_copy, payload)
            return payload
    except LockUnavailable as exc:
        raise RuntimeError("Another safety-status update is already running") from exc


def maybe_publish_from_recheck(
    previous: dict[str, Any],
    updated: dict[str, Any],
    now_text: str,
    *,
    jobs_path: Path | None,
    production_jobs_path: Path | None,
    safety_dir: Path | None = None,
) -> dict[str, Any] | None:
    if safety_dir is None:
        if jobs_path is None or production_jobs_path is None:
            return None
        try:
            if jobs_path.resolve() != production_jobs_path.resolve():
                return None
        except OSError:
            return None
        safety_dir = SAFETY_DIR
    records = closures_from_recheck(previous, updated, now_text)
    if not records:
        return None
    public_copy = PUBLIC_COPY if safety_dir == SAFETY_DIR else safety_dir / "safety-status.json"
    return activate_safety_overlay(
        records,
        safety_dir=safety_dir,
        source_checked_at=now_text,
        public_copy=public_copy,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish or inspect the public safety-status overlay")
    parser.add_argument("--check", action="store_true", help="Print the active overlay summary")
    args = parser.parse_args()
    overlay = load_overlay()
    entities = overlay.get("entities") or []
    print(
        json.dumps(
            {
                "generationId": overlay.get("generationId"),
                "statusPublishedAt": overlay.get("statusPublishedAt"),
                "sourceCheckedAt": overlay.get("sourceCheckedAt"),
                "entityCount": len(entities),
                "closed": sum(1 for item in entities if isinstance(item, dict) and item.get("status") in CLOSED_STATUSES),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.check and overlay.get("schemaVersion") != SCHEMA_VERSION:
        sys.exit(1)


if __name__ == "__main__":
    main()

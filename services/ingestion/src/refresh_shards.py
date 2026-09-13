"""Stable 5-way split of register HEIs so a daily run covers one fifth.

Full coverage still completes every 120 hours: shard = (UTC date − anchor) mod 5.
The same institution stays on its shard while the persisted assignment is reused.
Sorted-index modulo is only the initial mapping; adding a school must not rotate neighbours.
Jobs follow their employer.
Does not invent records and does not write data/published/.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

SHARD_COUNT = 5
DEFAULT_ANCHOR = date(2026, 9, 1)


def utc_today(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).date()


def shard_index_for_date(day: date, shard_count: int = SHARD_COUNT, anchor: date = DEFAULT_ANCHOR) -> int:
    if shard_count < 1:
        raise ValueError("shard_count must be >= 1")
    return (day.toordinal() - anchor.toordinal()) % shard_count


def assign_shards(ids: list[str], shard_count: int = SHARD_COUNT) -> dict[str, int]:
    return {item: index % shard_count for index, item in enumerate(sorted(ids))}


def assign_shards_stable(
    ids: list[str],
    previous: dict[str, int] | None = None,
    shard_count: int = SHARD_COUNT,
) -> dict[str, int]:
    """Keep existing institution IDs on their shard when the baseline set changes.

    Sorted-index modulo is only the initial assignment. New IDs join the
    currently smallest shard. Removed IDs leave a hole rather than rotating
    neighbours. This is not a cryptographic guarantee; it requires the
    persisted mapping to be reused.
    """
    if shard_count < 1:
        raise ValueError("shard_count must be >= 1")
    if not previous:
        return assign_shards(ids, shard_count)
    mapping = {
        item: previous[item]
        for item in ids
        if item in previous and isinstance(previous[item], int) and 0 <= previous[item] < shard_count
    }
    remaining = [item for item in sorted(ids) if item not in mapping]
    if not remaining:
        return mapping
    loads = [0] * shard_count
    for shard in mapping.values():
        loads[shard] += 1
    for item in remaining:
        shard = min(range(shard_count), key=lambda index: (loads[index], index))
        mapping[item] = shard
        loads[shard] += 1
    return mapping


def units_for_shard(
    ids: list[str],
    shard: int,
    shard_count: int = SHARD_COUNT,
    previous: dict[str, int] | None = None,
) -> list[str]:
    mapping = assign_shards_stable(ids, previous, shard_count)
    return [item for item in sorted(ids) if mapping[item] == shard]


def shard_sizes(ids: list[str], shard_count: int = SHARD_COUNT) -> list[int]:
    mapping = assign_shards(ids, shard_count)
    sizes = [0] * shard_count
    for shard in mapping.values():
        sizes[shard] += 1
    return sizes


def next_utc_midnight(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    tomorrow = current.date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc)


def merge_sharded_jobs(previous: dict, shard_result: dict, shard_job_ids: set[str]) -> dict:
    """Replace only this shard's jobs; keep the other four fifths untouched."""
    jobs = {item["id"]: item for item in previous.get("jobs") or [] if item.get("id")}
    existing_windows = [
        item for item in previous.get("windows") or []
        if item.get("ownerId") not in shard_job_ids
    ]
    evidence = {item["id"]: item for item in previous.get("evidence") or [] if item.get("id")}
    skipped = [item for item in previous.get("skipped") or [] if item.get("id") not in shard_job_ids]
    for job_id in shard_job_ids:
        jobs.pop(job_id, None)
        evidence.pop(f"ev-{job_id}", None)
    for item in shard_result.get("jobs") or []:
        jobs[item["id"]] = item
    new_windows = list(shard_result.get("windows") or [])
    all_windows = existing_windows + new_windows
    seen_win_keys = set()
    deduped_windows = []
    for w in all_windows:
        key = w.get("id") or f"{w.get('ownerId')}-{w.get('roundNumber')}-{w.get('opensAt')}-{w.get('closesAt')}"
        if key not in seen_win_keys:
            seen_win_keys.add(key)
            deduped_windows.append(w)
    for item in shard_result.get("evidence") or []:
        evidence[item["id"]] = item
    skipped.extend(shard_result.get("skipped") or [])
    merged_jobs = list(jobs.values())
    return {
        **previous,
        **{key: value for key, value in shard_result.items() if key not in {"jobs", "windows", "evidence", "skipped", "counts"}},
        "jobs": merged_jobs,
        "windows": deduped_windows,
        "evidence": list(evidence.values()),
        "skipped": skipped,
        "counts": {"jobs": len(merged_jobs), "skipped": len(skipped)},
    }


def merge_sharded_portals(previous: dict, shard_rows: list[dict], baseline_ids: list[str]) -> dict:
    by_id = {item["institutionId"]: item for item in previous.get("institutions") or []}
    for row in shard_rows:
        iid = row["institutionId"]
        prev = by_id.get(iid)
        if row.get("kind") == "missing" and prev and prev.get("kind") in ("e_application", "admissions_info"):
            merged = dict(prev)
            merged["lastAttemptAt"] = row.get("checkedAt")
            merged["lastAttemptReason"] = "probe_failed_kept_last_good"
            if "probes" in row:
                merged["lastProbes"] = row["probes"]
            by_id[iid] = merged
        else:
            by_id[iid] = row
    ordered = [by_id[item] for item in baseline_ids if item in by_id]
    ordered.extend(row for row in by_id.values() if row["institutionId"] not in set(baseline_ids))
    return {
        **previous,
        "institutions": ordered,
        "counts": {
            "institutions": len(ordered),
            "eApplication": sum(1 for row in ordered if row.get("kind") == "e_application"),
            "admissionsInfo": sum(1 for row in ordered if row.get("kind") == "admissions_info"),
            "missing": sum(1 for row in ordered if row.get("kind") == "missing"),
        },
    }

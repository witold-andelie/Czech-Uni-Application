"""Source health ledger and alarm (owner decision 2026-10-03).

A listing parser that silently stops matching returns zero rows and can still
report its source "complete" (the AV ČR selection-procedures page did this for
weeks when it moved to an inline list). Every harvest path records, per source
and per day, how many listing rows it read and whether the source was read
completely; the alarm fails the refresh workflow when

* a source that listed vacancies before has listed none on its last
  ``EMPTY_DAYS`` observed days, or
* a source has been incomplete on its last ``INCOMPLETE_DAYS`` observed days.

Observations are keyed by day, so writing the same run's result twice (each
checkpoint of a bounded tick) changes nothing. A failing alarm never discards
what the run harvested; it only turns the workflow red so the parser is fixed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "data" / "sources" / "coverage" / "source-health.json"
HISTORY_DAYS = 30
EMPTY_DAYS = 2
INCOMPLETE_DAYS = 3
# A source counts as one that "listed vacancies" when it once listed at least
# this many rows; a one-post school going quiet is not an alarm.
PEAK_ROWS = 3
# A listed notice's own page answering "not found" or "gone".
REMOVED_PAGE_STATUSES = {404, 410}


def _failure_kind(attempt: dict) -> str:
    """'removed' (a listed notice the school removed), 'throttled' (the host
    answered 429) or 'failed' (anything that may mean a broken source)."""
    kind = str(attempt.get("kind") or "")
    # An adapter reports one attempt per source with its reasons joined; the
    # 2026-10-06 18:01 refresh read UJEP this way and the alarm fired again.
    if kind == "adapter":
        reasons = [item for item in str(attempt.get("reason") or "").split(",") if item]
        if reasons and all(item in ("removed-detail-page", "throttled") for item in reasons):
            return "throttled" if "throttled" in reasons else "removed"
        return "failed"
    if attempt.get("status") == 429:
        return "throttled"
    if kind.startswith("detail") and attempt.get("status") in REMOVED_PAGE_STATUSES:
        return "removed"
    return "failed"


def observations_from_discovery(discovery: dict | None) -> list[dict]:
    """Per-source {sourceId, listed, complete} from a harvest's discovery block."""
    if not isinstance(discovery, dict):
        return []
    complete = set(discovery.get("completeSourceIds") or [])
    deferred = set(discovery.get("deferredSourceIds") or [])
    listed = dict(discovery.get("listedBySource") or {})
    for attempt in discovery.get("attempts") or []:
        if isinstance(attempt, dict) and attempt.get("kind") == "adapter" and attempt.get("sourceId"):
            listed.setdefault(attempt["sourceId"], int(attempt.get("listed") or 0))
    attempted = {attempt.get("sourceId") for attempt in discovery.get("attempts") or [] if isinstance(attempt, dict)}
    # A listed notice whose page the school has removed (404/410) keeps the
    # harvest incomplete, so absence never archives anything, but the source
    # itself works: UJEP's open-positions article kept linking three expired
    # notices and raised the alarm for days (2026-10-06). Any other failure,
    # a 429, a timeout or an unreadable listing, still counts.
    failures: dict[str, list[dict]] = {}
    for attempt in discovery.get("attempts") or []:
        if isinstance(attempt, dict) and not attempt.get("ok", True):
            failures.setdefault(attempt.get("sourceId"), []).append(attempt)
    rows = []
    for source_id in discovery.get("expectedSourceIds") or []:
        # A checkpoint of a bounded pass lists sources it has not reached yet.
        if source_id in deferred or (source_id not in listed and source_id not in attempted):
            continue
        kinds = {_failure_kind(item) for item in failures.get(source_id) or []}
        if source_id not in complete and "failed" not in kinds and "throttled" in kinds:
            # The host throttled the read: this pass did not reach the source,
            # as with a deferred one; that is not a broken parser (EURAXESS
            # from GitHub's shared runners, 2026-10-04 and 10-08).
            continue
        rows.append({"sourceId": source_id, "listed": listed.get(source_id),
                     "complete": source_id in complete or (bool(kinds) and kinds == {"removed"})})
    return rows


def load(path: Path | None = None) -> dict:
    path = path or LEDGER
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schemaVersion": 1, "sources": {}}


def update(ledger: dict, observations: list[dict], day: str) -> dict:
    """Record each observation under ``day``, replacing that day's earlier entry."""
    sources = ledger.setdefault("sources", {})
    for row in observations:
        source_id = str(row.get("sourceId") or "")
        if not source_id:
            continue
        entry = sources.setdefault(source_id, {"history": []})
        history = [item for item in entry.get("history") or [] if item.get("day") != day]
        listed = row.get("listed")
        history.append({"day": day, "listed": None if listed is None else int(listed), "complete": bool(row.get("complete"))})
        history.sort(key=lambda item: item["day"])
        entry["history"] = history[-HISTORY_DAYS:]
        counts = [item["listed"] for item in entry["history"] if isinstance(item.get("listed"), int)]
        entry["peakListed"] = max([entry.get("peakListed") or 0, *counts])
    return ledger


def alarms(ledger: dict) -> list[str]:
    found = []
    for source_id, entry in sorted((ledger.get("sources") or {}).items()):
        if entry.get("muted"):
            continue
        history = entry.get("history") or []
        recent = history[-EMPTY_DAYS:]
        if (
            len(recent) == EMPTY_DAYS
            and all(item.get("listed") == 0 and item.get("complete") for item in recent)
            and int(entry.get("peakListed") or 0) >= PEAK_ROWS
        ):
            found.append(
                f"{source_id}: listed no rows on {', '.join(item['day'] for item in recent)} "
                f"after listing up to {entry['peakListed']}; the listing parser probably no longer matches the page"
            )
        recent = history[-INCOMPLETE_DAYS:]
        if len(recent) == INCOMPLETE_DAYS and not any(item.get("complete") for item in recent):
            found.append(
                f"{source_id}: incomplete on {', '.join(item['day'] for item in recent)}; "
                "fetches or detail pages keep failing"
            )
    return found


def record(observations: list[dict], path: Path | None = None, now: datetime | None = None) -> None:
    if not observations:
        return
    path = path or LEDGER
    day = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    ledger = update(load(path), observations, day)
    ledger["note"] = (
        "Per-source listing rows and completeness by day, written by every harvest path; "
        "source_health.py --check fails the refresh when a source went empty or stays incomplete."
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 when a source went empty or stays incomplete")
    args = parser.parse_args(argv)
    ledger = load()
    sources = ledger.get("sources") or {}
    print(f"source health: {len(sources)} source(s) observed")
    found = alarms(ledger)
    for line in found:
        print(f"::error title=Source health::{line}" if args.check else f"alarm: {line}")
    return 1 if (args.check and found) else 0


if __name__ == "__main__":
    sys.exit(main())

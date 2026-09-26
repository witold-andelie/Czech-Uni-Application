"""Shared, offline live-evidence rules for the verifier, the gate and publishing.

One place decides what counts as confirmation, so the CLI verifier, the publish
gate (services/ingestion/src/cli/check_live_evidence.py) and the publication
pipeline (services/ingestion/src/publish.py) can never disagree. Nothing here
touches the network.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "data" / "sources" / "coverage" / "live-title-verification.json"
DEFAULT_MAX_AGE_DAYS = 7
CONFIRMED_STATUSES = ("matched", "operator_verified")


def parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_evidence(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def confirmed_rows(evidence: dict[str, Any], max_age_days: int, now: datetime) -> tuple[set[str], dict[str, str]]:
    """Return (confirmed candidate ids, id -> why-not-confirmed)."""
    confirmed_statuses = set(evidence.get("confirmedStatuses") or CONFIRMED_STATUSES)
    stale_after = timedelta(days=max_age_days)
    fresh: set[str] = set()
    reasons: dict[str, str] = {}
    for row in evidence.get("rows") or []:
        if not isinstance(row, dict) or not row.get("candidateId"):
            continue
        candidate_id = str(row["candidateId"])
        status = str(row.get("status") or "")
        if status not in confirmed_statuses:
            reasons[candidate_id] = status or "unconfirmed"
            continue
        checked = parse_ts(row.get("checkedAt") or row.get("verifiedAt"))
        if checked is None:
            reasons[candidate_id] = "unparseable checkedAt"
            continue
        if now - checked > stale_after:
            reasons[candidate_id] = f"older than {max_age_days} days"
            continue
        fresh.add(candidate_id)
    return fresh, reasons


def _deadline(job: dict[str, Any], windows: list[dict[str, Any]]) -> datetime | None:
    """Latest closing date announced for a job, from the job file's windows."""
    job_id = str(job.get("id") or "")
    moments = [
        parsed
        for window in windows
        if isinstance(window, dict)
        and window.get("ownerType", "research_job") == "research_job"
        and str(window.get("ownerId") or "") == job_id
        for parsed in [parse_ts(window.get("closesAt"))]
        if parsed is not None
    ]
    return max(moments) if moments else None


def _entering_publication(job: dict[str, Any]) -> bool:
    """Whether a candidate file job is one publication would expose.

    The same selection the publication pipeline applies: approved, public,
    live, with verified trilingual translations. Items already archived, closed,
    expired or unavailable are not entering the snapshot, so the gate does not
    demand fresh proof of them.
    """
    if job.get("publicationStatus") != "approved":
        return False
    if job.get("visibility") != "public":
        return False
    if job.get("translationStatus") != "verified":
        return False
    if job.get("lifecycleStatus") in ("closed", "expired", "unavailable"):
        return False
    return True


def missing_live_evidence(
    jobs_payload: dict[str, Any],
    evidence_payload: dict[str, Any],
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    now: datetime | None = None,
    publishable_only: bool = True,
) -> list[tuple[str, str]]:
    """(job id, reason) for every job entering the snapshot without live evidence.

    A job whose announced application window has already closed is exempt: it is
    expected to be archived or withheld rather than to re-prove a live
    announcement. Everything else - matched or operator_verified within the
    freshness window - must be confirmed per item. A http_404/403/500/timeout or
    source_change_noted row never confirms a job, which is how an unavailable
    official source holds publication instead of silently closing the vacancy.

    ``publishable_only`` restricts the check to the jobs publication would
    actually expose, so the gate can be run against a candidate file as a report
    without tripping over items that are already archived or blocked.
    """
    reference = now or datetime.now(timezone.utc)
    if not evidence_payload:
        return [("<evidence>", "live-title-verification.json missing or empty: run verify_live_titles.py")]
    fresh, reasons = confirmed_rows(evidence_payload, max_age_days, reference)
    jobs = jobs_payload.get("jobs") if isinstance(jobs_payload, dict) else jobs_payload
    windows = jobs_payload.get("windows") if isinstance(jobs_payload, dict) else []
    missing: list[tuple[str, str]] = []
    for job in jobs or []:
        if not isinstance(job, dict) or not job.get("id"):
            continue
        if publishable_only and not _entering_publication(job):
            continue
        job_id = str(job["id"])
        deadline = _deadline(job, windows or [])
        if deadline is not None and deadline < reference:
            continue
        if job_id not in fresh:
            missing.append((job_id, reasons.get(job_id, "no evidence row")))
    return sorted(missing)

"""Run a registered adapter source and dual-write JSON without closing on failure."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from adapters.base import Candidate
from adapters.jobs import adapter_for
from engine.run_source import run_source
from storage.memory import MemoryStore
from storage.postgres import persist_enabled, store_from_env


def _now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_job_id(employer_id: str | None, remote_id: str) -> str:
    """Stable job id, normalized like the discovery path's _stable_discovered_id.

    Charles University codes such as ``202610-L2-PřF-1300-104`` or
    ``VP1-FaF HK-KSKF-127`` were used raw here but folded to
    ``202610-l2-p-f-1300-104`` by discovery, so one vacancy got two ids and
    the complete-listing merge marked the reviewed id as disappeared.
    """
    prefix = str(employer_id or "").removeprefix("msmt-vs_")
    code = re.sub(r"[^a-z0-9]+", "-", str(remote_id).lower()).strip("-") or str(remote_id)
    return f"job-{prefix}-{code}" if prefix else f"job-{code}"


def candidate_to_snapshot_job(candidate: Candidate, source: dict, now_text: str) -> dict[str, Any]:
    employer_id = candidate.employer_id or source.get("employerId")
    title = candidate.title
    facts = candidate.facts or {}
    return {
        "id": snapshot_job_id(employer_id, candidate.remote_id),
        "employerId": employer_id,
        "title": {"zh-CN": title, "en": title, "cs": title},
        "originalText": title,
        "sourceLanguage": "cs",
        "translationStatus": "unreviewed",
        "sourceUrl": candidate.official_detail_url,
        "applicationUrl": candidate.application_url or candidate.official_detail_url,
        "officialDetailUrl": candidate.official_detail_url,
        "applicationMethod": candidate.application_method,
        "lifecycleStatus": "unknown",
        "visibility": "review_pending",
        "catalogueScopeStatus": candidate.catalogue_scope_status,
        "publicationStatus": "review_pending",
        "track": candidate.track,
        "paidStatus": candidate.paid_status,
        "discoverySourceId": source.get("id"),
        "sourceItemId": candidate.remote_id,
        "wholeOpportunityClosed": False,
        "dataClass": "official_career_extract",
        "sourceFetchedAt": now_text,
        "factsExtractedAt": now_text,
        "noticePostedAt": (candidate.extra or {}).get("noticePostedAt"),
        "minimumDegree": facts.get("minimumDegree") or "unknown",
        "doctorateRequired": facts.get("doctorateRequired"),
        "doctoralEnrollment": facts.get("doctoralEnrollment") or "unspecified",
    }


def _prague_today() -> date:
    return datetime.now(ZoneInfo("Europe/Prague")).date()


def candidate_window(candidate: Candidate, job_id: str, today: date) -> dict[str, Any] | None:
    """The application window the notice states, shaped like job_record's.

    The detail parser already reads the deadline, but listing adapters used to
    drop it: TUL notices from 2023-2026 kept no window and looked open (all 33
    queued on 2026-10-01 had stated deadlines that had passed).
    """
    facts = candidate.facts or {}
    opens = str(facts.get("opensAt") or "")[:10] or None
    closes = str(facts.get("closesAt") or "")[:10] or None
    if not (opens or closes):
        return None
    try:
        closed = bool(closes) and date.fromisoformat(closes) < today
    except ValueError:
        return None
    return {
        "id": f"win-{job_id}",
        "ownerType": "research_job",
        "ownerId": job_id,
        "academicYear": None,
        "roundNumber": None,
        "roundLabelOriginal": candidate.remote_id,
        "roundType": facts.get("roundType") or "unspecified",
        "applicantScope": None,
        "opensAt": opens,
        "closesAt": closes,
        "timezone": "Europe/Prague",
        "datePrecision": "date",
        "status": "closed" if closed else "unknown",
        "conditionalOnVacancies": False,
        "applicationUrl": candidate.application_url or candidate.official_detail_url,
        "sourceEvidenceId": f"ev-{job_id}",
    }


def _keep_prior_review(prior: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if prior.get("sourceUrl") != incoming.get("sourceUrl"):
        return incoming
    if prior.get("publicationStatus") == "approved" or prior.get("translationStatus") in ("verified", "reviewed"):
        # A listing row only proves the vacancy is still listed; it carries no
        # detail facts, salary object or source hash. Replacing a reviewed
        # record with it kept "approved" on a record the review no longer
        # matched (MENDELU, refresh run 36839142911). Detail changes reach
        # review through the detail harvest and live verification instead.
        return prior
    merged = dict(incoming)
    for key in (
        "translationStatus",
        "publicationStatus",
        "reviewedAt",
        "translationReview",
        "visibility",
        "lifecycleStatus",
    ):
        if prior.get(key) not in (None, "", "unreviewed", "review_pending"):
            merged[key] = prior[key]
    return merged


def merge_adapter_snapshot(
    previous: dict[str, Any],
    *,
    source_id: str,
    jobs: list[dict[str, Any]],
    complete: bool,
    discovery: dict[str, Any],
    now_text: str,
    windows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    merged = dict(previous or {})
    merged["discovery"] = discovery
    if not complete:
        return merged
    prior_jobs = [item for item in merged.get("jobs") or [] if isinstance(item, dict)]
    prior_by_id = {item["id"]: item for item in prior_jobs if item.get("id")}
    kept = [item for item in prior_jobs if item.get("discoverySourceId") != source_id]
    incoming_ids = {item["id"] for item in jobs if item.get("id")}
    archived_ids: list[str] = []
    for prior in prior_jobs:
        if prior.get("discoverySourceId") != source_id or prior.get("id") in incoming_ids:
            continue
        archived = dict(prior)
        archived["lifecycleStatus"] = "unavailable"
        archived["visibility"] = "archived"
        archived["wholeOpportunityClosed"] = False
        archived["lastAttemptAt"] = now_text
        archived["lastAttemptReason"] = "missing-from-complete-official-listing"
        kept.append(archived)
        archived_ids.append(str(prior["id"]))
    incoming_windows = {
        str(item["ownerId"]): item for item in windows or [] if isinstance(item, dict) and item.get("ownerId")
    }
    replaced_windows: set[str] = set()
    past_deadline: list[str] = []
    for job in jobs:
        prior = prior_by_id.get(job["id"])
        window = incoming_windows.get(str(job["id"]))
        expired = bool(window and window.get("status") == "closed")
        if prior is None and expired:
            # As in the discovery path (job_record): a notice whose stated
            # deadline has passed does not become a new identity.
            past_deadline.append(str(job["id"]))
            continue
        record = _keep_prior_review(prior, job) if prior else job
        if record is not prior:
            if expired:
                record = {**record, "lifecycleStatus": "expired", "visibility": "archived"}
            if window:
                replaced_windows.add(str(job["id"]))
        kept.append(record)
    merged["jobs"] = kept
    if replaced_windows:
        merged["windows"] = [
            item
            for item in merged.get("windows") or []
            if not (isinstance(item, dict) and str(item.get("ownerId")) in replaced_windows)
        ] + [incoming_windows[ident] for ident in sorted(replaced_windows)]
    skipped = [
        item
        for item in merged.get("skipped") or []
        if not (isinstance(item, dict) and item.get("id") in incoming_ids)
    ]
    skipped.extend({"id": ident, "reason": "missing-from-complete-official-listing"} for ident in archived_ids)
    skipped.extend({"id": ident, "reason": "past-deadline"} for ident in past_deadline)
    merged["skipped"] = skipped
    merged["counts"] = {"jobs": len(kept), "skipped": len(skipped)}
    return merged


def harvest_adapter_source(
    source: dict,
    *,
    fetch_page,
    previous: dict[str, Any] | None = None,
    store=None,
    now_text: str | None = None,
    post_json=None,
    fetch_attachment=None,
    pdf_text=None,
    today: date | None = None,
) -> dict[str, Any]:
    adapter = adapter_for(source)
    if adapter is None:
        raise ValueError(f"no adapter for {source.get('id')}")
    if store is None:
        store = store_from_env() if persist_enabled() else MemoryStore()
        if store is None:
            store = MemoryStore()
    if post_json is None or fetch_attachment is None or pdf_text is None:
        from harvest_nine_hei_jobs import extract_pdf_text, request_binary, request_json

        post_json = post_json or request_json
        fetch_attachment = fetch_attachment or request_binary
        pdf_text = pdf_text or extract_pdf_text
    stamp = now_text or _now_text()
    context = {
        "fetch_page": fetch_page,
        "post_json": post_json,
        "fetch_attachment": fetch_attachment,
        "pdf_text": pdf_text,
    }
    outcome = run_source(adapter, source, context, store=store)
    complete = bool(outcome["completeness"].ok)
    snapshot_jobs = (
        [candidate_to_snapshot_job(item, source, stamp) for item in outcome["candidates"]]
        if complete
        else []
    )
    current = today or _prague_today()
    snapshot_windows = [
        window
        for item, job in zip(outcome["candidates"], snapshot_jobs)
        for window in [candidate_window(item, job["id"], current)]
        if window is not None
    ]
    discovery = {
        "attempts": [
            {
                "sourceId": source["id"],
                "url": source.get("url"),
                "ok": complete,
                "kind": "adapter",
                "listed": outcome["completeness"].listed_count,
                "parsed": outcome["completeness"].parsed_count,
                **({} if complete else {"reason": ",".join(outcome["completeness"].reasons) or "incomplete"}),
            }
        ],
        "quarantined": [],
        "discoveredCount": len(outcome["candidates"]) if complete else 0,
        "completeSourceIds": [source["id"]] if complete else [],
        "expectedSourceIds": [source["id"]],
        "deferredSourceIds": [],
        "runKind": "adapter",
        "adapterKey": getattr(adapter, "adapter_key", source.get("parser")),
        "runStatus": outcome["run"]["status"],
        "keptAllOfficial": True,
    }
    snapshot = merge_adapter_snapshot(
        previous or {},
        source_id=source["id"],
        jobs=snapshot_jobs,
        complete=complete,
        discovery=discovery,
        now_text=stamp,
        windows=snapshot_windows,
    )
    return {
        "jobs": snapshot.get("jobs") or [],
        "windows": list(snapshot.get("windows") or (previous or {}).get("windows") or []),
        "skipped": snapshot.get("skipped") or [],
        "counts": snapshot.get("counts") or {"jobs": 0, "skipped": 0},
        "discovery": discovery,
        "processedCandidateIds": [item["id"] for item in snapshot_jobs],
        "complete": complete,
        "snapshot": snapshot,
        "run": outcome["run"],
        "candidates": outcome["candidates"],
        "completeness": outcome["completeness"],
        "store": store,
        "supabase": {
            "ok": True,
            "status": outcome["run"]["status"],
            "runs": 1,
            "jobs": len(outcome["candidates"]) if complete else 0,
            "listed": outcome["completeness"].listed_count,
            "parsed": outcome["completeness"].parsed_count,
        },
    }

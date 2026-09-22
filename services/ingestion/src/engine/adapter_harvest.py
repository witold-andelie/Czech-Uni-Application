"""Run a registered adapter source and dual-write JSON without closing on failure."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from adapters.base import Candidate
from adapters.jobs import adapter_for
from engine.run_source import run_source
from storage.memory import MemoryStore
from storage.postgres import persist_enabled, store_from_env


def _now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_job_id(employer_id: str | None, remote_id: str) -> str:
    prefix = str(employer_id or "").removeprefix("msmt-vs_")
    return f"job-{prefix}-{remote_id}" if prefix else f"job-{remote_id}"


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


def _keep_prior_review(prior: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if prior.get("sourceUrl") != incoming.get("sourceUrl"):
        return incoming
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
    for job in jobs:
        prior = prior_by_id.get(job["id"])
        kept.append(_keep_prior_review(prior, job) if prior else job)
    merged["jobs"] = kept
    skipped = [
        item
        for item in merged.get("skipped") or []
        if not (isinstance(item, dict) and item.get("id") in incoming_ids)
    ]
    skipped.extend({"id": ident, "reason": "missing-from-complete-official-listing"} for ident in archived_ids)
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

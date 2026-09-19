"""Write harvest results to Supabase without changing the public snapshot."""

from __future__ import annotations

from typing import Any

from storage.postgres import job_title, persist_enabled, store_from_env


def harvest_job_facts(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": job.get("originalText") or job_title(job),
        "official_detail_url": job.get("officialDetailUrl") or job.get("sourceUrl"),
        "application_url": job.get("applicationUrl"),
        "scope_classification": job.get("scopeClassification") or job.get("catalogueScopeStatus") or "unspecified",
        "catalogue_scope_status": job.get("catalogueScopeStatus") or "unspecified",
        "track": job.get("track"),
        "paid_status": job.get("paidStatus") or "unconfirmed",
    }


def _adapter_owned_source_ids() -> set[str]:
    from adapters.jobs import ADAPTERS_BY_PARSER
    from harvest_nine_hei_jobs import load_registered_job_sources

    return {
        str(item["id"])
        for item in load_registered_job_sources()
        if item.get("parser") in ADAPTERS_BY_PARSER
    }


def persist_job_harvest(
    *,
    expected_source_ids: list[str],
    complete_source_ids: list[str],
    deferred_source_ids: list[str],
    attempts: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Record one harvest tick. Incomplete sources never upsert identities."""
    if not persist_enabled():
        return {"ok": True, "skipped": "supabase-write-disabled", "runs": 0, "jobs": 0}
    store = store_from_env()
    if store is None:
        return {"ok": True, "skipped": "supabase-not-configured", "runs": 0, "jobs": 0}
    owned = _adapter_owned_source_ids()
    expected_source_ids = [item for item in expected_source_ids if item not in owned]
    complete = set(complete_source_ids) - owned
    deferred = set(deferred_source_ids) - owned
    if not expected_source_ids:
        store.close()
        return {"ok": True, "skipped": "adapter-owned", "runs": 0, "jobs": 0}
    failed_reason: dict[str, str] = {}
    for attempt in attempts:
        source_id = attempt.get("sourceId")
        if source_id and attempt.get("ok") is False and source_id not in failed_reason:
            failed_reason[str(source_id)] = str(attempt.get("reason") or "source-failed")
    written = 0
    runs = 0
    try:
        for source_id in expected_source_ids:
            run = store.start_run({"id": source_id})
            runs += 1
            if source_id in complete:
                matching = [job for job in jobs if job.get("discoverySourceId") == source_id]
                for job in matching:
                    detail = job.get("sourceUrl")
                    if not isinstance(detail, str) or not detail.startswith("http"):
                        continue
                    store.upsert_job(
                        source_id=source_id,
                        employer_id=job.get("employerId"),
                        remote_id=str(job.get("sourceItemId") or job.get("id") or ""),
                        official_detail_url=detail,
                        facts=harvest_job_facts(job),
                        run_id=run["id"],
                    )
                    written += 1
                store.finish_run(
                    run["id"],
                    status="succeeded",
                    listing_complete=True,
                    listed_count=len(matching),
                    parsed_count=len(matching),
                )
            elif source_id in deferred:
                store.finish_run(
                    run["id"],
                    status="deferred",
                    listing_complete=False,
                    listed_count=0,
                    parsed_count=0,
                    error_class="retry-after-deferred",
                )
            else:
                store.finish_run(
                    run["id"],
                    status="failed",
                    listing_complete=False,
                    listed_count=0,
                    parsed_count=0,
                    error_class=failed_reason.get(source_id, "incomplete"),
                )
    finally:
        store.close()
    return {"ok": True, "skipped": None, "runs": runs, "jobs": written}

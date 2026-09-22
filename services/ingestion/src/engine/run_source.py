"""Run one registered source through an adapter and persist the result.

A partial or failed run never advances absence counters and never closes jobs.
"""

from __future__ import annotations

from typing import Any

from adapters.base import CompletenessResult, SourceAdapter
from engine.urls import official_detail_allowed
from storage.memory import MemoryStore


def _external_id(source: dict, employer_id: str | None, remote_id: str) -> str:
    return f"{employer_id or source['id']}:{remote_id}"


def run_source(
    adapter: SourceAdapter,
    source: dict,
    context: dict[str, Any],
    store: Any | None = None,
) -> dict[str, Any]:
    store = store or MemoryStore()
    run = store.start_run(source)
    context = {**context, "source": source, "run_id": run["id"]}
    try:
        references = adapter.discover(context)
        fetch_all = getattr(adapter, "fetch_all_details", None)
        if callable(fetch_all):
            documents = fetch_all(context)
        else:
            documents = []
            for reference in references:
                documents.extend(adapter.fetch_detail(reference, context))
        for document in documents:
            extra = document.extra if isinstance(document.extra, dict) else {}
            store.save_document(
                run["id"],
                document.url,
                document.body,
                document.status,
                content_type=document.content_type,
                raw=extra.get("attachment_bytes"),
                aux=extra.get("attachment_aux_text"),
            )
        for reference in references:
            store.save_observation(run["id"], reference.remote_id, reference.detail_url, reference.title)
        candidates = adapter.normalize(documents, context)
        completeness: CompletenessResult = adapter.validate_completeness(context)
        if completeness.ok:
            seen: set[str] = set()
            for candidate in candidates:
                allowed, reason = official_detail_allowed(candidate.official_detail_url, source)
                facts = {
                    "title": candidate.title,
                    "official_detail_url": candidate.official_detail_url,
                    "application_url": candidate.application_url,
                    "scope_classification": candidate.scope_classification,
                    "catalogue_scope_status": candidate.catalogue_scope_status,
                    "track": candidate.track,
                    "paid_status": candidate.paid_status,
                    "url_directness": "vacancy_document" if allowed else reason,
                    **candidate.facts,
                }
                store.upsert_job(
                    source_id=source["id"],
                    employer_id=candidate.employer_id,
                    remote_id=candidate.remote_id,
                    official_detail_url=candidate.official_detail_url,
                    facts=facts,
                    run_id=run["id"],
                )
                seen.add(_external_id(source, candidate.employer_id, candidate.remote_id))
            list_ids = getattr(store, "list_external_ids", None)
            if callable(list_ids):
                for external_id in list_ids(employer_id=source.get("employerId")):
                    if external_id not in seen:
                        store.mark_absent(external_id)
            store.finish_run(
                run["id"],
                status="succeeded",
                listing_complete=True,
                listed_count=completeness.listed_count,
                parsed_count=completeness.parsed_count,
            )
        else:
            store.finish_run(
                run["id"],
                status="partial" if references or documents else "failed",
                listing_complete=False,
                listed_count=completeness.listed_count,
                parsed_count=completeness.parsed_count,
                error_class=completeness.reasons[0] if completeness.reasons else "incomplete",
            )
        return {
            "run": store.runs[run["id"]],
            "references": references,
            "documents": documents,
            "candidates": candidates,
            "completeness": completeness,
            "store": store,
        }
    except Exception as exc:  # noqa: BLE001 — the engine must record the failure
        store.finish_run(
            run["id"],
            status="failed",
            listing_complete=False,
            listed_count=0,
            parsed_count=0,
            error_class=type(exc).__name__,
        )
        raise

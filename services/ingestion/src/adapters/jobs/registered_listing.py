"""Thin adapter over registered HTML listing parsers.

Specialized platform adapters (CZU WP Job Manager, CUNI AJAX) stay separate.
This wrapper lets every other HTML registry parser use the same engine:
incomplete runs write no identities, and classification does not drop rows
after the listing parser has emitted them.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from adapters.base import Candidate, CompletenessResult, ListingReference, RawDocument
from harvest_nine_hei_jobs import classify_track, discover_registered_candidates, parse_generic_job_page

SCOPE_FROM_TRACK = {
    "postdoc": "postdoctoral",
    "assistant": "research",
    "post_master": "research_technical",
}


class HarvestListingAdapter:
    def __init__(self, source: dict):
        self.source = source
        self.adapter_key = str(source.get("parser") or "registered_listing")
        self._listing_refs: list[ListingReference] = []
        self._complete = False
        self._reasons: list[str] = []
        self._details_ok = 0

    def discover(self, context: dict[str, Any]) -> list[ListingReference]:
        fetch_page = context["fetch_page"]
        listing_source = {**self.source, "followDetails": False}
        result = discover_registered_candidates(fetch_page, registry=[listing_source])
        self._complete = self.source["id"] in (result.get("completeSourceIds") or [])
        for attempt in result.get("attempts") or []:
            if attempt.get("ok") is False and attempt.get("reason"):
                self._reasons.append(str(attempt["reason"]))
        refs: list[ListingReference] = []
        for index, row in enumerate(result.get("candidates") or []):
            url = str(row.get("sourceUrl") or "").strip()
            if not url:
                continue
            remote_id = str(row.get("code") or url)
            refs.append(
                ListingReference(
                    remote_id=remote_id,
                    detail_url=url,
                    title=str(row.get("title") or ""),
                    listing_url=str(self.source.get("url") or url),
                    position=index,
                    extra={"listing": row},
                )
            )
        self._listing_refs = refs
        return list(refs)

    def fetch_detail(self, reference: ListingReference, context: dict[str, Any]) -> list[RawDocument]:
        fetch_page = context["fetch_page"]
        status, body = fetch_page(reference.detail_url)
        if status != 200 or not body:
            self._reasons.append("invalid-detail-response")
            return []
        self._details_ok += 1
        return [
            RawDocument(
                url=reference.detail_url,
                final_url=reference.detail_url,
                body=body,
                extra={"reference": reference},
            )
        ]

    def normalize(self, documents: list[RawDocument], context: dict[str, Any]) -> list[Candidate]:
        employer_id = self.source.get("employerId")
        source_id = self.source.get("id")
        listing_url = self.source.get("url")
        out: list[Candidate] = []
        for document in documents:
            reference: ListingReference | None = document.extra.get("reference")
            if reference is None:
                continue
            listing = reference.extra.get("listing") or {}
            parsed = parse_generic_job_page(document.body, document.url, reference.title)
            track = (
                parsed.get("track")
                if isinstance(parsed, dict)
                else listing.get("track") or classify_track(reference.title, document.body)
            )
            if parsed is None:
                facts: dict[str, Any] = dict(listing)
                catalogue = "unspecified"
                scope = "unknown"
            else:
                facts = dict(parsed)
                catalogue = "included"
                scope = SCOPE_FROM_TRACK.get(track or "", "unknown")
            out.append(
                Candidate(
                    remote_id=reference.remote_id,
                    official_detail_url=reference.detail_url,
                    application_url=str(listing.get("applicationUrl") or reference.detail_url),
                    title=reference.title,
                    body_html=document.body,
                    employer_id=listing.get("employerId") or employer_id,
                    source_id=source_id,
                    listing_url=listing_url,
                    application_method="official_instructions",
                    scope_classification=scope,
                    catalogue_scope_status=catalogue,
                    track=track,
                    paid_status=facts.get("paidStatus") or listing.get("paidStatus") or "unconfirmed",
                    facts=facts,
                )
            )
        return out

    def validate_completeness(self, context: dict[str, Any]) -> CompletenessResult:
        listed = len(self._listing_refs)
        parsed = self._details_ok
        ok = self._complete and not self._reasons and listed == parsed
        return CompletenessResult(
            ok=ok,
            expected_count=listed,
            listed_count=listed,
            parsed_count=parsed,
            reasons=list(self._reasons),
        )


def uses_binary_or_private_api(source: dict) -> bool:
    parser = str(source.get("parser") or "")
    if parser in {"lmc_graphql", "zcu_document_feed"}:
        return True
    if source.get("detailFormat") == "pdf":
        return True
    path = urlsplit(str(source.get("url") or "")).path.lower()
    return path.endswith(".pdf")

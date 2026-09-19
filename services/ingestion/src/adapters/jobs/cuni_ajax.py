"""Charles University central open-position adapter.

Stores every official active vacancy from the AJAX listing. Classification is a
field on the candidate, never a reason to drop the row.
"""

from __future__ import annotations

from typing import Any
from adapters.base import Candidate, CompletenessResult, ListingReference, RawDocument
from harvest_nine_hei_jobs import (
    classify_track,
    parse_cuni_ajax_listing,
    parse_generic_job_page,
    _cuni_ajax_pagination_urls,
)

ADAPTER_KEY = "cuni_ajax"

SCOPE_FROM_TRACK = {
    "postdoc": "postdoctoral",
    "assistant": "research",
    "post_master": "research_technical",
}


class CuniAjaxAdapter:
    adapter_key = ADAPTER_KEY

    def __init__(self, source: dict):
        self.source = source
        self._listing_refs: list[ListingReference] = []
        self._reasons: list[str] = []
        self._pages_fetched = 0
        self._details_ok = 0
        self._pending_pages = False

    def discover(self, context: dict[str, Any]) -> list[ListingReference]:
        fetch_page = context["fetch_page"]
        listing_url = self.source["url"]
        detail_base = str(self.source.get("detailBaseUrl") or "https://cuni.cz/UKEN-1573.html")
        max_pages = max(1, min(int(self.source.get("maxPages") or 20), 20))
        queue = [listing_url]
        visited: set[str] = set()
        found: list[dict] = []
        while queue:
            if len(visited) >= max_pages:
                self._pending_pages = True
                self._reasons.append("pagination-limit-exceeded")
                break
            page_url = queue.pop(0)
            if page_url in visited:
                continue
            visited.add(page_url)
            status, body = fetch_page(page_url)
            if status != 200 or not body:
                self._reasons.append("invalid-listing-response")
                continue
            rows = parse_cuni_ajax_listing(body, detail_base)
            found.extend(rows)
            self._pages_fetched += 1
            for next_url in _cuni_ajax_pagination_urls(body, page_url):
                if next_url not in visited and next_url not in queue:
                    queue.append(next_url)
        if queue:
            self._pending_pages = True
            if "pagination-limit-exceeded" not in self._reasons:
                self._reasons.append("pagination-incomplete")

        seen: set[str] = set()
        refs: list[ListingReference] = []
        for index, row in enumerate(found):
            code = str(row["code"])
            if code in seen:
                continue
            seen.add(code)
            refs.append(
                ListingReference(
                    remote_id=code,
                    detail_url=row["sourceUrl"],
                    title=row["title"],
                    listing_url=listing_url,
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
            parsed = parse_generic_job_page(document.body, document.url, reference.title)
            track = (
                parsed.get("track")
                if isinstance(parsed, dict)
                else classify_track(reference.title, document.body)
            )
            if parsed is None:
                facts: dict[str, Any] = {}
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
                    application_url=reference.detail_url,
                    title=reference.title,
                    body_html=document.body,
                    employer_id=employer_id,
                    source_id=source_id,
                    listing_url=listing_url,
                    application_method="official_instructions",
                    scope_classification=scope,
                    catalogue_scope_status=catalogue,
                    track=track,
                    paid_status=facts.get("paidStatus") or "unconfirmed",
                    facts=facts,
                    extra={"pracid": reference.remote_id},
                )
            )
        return out

    def validate_completeness(self, context: dict[str, Any]) -> CompletenessResult:
        listed = len(self._listing_refs)
        parsed = self._details_ok
        ok = (
            not self._reasons
            and not self._pending_pages
            and self._pages_fetched > 0
            and listed == parsed
        )
        return CompletenessResult(
            ok=ok,
            expected_count=listed,
            listed_count=listed,
            parsed_count=parsed,
            reasons=list(self._reasons),
            extra={"pagesFetched": self._pages_fetched},
        )

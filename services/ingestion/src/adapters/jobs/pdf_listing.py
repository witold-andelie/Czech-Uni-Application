"""Adjacent adapters for listing parsers whose detail documents are PDFs.

Shared ``PdfListingAdapter`` mirrors the registered-listing thin adapter but
fetches detail documents as bounded binary attachments and runs local PDF text
extraction. A failed extraction never converts into a vacancy disappearance:
the run stays incomplete and writes nothing.
"""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urljoin

from adapters.base import Candidate, CompletenessResult, ListingReference, RawDocument
from harvest_nine_hei_jobs import (
    classify_track,
    page_ok,
    parse_generic_job_page,
    parse_tul_careers,
    parse_zcu_document_feed,
)

SCOPE_FROM_TRACK = {
    "postdoc": "postdoctoral",
    "assistant": "research",
    "post_master": "research_technical",
}


class PdfListingAdapter:
    def __init__(self, source: dict):
        self.source = source
        self.adapter_key = str(source.get("parser") or "pdf_listing")
        self._refs: list[ListingReference] = []
        self._complete = False
        self._reasons: list[str] = []
        self._details_ok = 0

    def _list_rows(self, html: str, listing_url: str) -> list[dict]:
        raise NotImplementedError

    def discover(self, context: dict[str, Any]) -> list[ListingReference]:
        fetch_page = context["fetch_page"]
        stub = self.source.get("url", "")
        urls = [urljoin(stub, str(item)) for item in [stub, *(self.source.get("pages") or [])]]
        visited: set[str] = set()
        rows: list[dict] = []
        attempts = 0
        self._complete = False
        for url in urls:
            if url in visited or attempts >= 20:
                continue
            visited.add(url)
            attempts += 1
            status, html = fetch_page(url)
            ok = page_ok(status, html)
            if url == urljoin(stub, stub) and ok:
                self._complete = True
            if not ok:
                self._reasons.append(f"invalid-listing:{status}")
                continue
            rows.extend(self._list_rows(html, url))

        refs: list[ListingReference] = []
        seen: set[str] = set()
        for index, row in enumerate(rows):
            url = str(row.get("sourceUrl") or "")
            remote = str(row.get("code") or url)
            if not url or remote in seen:
                continue
            seen.add(remote)
            refs.append(
                ListingReference(
                    remote_id=remote,
                    detail_url=url,
                    title=str(row.get("title") or ""),
                    listing_url=self.source.get("url"),
                    position=index,
                    extra={"listing": row},
                )
            )
        self._refs = refs
        return list(refs)

    def fetch_detail(self, reference: ListingReference, context: dict[str, Any]) -> list[RawDocument]:
        fetch_attachment = context.get("fetch_attachment")
        pdf_text = context.get("pdf_text")
        if fetch_attachment is None or pdf_text is None:
            self._reasons.append("attachment-extraction-unavailable")
            return []
        detail_status, attachment = fetch_attachment(reference.detail_url)
        text = pdf_text(attachment) if detail_status == 200 else ""
        detail_ok = detail_status == 200 and len((text or "").strip()) >= 20
        if not detail_ok:
            self._reasons.append("pdf-text-extraction-failed")
            return []
        self._details_ok += 1
        detail_html = (
            f"<h1>{escape(str(reference.title or ''))}</h1>"
            f"<p>{escape(text)}</p>"
        )
        return [
            RawDocument(
                url=reference.detail_url,
                final_url=reference.detail_url,
                body=detail_html,
                content_type="application/pdf",
                extra={
                    "reference": reference,
                    "attachment_bytes": attachment,
                    "attachment_aux_text": text,
                },
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
        listed = len(self._refs)
        ok = self._complete and not self._reasons and listed == self._details_ok
        return CompletenessResult(
            ok=ok,
            expected_count=listed,
            listed_count=listed,
            parsed_count=self._details_ok,
            reasons=list(self._reasons),
        )


class ZcuDocumentFeedAdapter(PdfListingAdapter):
    def _list_rows(self, html: str, listing_url: str) -> list[dict]:
        try:
            return parse_zcu_document_feed(html)
        except (ValueError, TypeError, KeyError) as exc:
            self._reasons.append(f"document-feed-invalid:{type(exc).__name__}")
            return []


class TulCareersAdapter(PdfListingAdapter):
    def _list_rows(self, html: str, listing_url: str) -> list[dict]:
        return parse_tul_careers(html, listing_url)
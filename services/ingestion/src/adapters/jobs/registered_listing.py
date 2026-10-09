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
from html import escape

from harvest_nine_hei_jobs import (
    NOTICE_BUNDLE_FACTS,
    _stable_discovered_id,
    classify_track,
    configured_detail_html,
    discover_registered_candidates,
    is_notice_bundle,
    parse_generic_job_page,
    visible_text,
)

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
        self._source_rows: int | None = None
        # Listed vacancies whose notice was read before and is not read again
        # (EURAXESS): listed, so not archived, and their stored record stands.
        self.unchanged_job_ids: set[str] = set()

    def discover(self, context: dict[str, Any]) -> list[ListingReference]:
        fetch_page = context["fetch_page"]
        listing_source = {**self.source, "followDetails": False}
        result = discover_registered_candidates(fetch_page, registry=[listing_source])
        self._complete = self.source["id"] in (result.get("completeSourceIds") or [])
        # Rows the listing yielded, quarantined ones included (source health).
        self._source_rows = (result.get("listedBySource") or {}).get(self.source["id"])
        for attempt in result.get("attempts") or []:
            if attempt.get("ok") is not False:
                continue
            # Name each failure, so source health can tell a host that
            # throttled the read from a broken one (2026-10-08).
            if attempt.get("status") == 429:
                self._reasons.append("throttled")
            elif attempt.get("reason"):
                self._reasons.append(str(attempt["reason"]))
            elif str(attempt.get("kind") or "").startswith("detail") and attempt.get("status") in (404, 410):
                self._reasons.append("removed-detail-page")
            else:
                self._reasons.append(f"http-{attempt.get('status')}")
        refs: list[ListingReference] = []
        for index, row in enumerate(result.get("candidates") or []):
            url = str(row.get("sourceUrl") or "").strip()
            if not url:
                continue
            remote_id = str(row.get("code") or url)
            # The id the discovery path gives the same row: a code-less row is
            # keyed by a digest of employer, title and URL. Keyed by its raw URL
            # here instead, every reviewed vacancy of a code-less listing (UPOL,
            # UHK, JČU ...) read as missing and was archived (2026-10-01).
            job_id = _stable_discovered_id(
                {**row, "employerId": row.get("employerId") or self.source.get("employerId")}
            )
            refs.append(
                ListingReference(
                    remote_id=remote_id,
                    detail_url=url,
                    title=str(row.get("title") or ""),
                    listing_url=str(self.source.get("url") or url),
                    position=index,
                    extra={"listing": row, "jobId": job_id},
                )
            )
        self._listing_refs = refs
        return list(refs)

    def fetch_detail(self, reference: ListingReference, context: dict[str, Any]) -> list[RawDocument]:
        # Discovery may already hold the notice itself: the ČVUT notice board
        # reads every official PDF attachment into _factHtml, while the detail
        # page carries only metadata (title, posting and removal dates).
        # Fetching that page again lost every fact in the notice (2026-10-01).
        unchanged = (reference.extra.get("listing") or {}).get("_unchangedJobId")
        if unchanged:
            self.unchanged_job_ids.add(str(unchanged))
            self._details_ok += 1
            return []
        embedded = (reference.extra.get("listing") or {}).get("_factHtml")
        if isinstance(embedded, str) and embedded.strip():
            self._details_ok += 1
            return [
                RawDocument(
                    url=reference.detail_url,
                    final_url=reference.detail_url,
                    body=embedded,
                    extra={"reference": reference},
                )
            ]
        if urlsplit(reference.detail_url).path.lower().endswith(".pdf"):
            # A notice published as a PDF is read as text, as discovery does;
            # fetched as a page its bytes matched no title (JČU, 2026-10-01).
            status, payload = context["fetch_attachment"](reference.detail_url)
            text = context["pdf_text"](payload) if status == 200 else ""
            if len(text.strip()) < 20:
                self._reasons.append("pdf-text-extraction-failed")
                return []
            body = f"<h1>{escape(reference.title)}</h1><p>{escape(text)}</p>"
        else:
            status, body = context["fetch_page"](reference.detail_url)
            if status != 200 or not body:
                # A listed notice whose page the school removed (404/410) is
                # named apart: the read stays incomplete, but source health
                # does not count it as a failing source (UJEP, 2026-10-06).
                self._reasons.append(
                    "removed-detail-page" if status in (404, 410) else "throttled" if status == 429 else "invalid-detail-response"
                )
                return []
            # The source's own content container, as the discovery path reads
            # it: the whole UHK page put its footer menu ("Věda a výzkum")
            # into a lawyer's and an investment head's notices, which then
            # read as research posts (2026-10-08).
            body = configured_detail_html(body, self.source)
            if not body:
                self._reasons.append("missing-configured-detail-container")
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
            if (
                self.source.get("followDetails", True) is False
                and listing.get("track")
                and not (isinstance(listing.get("_factHtml"), str) and listing["_factHtml"].strip())
            ):
                # The "detail" is the listing page itself, shared by every row:
                # facts parsed from the whole page belong to whichever advert
                # comes first (VŠCHT 560 and a rolling PhD took 110's deadline,
                # 2026-10-02). The row's own section was parsed at discovery.
                parsed = {key: value for key, value in listing.items() if not key.startswith("_")}
                if isinstance(listing.get("_factText"), str) and listing["_factText"].strip():
                    parsed["_factText"] = listing["_factText"]
            else:
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
            if isinstance(parsed, dict) and is_notice_bundle(self.adapter_key, visible_text(document.body)):
                # Same rule as the discovery path, so the two never disagree.
                facts.update(NOTICE_BUNDLE_FACTS)
            if listing.get("ignoreDetailDeadline") is True:
                facts = {key: value for key, value in facts.items() if key not in {"closesAt", "opensAt"}}
                facts["ignoreDetailDeadline"] = True
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
                    extra={"jobId": reference.extra.get("jobId")} if reference.extra.get("jobId") else {},
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
            extra={"sourceRows": self._source_rows} if self._source_rows is not None else {},
        )


def uses_binary_or_private_api(source: dict) -> bool:
    parser = str(source.get("parser") or "")
    if parser in {"lmc_graphql", "zcu_document_feed"}:
        return True
    # Vacancies read from PDFs attached to each detail page (UPCE): only the
    # discovery path follows those attachments and keys the vacancy by them.
    if source.get("detailAttachmentPatterns"):
        return True
    if source.get("detailFormat") == "pdf":
        return True
    path = urlsplit(str(source.get("url") or "")).path.lower()
    return path.endswith(".pdf")

"""Reusable programme-listing adapter.

The CZU programme tracer and the MŠMT/``studyin`` directory drive listing rows
through ``context["parse_programme_listing"]``; this adapter owns discovery,
detail fetch, completeness, and normalization so the engine stays the same as
for vacancies. Incomplete runs write no programme identities.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from adapters.base import Candidate, CompletenessResult, ListingReference, RawDocument
from harvest_nine_hei_jobs import page_ok


class ProgrammeListingAdapter:
    def __init__(self, source: dict):
        self.source = source
        self.adapter_key = str(source.get("parser") or "programme_listing")
        self._refs: list[ListingReference] = []
        self._complete = False
        self._reasons: list[str] = []
        self._details_ok = 0

    def _parse_rows(self, html: str, listing_url: str, context: dict[str, Any]) -> list[dict]:
        parser = context.get("parse_programme_listing")
        if parser is None:
            self._reasons.append("programme-listing-parser-unavailable")
            return []
        return parser(html, listing_url)

    def discover(self, context: dict[str, Any]) -> list[ListingReference]:
        fetch_page = context.get("fetch_page")
        if fetch_page is None:
            self._reasons.append("fetch-page-unavailable")
            return []
        stub = self.source.get("url", "")
        urls = [urljoin(stub, str(item)) for item in [stub, *(self.source.get("pages") or [])]]
        visited: set[str] = set()
        rows: list[dict] = []
        for url in urls:
            if url in visited:
                continue
            visited.add(url)
            status, html = fetch_page(url)
            ok = page_ok(status, html)
            if url == urljoin(stub, stub) and ok:
                self._complete = True
            if not ok:
                self._reasons.append(f"invalid-listing:{status}")
                continue
            rows.extend(self._parse_rows(html, url, context))

        refs: list[ListingReference] = []
        seen: set[str] = set()
        for index, row in enumerate(rows):
            url = str(row.get("sourceUrl") or row.get("officialDetailUrl") or "")
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
        fetch_page = context.get("fetch_page")
        if fetch_page is None:
            self._reasons.append("fetch-page-unavailable")
            return []
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
        source_id = self.source.get("id")
        institution_id = self.source.get("employerId")
        out: list[Candidate] = []
        for document in documents:
            reference: ListingReference | None = document.extra.get("reference")
            if reference is None:
                continue
            listing = reference.extra.get("listing") or {}
            facts = {
                "official_code": listing.get("code"),
                "degree": listing.get("degree"),
                "academic_year": listing.get("academicYear"),
                "campus_mode": listing.get("campusMode"),
                "teaching_languages": listing.get("teachingLanguages"),
                "language_evidence_url": listing.get("languageEvidenceUrl"),
                "application_url": listing.get("applicationUrl"),
                "title": reference.title,
            }
            out.append(
                Candidate(
                    remote_id=reference.remote_id,
                    official_detail_url=reference.detail_url,
                    application_url=str(listing.get("applicationUrl") or reference.detail_url),
                    title=reference.title,
                    body_html=document.body,
                    employer_id=institution_id,
                    source_id=source_id,
                    listing_url=self.source.get("url"),
                    application_method="official_instructions",
                    entity_kind="programme",
                    facts={key: value for key, value in facts.items() if value is not None},
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
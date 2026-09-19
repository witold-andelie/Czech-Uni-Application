"""CZU jobs.czu.cz WP Job Manager adapter.

Stores every official current vacancy after listing/REST reconciliation.
Classification is a field on the candidate, never a reason to drop the row.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urljoin

from adapters.base import Candidate, CompletenessResult, ListingReference, RawDocument
from harvest_nine_hei_jobs import (
    classify_track,
    parse_czu_ajax_listing,
    parse_czu_rest_listing,
    parse_generic_job_page,
)

ADAPTER_KEY = "czu_wp_job_manager"

SCOPE_FROM_TRACK = {
    "postdoc": "postdoctoral",
    "assistant": "research",
    "post_master": "research_technical",
}


def _url_with_query(url: str, values: dict[str, object]) -> str:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in values.items():
        query[key] = [str(value)]
    return parsed._replace(query=urlencode(query, doseq=True)).geturl()


def _page_ok(status: int, html: str) -> bool:
    return status == 200 and bool(html) and "wp-job-manager" in html


class CzuWpJobManagerAdapter:
    adapter_key = ADAPTER_KEY

    def __init__(self, source: dict):
        self.source = source
        self._listing_refs: list[ListingReference] = []
        self._rest_by_id: dict[str, dict] = {}
        self._reasons: list[str] = []
        self._expected_pages: int | None = None
        self._public_found: bool | None = None
        self._landing_ok = False
        self._pages_fetched = 0

    def discover(self, context: dict[str, Any]) -> list[ListingReference]:
        fetch_page = context["fetch_page"]
        portal_url = self.source["url"]
        status, landing_html = fetch_page(portal_url)
        self._landing_ok = (
            _page_ok(status, landing_html)
            and "job_listings" in landing_html
            and "jm-ajax/%%endpoint%%" in landing_html
        )
        if not self._landing_ok:
            self._reasons.append("missing-public-job-manager-listing")
            return []

        per_page = max(1, min(int(self.source.get("perPage") or 100), 100))
        max_pages_limit = max(1, min(int(self.source.get("maxPages") or 20), 20))
        public_endpoint = str(
            self.source.get("publicListUrl") or urljoin(portal_url, "/jm-ajax/get_listings/")
        )
        public_rows: list[dict] = []
        expected_pages: int | None = None
        page = 1
        while expected_pages is None or page <= expected_pages:
            if page > max_pages_limit:
                self._reasons.append("pagination-limit-exceeded")
                break
            page_url = _url_with_query(
                public_endpoint,
                {
                    "lang": "cs",
                    "per_page": per_page,
                    "orderby": "featured",
                    "featured_first": "false",
                    "order": "DESC",
                    "page": page,
                    "show_pagination": "false",
                },
            )
            page_status, body = fetch_page(page_url)
            parsed_page = parse_czu_ajax_listing(body, page_url) if page_status == 200 else None
            if parsed_page is None:
                self._reasons.append("invalid-public-listing-response")
                break
            rows, page_count = parsed_page
            self._pages_fetched += 1
            if expected_pages is None:
                expected_pages = page_count
            elif page_count != expected_pages:
                self._reasons.append("inconsistent-public-page-count")
                break
            public_rows.extend(rows)
            if expected_pages == 0:
                break
            page += 1
        self._expected_pages = expected_pages

        seen: set[str] = set()
        refs: list[ListingReference] = []
        for index, row in enumerate(public_rows):
            code = str(row["code"])
            if code in seen:
                self._reasons.append("duplicate-public-id")
                continue
            seen.add(code)
            refs.append(
                ListingReference(
                    remote_id=code,
                    detail_url=row["sourceUrl"],
                    title=row["title"],
                    listing_url=portal_url,
                    position=index,
                    page=None,
                    extra={"public": row},
                )
            )
        self._listing_refs = refs
        return list(refs)

    def fetch_detail(self, reference: ListingReference, context: dict[str, Any]) -> list[RawDocument]:
        # REST bodies are fetched in batches by fetch_all_details; this method
        # returns the already-loaded document for one listing row.
        item = self._rest_by_id.get(reference.remote_id)
        if item is None:
            return []
        return [
            RawDocument(
                url=item["sourceUrl"],
                final_url=item["sourceUrl"],
                body=item["_factHtml"],
                content_type="text/html",
                extra={"rest": item, "reference": reference},
            )
        ]

    def fetch_all_details(self, context: dict[str, Any]) -> list[RawDocument]:
        fetch_page = context["fetch_page"]
        portal_url = self.source["url"]
        api_url = str(self.source.get("apiUrl") or urljoin(portal_url, "/wp-json/wp/v2/job-listings"))
        public_ids = [ref.remote_id for ref in self._listing_refs]
        rest_by_id: dict[str, dict] = {}
        for chunk_index in range(0, len(public_ids), 100):
            chunk = public_ids[chunk_index : chunk_index + 100]
            rest_url = _url_with_query(
                api_url,
                {
                    "include": ",".join(chunk),
                    "per_page": len(chunk),
                    "orderby": "include",
                    "context": "view",
                },
            )
            rest_status, rest_body = fetch_page(rest_url)
            rest_rows = parse_czu_rest_listing(rest_body, api_url) if rest_status == 200 else None
            ids_match = rest_rows is not None and {row["code"] for row in rest_rows} == set(chunk)
            if not ids_match:
                self._reasons.append("public-rest-item-mismatch")
                continue
            rest_by_id.update({row["code"]: row for row in rest_rows})
        self._rest_by_id = rest_by_id
        documents: list[RawDocument] = []
        for ref in self._listing_refs:
            documents.extend(self.fetch_detail(ref, context))
        return documents

    def normalize(self, documents: list[RawDocument], context: dict[str, Any]) -> list[Candidate]:
        employer_id = self.source.get("employerId")
        source_id = self.source.get("id")
        listing_url = self.source.get("url")
        public_by_id = {ref.remote_id: ref for ref in self._listing_refs}
        out: list[Candidate] = []
        for document in documents:
            rest = document.extra.get("rest") or {}
            reference: ListingReference | None = document.extra.get("reference")
            code = str(rest.get("code") or (reference.remote_id if reference else ""))
            public = public_by_id.get(code)
            if public is None or not rest:
                continue
            if rest.get("title") != public.title or rest.get("sourceUrl") != public.detail_url:
                self._reasons.append("public-rest-detail-mismatch")
                continue
            filled = bool(rest.get("filled"))
            parsed = parse_generic_job_page(rest["_factHtml"], rest["sourceUrl"], rest["title"])
            track = parsed.get("track") if isinstance(parsed, dict) else classify_track(rest["title"], rest.get("_factHtml") or "")
            scope = SCOPE_FROM_TRACK.get(track or "", "unknown")
            if parsed is None:
                scope = "unknown"
                facts: dict[str, Any] = {}
                catalogue = "unspecified"
            else:
                facts = dict(parsed)
                catalogue = "included"
            if filled:
                catalogue = "excluded"
            official_url = rest["sourceUrl"]
            extra = {
                "noticePostedAt": rest.get("noticePostedAt"),
                "filled": filled,
                "wordpressId": code,
            }
            out.append(
                Candidate(
                    remote_id=code,
                    official_detail_url=official_url,
                    application_url=official_url,
                    title=rest["title"],
                    body_html=rest["_factHtml"],
                    employer_id=employer_id,
                    source_id=source_id,
                    listing_url=listing_url,
                    application_method="official_instructions",
                    scope_classification=scope,
                    catalogue_scope_status=catalogue,
                    track=track,
                    paid_status=facts.get("paidStatus") or "unconfirmed",
                    facts=facts,
                    extra=extra,
                )
            )
        return out

    def validate_completeness(self, context: dict[str, Any]) -> CompletenessResult:
        listed = len(self._listing_refs)
        parsed = len(self._rest_by_id)
        ok = (
            self._landing_ok
            and not self._reasons
            and listed == parsed
            and (self._expected_pages == 0 or self._pages_fetched == (self._expected_pages or 0))
        )
        return CompletenessResult(
            ok=ok,
            expected_count=listed,
            listed_count=listed,
            parsed_count=parsed,
            reasons=list(self._reasons),
            extra={
                "expectedPages": self._expected_pages,
                "pagesFetched": self._pages_fetched,
            },
        )

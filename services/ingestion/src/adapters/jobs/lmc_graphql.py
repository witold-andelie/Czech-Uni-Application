"""LMC / Alma career-widget adapter (VUT and other Czech universities).

Reads the public widget configuration embedded in the official employer portal,
then POSTs GraphQL listing and detail requests to the public widget endpoint.
No browser automation and no fabricated rows: an unreachable portal, a wrong
page number, or a listing/detail count mismatch leaves the run incomplete, and
an incomplete run never writes identities or closes existing jobs.
"""

from __future__ import annotations

from typing import Any

from adapters.base import Candidate, CompletenessResult, ListingReference, RawDocument
from harvest_nine_hei_jobs import (
    LMC_GRAPHQL_ENDPOINT,
    _lmc_detail_payload,
    _lmc_job_ad,
    _lmc_listing_payload,
    page_ok,
    parse_lmc_graphql_detail,
    parse_lmc_graphql_listing,
    parse_lmc_widget_config,
)

SCOPE_FROM_TRACK = {
    "postdoc": "postdoctoral",
    "assistant": "research",
    "post_master": "research_technical",
}


class LmcGraphqlAdapter:
    adapter_key = "lmc_graphql"

    def __init__(self, source: dict):
        self.source = source
        self._portal_url = str(source.get("url") or "")
        self._config: dict | bool | None = None
        self._refs: list[ListingReference] = []
        self._complete = False
        self._reasons: list[str] = []
        self._listing_rows = 0
        self._details_ok = 0

    def _load_config(self, context: dict[str, Any]) -> dict | None:
        if self._config is not None:
            return self._config if isinstance(self._config, dict) else None
        fetch_page = context["fetch_page"]
        status, landing = fetch_page(self._portal_url)
        if not page_ok(status, landing):
            self._reasons.append(f"invalid-listing-shell:{status}")
            self._config = False
            return None
        config = parse_lmc_widget_config(landing)
        if config is None:
            self._reasons.append("missing-public-widget-config")
            self._config = False
            return None
        self._config = config
        return config

    def _detail_path(self, config: dict) -> str:
        return str(
            self.source.get("detailPath") or config.get("detailPath") or "detail-pozice"
        )

    def discover(self, context: dict[str, Any]) -> list[ListingReference]:
        post_json = context.get("post_json")
        config = self._load_config(context)
        if config is None or post_json is None:
            if post_json is None:
                self._reasons.append("post-json-unavailable")
            return []
        endpoint = str(self.source.get("apiUrl") or LMC_GRAPHQL_ENDPOINT)
        headers = {"X-Api-Key": config["apiKey"]}
        max_pages = max(1, min(int(self.source.get("maxPages") or 20), 20))
        detail_path = self._detail_path(config)
        rows: list[dict] = []
        expected_total: int | None = None
        last_page = 1
        page = 1
        while page <= last_page and page <= max_pages:
            api_status, body = post_json(
                endpoint, _lmc_listing_payload(config, page), headers
            )
            parsed_page = parse_lmc_graphql_listing(body, self._portal_url, detail_path)
            if not (api_status == 200 and parsed_page is not None):
                self._complete = False
                self._reasons.append("invalid-widget-listing-response")
                break
            page_rows, paginator = parsed_page
            if int(paginator["currentPage"]) != page:
                self._complete = False
                self._reasons.append("widget-page-number-mismatch")
                break
            last_page = int(paginator["lastPage"])
            expected_total = int(paginator["totalNumberOfItems"])
            rows.extend(page_rows)
            page += 1
        else:
            if last_page > max_pages:
                self._complete = False
                self._reasons.append("pagination-limit-exceeded")

        unique: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            code = str(row.get("code") or "")
            if code and code not in seen:
                seen.add(code)
                unique.append(row)
        if expected_total is not None and len(unique) != expected_total:
            self._complete = False
            self._reasons.append(f"listing-count-mismatch:{len(unique)}/{expected_total}")
        if not self._reasons:
            self._complete = True
        self._listing_rows = len(unique)

        refs: list[ListingReference] = []
        for index, row in enumerate(unique):
            url = str(row.get("sourceUrl") or "")
            refs.append(
                ListingReference(
                    remote_id=str(row.get("code") or url),
                    detail_url=url,
                    title=str(row.get("title") or ""),
                    listing_url=self._portal_url,
                    position=index,
                    extra={"listing": row},
                )
            )
        self._refs = refs
        return list(refs)

    def fetch_all_details(self, context: dict[str, Any]) -> list[RawDocument]:
        post_json = context.get("post_json")
        config = self._load_config(context)
        if config is None or post_json is None:
            return []
        endpoint = str(self.source.get("apiUrl") or LMC_GRAPHQL_ENDPOINT)
        headers = {"X-Api-Key": config["apiKey"]}
        documents: list[RawDocument] = []
        for reference in self._refs:
            api_status, body = post_json(
                endpoint, _lmc_detail_payload(config, reference.remote_id), headers
            )
            job = _lmc_job_ad(body)
            detail_ok = (
                api_status == 200
                and job is not None
                and str(job.get("id") or "") == reference.remote_id
            )
            if not detail_ok:
                self._complete = False
                self._reasons.append("invalid-widget-detail-response")
                continue
            self._details_ok += 1
            documents.append(
                RawDocument(
                    url=reference.detail_url,
                    final_url=reference.detail_url,
                    body=body,
                    content_type="application/json",
                    extra={"expected_id": reference.remote_id, "reference": reference},
                )
            )
        return documents

    def normalize(self, documents: list[RawDocument], context: dict[str, Any]) -> list[Candidate]:
        out: list[Candidate] = []
        for document in documents:
            reference: ListingReference | None = document.extra.get("reference")
            if reference is None:
                continue
            listing = reference.extra.get("listing") or {}
            parsed = parse_lmc_graphql_detail(
                document.body, document.url, document.extra.get("expected_id")
            )
            if parsed is None:
                continue
            track = parsed.get("track") or listing.get("track")
            scope = SCOPE_FROM_TRACK.get(track or "", "unknown")
            out.append(
                Candidate(
                    remote_id=reference.remote_id,
                    official_detail_url=reference.detail_url,
                    application_url=str(parsed.get("applicationUrl") or reference.detail_url),
                    title=str(parsed.get("title") or reference.title),
                    body_html=str(parsed.get("_factHtml") or ""),
                    employer_id=self.source.get("employerId"),
                    source_id=self.source.get("id"),
                    listing_url=self._portal_url,
                    application_method=str(parsed.get("applicationMethod") or "official_instructions"),
                    scope_classification=scope,
                    catalogue_scope_status="included",
                    track=track,
                    paid_status=str(parsed.get("paidStatus") or "unconfirmed"),
                    facts=parsed,
                )
            )
        return out

    def validate_completeness(self, context: dict[str, Any]) -> CompletenessResult:
        ok = self._complete and not self._reasons and self._listing_rows == self._details_ok
        return CompletenessResult(
            ok=ok,
            expected_count=self._listing_rows,
            listed_count=self._listing_rows,
            parsed_count=self._details_ok,
            reasons=list(self._reasons),
        )
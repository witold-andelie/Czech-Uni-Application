"""Source-adapter protocol shared by job and programme collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ListingReference:
    """One official listing row before the detail body is fetched."""

    remote_id: str
    detail_url: str
    title: str
    listing_url: str
    position: int | None = None
    page: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawDocument:
    """Fetched official body; the engine stores the bytes, adapters parse them."""

    url: str
    final_url: str
    body: str
    content_type: str = "text/html"
    status: int = 200
    source_language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    """Normalized official vacancy or programme row. Classification is not a filter."""

    remote_id: str
    official_detail_url: str
    application_url: str | None
    title: str
    body_html: str
    employer_id: str | None = None
    source_id: str | None = None
    listing_url: str | None = None
    application_method: str = "official_instructions"
    scope_classification: str = "unknown"
    catalogue_scope_status: str = "unspecified"
    track: str | None = None
    paid_status: str = "unconfirmed"
    entity_kind: str = "research_job"
    facts: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletenessResult:
    ok: bool
    expected_count: int | None = None
    listed_count: int = 0
    parsed_count: int = 0
    reasons: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


class FetchPage:
    """(url) -> (status, text). Injected so tests never touch live universities."""

    def __call__(self, url: str) -> tuple[int, str]: ...


class SourceAdapter(Protocol):
    adapter_key: str

    def discover(self, context: dict[str, Any]) -> list[ListingReference]: ...

    def fetch_detail(self, reference: ListingReference, context: dict[str, Any]) -> list[RawDocument]: ...

    def normalize(self, documents: list[RawDocument], context: dict[str, Any]) -> list[Candidate]: ...

    def validate_completeness(self, context: dict[str, Any]) -> CompletenessResult: ...

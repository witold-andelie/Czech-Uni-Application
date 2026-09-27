"""Canonical job fact hash. Classification labels must not fork versions."""

from __future__ import annotations

from hashlib import sha256
from typing import Any
import json


def canonical_job_facts(facts: dict[str, Any], official_detail_url: str) -> dict[str, Any]:
    title = facts.get("title")
    if isinstance(title, dict):
        title = title.get("cs") or title.get("en") or title.get("zh-CN") or next(iter(title.values()), "")
    return {
        "title": "" if title is None else str(title),
        "official_detail_url": official_detail_url,
        "paid_status": facts.get("paid_status") or "unconfirmed",
        "track": facts.get("track") or None,
        "catalogue_scope_status": facts.get("catalogue_scope_status") or "unspecified",
    }


def job_fact_hash(facts: dict[str, Any], official_detail_url: str) -> str:
    payload = canonical_job_facts(facts, official_detail_url)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


# Whole-page HTML and request noise must not live in catalog.*_version.facts.
# Oversized strings are reported and omitted, never silently truncated.
FACT_BODY_KEYS = frozenset(
    {
        "body",
        "html",
        "raw",
        "raw_html",
        "page_html",
        "document_body",
        "attachment_bytes",
        "attachment_aux_text",
    }
)
FACT_NOISE_KEYS = frozenset({"request_id", "fetched_at", "harvested_at", "run_id", "http_date"})
FACT_STORE_MAX_CHARS = 8_000


def stored_facts(facts: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Structured facts for Postgres. Returns (payload, rejected_field_names)."""
    payload: dict[str, Any] = {}
    rejected: list[str] = []
    for key, value in (facts or {}).items():
        name = str(key)
        if name in FACT_BODY_KEYS or name in FACT_NOISE_KEYS:
            rejected.append(name)
            continue
        if isinstance(value, str) and len(value) > FACT_STORE_MAX_CHARS:
            rejected.append(name)
            continue
        if isinstance(value, (bytes, bytearray)):
            rejected.append(name)
            continue
        payload[name] = value
    return payload, rejected

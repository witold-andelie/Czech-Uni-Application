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

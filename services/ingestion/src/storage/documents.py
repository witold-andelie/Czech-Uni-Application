"""Shared document record for RestStore, PostgresStore and MemoryStore."""

from __future__ import annotations

from typing import Any

from storage.hashes import raw_sha256, text_sha256

TIER_DURABLE = "durable"
TIER_TRANSIENT = "transient"


def prepare_document(
    *,
    url: str,
    body: str,
    status: int = 200,
    content_type: str | None = None,
    raw: bytes | None = None,
    aux: str | None = None,
    keep: bool = False,
    tier: str = TIER_TRANSIENT,
) -> dict[str, Any]:
    raw_bytes = raw if raw is not None else (body or "").encode("utf-8")
    text = aux if aux is not None else (body or "")
    durable = bool(keep) or tier == TIER_DURABLE
    return {
        "url": url,
        "status": status,
        "content_type": content_type or ("application/pdf" if raw is not None else "text/html"),
        "raw_bytes": raw_bytes,
        "text": text,
        "raw_sha256": raw_sha256(raw_bytes),
        "text_sha256": text_sha256(text),
        "sha256": text_sha256(text),
        "byte_size": len(raw_bytes),
        "is_pdf": raw is not None,
        "keep": durable,
        "evidence_tier": TIER_DURABLE if durable else TIER_TRANSIENT,
    }

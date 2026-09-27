"""Three independent digests: raw bytes, extracted text, structured facts.

`raw_sha256` is the identity of a Storage object. `text_sha256` detects
extracted-text change. `fact_hash` (see facts.job_fact_hash) decides whether a
business version is new. A PDF's extracted text must never stand in for the
file itself: two PDFs can yield the same text.
"""

from __future__ import annotations

from hashlib import sha256


def raw_sha256(data: bytes) -> str:
    return sha256(data or b"").hexdigest()


def text_sha256(text: str) -> str:
    return sha256((text or "").encode("utf-8")).hexdigest()

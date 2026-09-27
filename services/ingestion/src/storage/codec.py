"""Deterministic gzip for HTML/JSON/extracted text. PDFs stay raw unless smaller."""

from __future__ import annotations

import gzip
import io

GZIP_MAGIC = b"\x1f\x8b"
# Compress a PDF only when gzip saves at least this fraction of the original.
PDF_GZIP_MIN_SAVING = 0.10


def gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(data or b"")
    return buffer.getvalue()


def gunzip_bytes(data: bytes) -> bytes:
    if not data.startswith(GZIP_MAGIC):
        return data
    return gzip.decompress(data)


def encode_evidence(data: bytes, content_type: str | None) -> tuple[bytes, str, bool]:
    """Return (payload, object_suffix, compressed).

    HTML, JSON and extracted text are always gzipped with a stable header.
    PDFs keep original bytes unless gzip is at least 10% smaller.
    """
    kind = (content_type or "").split(";", 1)[0].strip().lower()
    if kind in {"application/pdf"} or (data or b"").startswith(b"%PDF"):
        compressed = gzip_bytes(data)
        if len(data) and (len(data) - len(compressed)) / len(data) >= PDF_GZIP_MIN_SAVING:
            return compressed, ".gz", True
        return data, "", False
    return gzip_bytes(data), ".gz", True

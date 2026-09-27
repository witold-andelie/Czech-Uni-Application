from __future__ import annotations

import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.codec import gunzip_bytes, gzip_bytes  # noqa: E402
from storage.evidence import DEFAULT_BUCKET, EvidenceStore  # noqa: E402
from storage.hashes import raw_sha256  # noqa: E402
from storage.rest import RestStore  # noqa: E402


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bytes | None]] = []
        self.objects: dict[str, bytes] = {}
        self.bucket_exists = False
        self.fail_upload = False

    def __call__(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 60,
    ):
        self.calls.append((method, path, data))
        if method == "GET" and path.startswith("bucket/"):
            if not self.bucket_exists:
                raise RuntimeError(f"supabase storage GET {path} -> 404: bucket not found")
            return {}
        if method == "POST" and path == "bucket":
            self.bucket_exists = True
            return {"name": "source-evidence"}
        if method == "HEAD" and path.startswith("object/"):
            key = path.split("/", 1)[1]
            if key in self.objects:
                return {}
            raise RuntimeError(f"supabase storage HEAD {path} -> 404: not found")
        if method == "POST" and path.startswith("object/list/"):
            return [
                {"name": key, "metadata": {"size": len(body)}, "updated_at": "2020-01-01T00:00:00Z"}
                for key, body in self.objects.items()
            ]
        if method == "DELETE" and path.startswith("object/"):
            key = path.split("/", 1)[1]
            self.objects.pop(key, None)
            return {}
        if method == "POST" and path.startswith("object/"):
            if self.fail_upload:
                raise RuntimeError("supabase storage POST object -> 500: boom")
            key = path.split("/", 1)[1]
            self.objects[key] = data or b""
            return [f"source-evidence/{key}"]
        raise AssertionError(f"unexpected call {method} {path}")


def _evidence_with(transport: FakeTransport) -> EvidenceStore:
    store = EvidenceStore(url="https://example.supabase.co", key="service-token")
    store._request = transport  # type: ignore[assignment]
    return store


def test_gzip_is_deterministic() -> None:
    first = gzip_bytes(b"<html>same</html>")
    second = gzip_bytes(b"<html>same</html>")
    assert first == second
    assert gunzip_bytes(first) == b"<html>same</html>"


def test_evidence_creates_private_bucket_then_uploads_gzip_by_raw_sha() -> None:
    transport = FakeTransport()
    evidence = _evidence_with(transport)
    body = b"<html>official listing</html>"
    path = evidence.put(body, "text/html; charset=utf-8")
    digest = raw_sha256(body)
    assert path == f"{DEFAULT_BUCKET}/{digest}.gz"
    assert transport.bucket_exists
    methods = [c[0] for c in transport.calls]
    assert methods[:2] == ["GET", "POST"]
    assert any(c[0] == "HEAD" for c in transport.calls)
    uploads = [c for c in transport.calls if c[0] == "POST" and c[1].startswith("object/")]
    assert len(uploads) == 1
    assert gunzip_bytes(uploads[0][2] or b"") == body


def test_evidence_skips_upload_when_object_already_exists() -> None:
    transport = FakeTransport()
    evidence = _evidence_with(transport)
    body = b"same bytes"
    first = evidence.put(body)
    second = evidence.put(body)
    assert first == second
    uploads = [c for c in transport.calls if c[0] == "POST" and c[1].startswith("object/")]
    assert len(uploads) == 1
    other = EvidenceStore(url="https://example.supabase.co", key="service-token")
    other._request = transport  # type: ignore[assignment]
    reused = other.put(body)
    assert reused == first
    uploads_after = [c for c in transport.calls if c[0] == "POST" and c[1].startswith("object/")]
    assert len(uploads_after) == 1


def test_evidence_bucket_already_exists_skips_creation() -> None:
    transport = FakeTransport()
    transport.bucket_exists = True
    evidence = _evidence_with(transport)
    evidence.put(b"x")
    methods = [c[0] for c in transport.calls]
    assert "GET" in methods
    assert methods.count("POST") == 1
    assert transport.calls[-1][1].startswith("object/")


def test_evidence_upload_failure_raises() -> None:
    transport = FakeTransport()
    transport.fail_upload = True
    evidence = _evidence_with(transport)
    try:
        evidence.put(b"boom")
    except RuntimeError as exc:
        assert "500" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


class RowCapture:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def __call__(self, method: str, path: str, payload=None, extra: dict | None = None) -> None:
        self.rows.append(payload or {})


def test_rest_store_save_document_skips_upload_unless_kept() -> None:
    transport = FakeTransport()
    store = RestStore(url="https://example.supabase.co", key="service-token")
    store.runs["run-1"] = {"source_id": "src-test"}
    store.evidence = _evidence_with(transport)
    capture = RowCapture()
    store._request = capture  # type: ignore[assignment]

    skipped = store.save_document("run-1", "https://official.example/nav.html", "<html>nav</html>")
    assert skipped["kept"] is False
    assert skipped["storage_path"] is None
    assert capture.rows == []
    uploads = [c for c in transport.calls if c[0] == "POST" and c[1].startswith("object/")]
    assert uploads == []


def test_rest_store_save_document_uploads_gzip_when_kept() -> None:
    transport = FakeTransport()
    store = RestStore(url="https://example.supabase.co", key="service-token")
    store.runs["run-1"] = {"source_id": "src-test"}
    store.evidence = _evidence_with(transport)
    capture = RowCapture()
    store._request = capture  # type: ignore[assignment]

    body = "<html>job</html>"
    result = store.save_document(
        "run-1",
        "https://official.example/job.html",
        body,
        keep=True,
        tier="durable",
    )
    assert result["kept"] is True
    assert result["storage_path"].startswith(f"{DEFAULT_BUCKET}/")
    assert result["raw_sha256"] == sha256(body.encode("utf-8")).hexdigest()
    assert result["raw_sha256"] != ""
    uploads = [c for c in transport.calls if c[0] == "POST" and c[1].startswith("object/")]
    assert len(uploads) == 1
    assert gunzip_bytes(uploads[0][2] or b"") == body.encode("utf-8")
    assert capture.rows[0]["raw_sha256"] == result["raw_sha256"]
    assert capture.rows[0]["text_sha256"] == result["text_sha256"]


def test_rest_store_save_document_pdf_uses_raw_bytes_hash_not_extracted_text() -> None:
    transport = FakeTransport()
    store = RestStore(url="https://example.supabase.co", key="service-token")
    store.runs["run-1"] = {"source_id": "src-pdf"}
    store.evidence = _evidence_with(transport)
    capture = RowCapture()
    store._request = capture  # type: ignore[assignment]

    raw = b"%PDF-1.4 fake-unique"
    text = "extracted text only for deep detail"
    result = store.save_document(
        "run-1",
        "https://xdoc.example/42",
        text,
        status=200,
        content_type="application/pdf",
        raw=raw,
        aux="extracted text",
        keep=True,
        tier="durable",
    )
    assert result["raw_sha256"] == sha256(raw).hexdigest()
    assert result["text_sha256"] == sha256(b"extracted text").hexdigest()
    assert result["raw_sha256"] != result["text_sha256"]
    assert result["storage_path"] != result["aux_object_path"]
    assert raw in transport.objects.values() or any(
        gunzip_bytes(value) == raw for value in transport.objects.values()
    )

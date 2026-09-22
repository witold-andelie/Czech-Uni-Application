from __future__ import annotations

import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.evidence import DEFAULT_BUCKET, EvidenceStore  # noqa: E402
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
    ) -> str:
        self.calls.append((method, path, data))
        if method == "GET" and path.startswith("bucket/"):
            if not self.bucket_exists:
                raise RuntimeError(f"supabase storage GET {path} -> 404: bucket not found")
            return "{}"
        if method == "POST" and path == "bucket":
            self.bucket_exists = True
            return '{"name":"source-evidence"}'
        if method == "POST" and path.startswith("object/"):
            if self.fail_upload:
                raise RuntimeError("supabase storage POST object -> 500: boom")
            key = path.split("/", 1)[1]
            self.objects[key] = data or b""
            return '["source-evidence/' + key + '"]'
        raise AssertionError(f"unexpected call {method} {path}")


def _evidence_with(transport: FakeTransport) -> EvidenceStore:
    store = EvidenceStore(url="https://example.supabase.co", key="service-token")
    store._request = transport  # type: ignore[assignment]
    return store


def test_evidence_creates_private_bucket_then_uploads_by_sha() -> None:
    transport = FakeTransport()
    evidence = _evidence_with(transport)
    body = b"<html>official listing</html>"
    path = evidence.put(body, "text/html; charset=utf-8")
    assert path == f"{DEFAULT_BUCKET}/{sha256(body).hexdigest()}"
    assert transport.bucket_exists
    methods, paths, _ = zip(*transport.calls)
    assert list(methods) == ["GET", "POST", "POST"]
    assert paths[0] == "bucket/source-evidence"
    assert paths[1] == "bucket"
    assert paths[2].startswith("object/source-evidence/")
    assert transport.objects[paths[2].split("/", 1)[1]] == body


def test_evidence_deduplicates_same_sha_within_run() -> None:
    transport = FakeTransport()
    evidence = _evidence_with(transport)
    body = b"same bytes"
    first = evidence.put(body)
    second = evidence.put(body)
    assert first == second
    uploads = [c for c in transport.calls if c[0] == "POST" and c[1].startswith("object/")]
    assert len(uploads) == 1


def test_evidence_bucket_already_exists_skips_creation() -> None:
    transport = FakeTransport()
    transport.bucket_exists = True
    evidence = _evidence_with(transport)
    evidence.put(b"x")
    methods = [c[0] for c in transport.calls]
    assert methods == ["GET", "POST"]
    assert transport.calls[1][1].startswith("object/")


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


def test_rest_store_save_document_uploads_evidence() -> None:
    transport = FakeTransport()
    store = RestStore(url="https://example.supabase.co", key="service-token")
    store.runs["run-1"] = {"source_id": "src-test"}
    store.evidence = _evidence_with(transport)
    capture = RowCapture()
    store._request = capture  # type: ignore[assignment]

    result = store.save_document("run-1", "https://official.example/job.html", "<html>job</html>")
    assert result["storage_path"].startswith(f"{DEFAULT_BUCKET}/")
    assert result["status"] == 200
    assert "aux_object_path" in result and result["aux_object_path"] is None
    uploads = [c for c in transport.calls if c[0] == "POST" and c[1].startswith("object/")]
    assert len(uploads) == 1
    assert uploads[0][2] == b"<html>job</html>"


def test_rest_store_save_document_pdf_uploads_pdf_and_aux_text() -> None:
    transport = FakeTransport()
    store = RestStore(url="https://example.supabase.co", key="service-token")
    store.runs["run-1"] = {"source_id": "src-pdf"}
    store.evidence = _evidence_with(transport)
    capture = RowCapture()
    store._request = capture  # type: ignore[assignment]

    result = store.save_document(
        "run-1",
        "https://xdoc.example/42",
        "extracted text only for deep detail",
        status=200,
        content_type="application/pdf",
        raw=b"%PDF-1.4 fake",
        aux="extracted text",
    )
    assert b"%PDF-1.4 fake" in transport.objects.values()
    assert b"extracted text" in transport.objects.values()
    assert result["storage_path"] != result["aux_object_path"]
    row = capture.rows[0]
    assert row["storage_path"] == result["storage_path"]
    assert row["aux_object_path"] == result["aux_object_path"]
    assert row["content_type"] == "application/pdf"
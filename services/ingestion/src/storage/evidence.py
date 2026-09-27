"""Private Supabase Storage for durable evidence (HTML/JSON/PDF).

Objects are immutable. The object key is the raw SHA-256, plus `.gz` when the
payload is deterministically gzipped. A storage failure raises so the enclosing
source run is marked failed and never completes.

Existence is checked on the bucket (not only an in-process set) so a later run
reuses the same object instead of uploading again. Deleting `storage.objects`
rows in Postgres does not delete files; callers must use this API.
"""

from __future__ import annotations

import json
import os
import ssl
from typing import Any
from urllib.parse import quote
import urllib.error
import urllib.request

from storage.codec import encode_evidence, gzip_bytes
from storage.hashes import raw_sha256

DEFAULT_BUCKET = "source-evidence"
LIST_PAGE = 1000


class EvidenceStore:
    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
        bucket: str = DEFAULT_BUCKET,
    ):
        self.url = (url or os.environ.get("SUPABASE_URL") or "").rstrip("/")
        self.key = (
            key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SECRET_KEY")
            or ""
        )
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required for evidence storage")
        self.bucket = bucket
        self._ctx = ssl.create_default_context()
        self._objects: set[str] = set()
        self._missing: set[str] = set()
        self._bucket_checked = False

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 60,
    ) -> dict[str, Any] | list[Any]:
        req = urllib.request.Request(
            f"{self.url}/storage/v1/{path.lstrip('/')}",
            data=data,
            headers=self._headers(headers),
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=self._ctx) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return _response_value(raw)
        except urllib.error.HTTPError as exc:
            snippet = exc.read().decode("utf-8", errors="replace")[:300].replace(self.key, "[redacted]")
            raise RuntimeError(f"supabase storage {method} {path} -> {exc.code}: {snippet}") from None

    def bucket_exists(self) -> bool:
        try:
            self._request("GET", f"bucket/{quote(self.bucket, safe='')}")
            return True
        except RuntimeError as exc:
            message = str(exc)
            if "-> 404:" in message or "NoSuchBucket" in message:
                return False
            raise

    def ensure_bucket(self) -> None:
        if self.bucket_exists():
            return
        self._request(
            "POST",
            "bucket",
            data=json.dumps({"id": self.bucket, "name": self.bucket, "public": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    def object_key(self, digest: str, compressed: bool) -> str:
        return f"{digest}.gz" if compressed else digest

    def exists(self, key: str) -> bool:
        if key in self._objects:
            return True
        if key in self._missing:
            return False
        if not self._bucket_checked:
            self.ensure_bucket()
            self._bucket_checked = True
        try:
            self._request("HEAD", f"object/{quote(self.bucket, safe='')}/{key}")
            self._objects.add(key)
            return True
        except RuntimeError as exc:
            message = str(exc)
            if "-> 404:" in message or "-> 400:" in message:
                self._missing.add(key)
                return False
            raise

    def put(self, body: bytes, content_type: str = "text/html; charset=utf-8") -> str:
        digest = raw_sha256(body)
        payload, suffix, compressed = encode_evidence(body, content_type)
        key = f"{digest}{suffix}"
        content = "application/gzip" if compressed else (content_type or "application/octet-stream")
        return self.upload(key, payload, content)

    def put_text(self, text: str) -> str | None:
        if not text or not text.strip():
            return None
        encoded = text.encode("utf-8")
        digest = raw_sha256(encoded)
        payload = gzip_bytes(encoded)
        return self.upload(f"{digest}.gz", payload, "application/gzip")

    def upload(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> str:
        path = f"{self.bucket}/{key}"
        if self.exists(key):
            return path
        if not self._bucket_checked:
            self.ensure_bucket()
            self._bucket_checked = True
        self._request(
            "POST",
            f"object/{quote(self.bucket, safe='')}/{key}",
            data=body,
            headers={
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )
        self._objects.add(key)
        self._missing.discard(key)
        return path

    def delete(self, key: str) -> None:
        self._request("DELETE", f"object/{quote(self.bucket, safe='')}/{key}")
        self._objects.discard(key)
        self._missing.add(key)

    def list_objects(self, prefix: str = "", *, limit: int = LIST_PAGE) -> list[dict[str, Any]]:
        """Paginated object listing. Each item has name and metadata.size when present."""
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = {
                "prefix": prefix,
                "limit": limit,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            }
            chunk = self._request(
                "POST",
                f"object/list/{quote(self.bucket, safe='')}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            items = chunk if isinstance(chunk, list) else []
            rows.extend(item for item in items if isinstance(item, dict))
            if len(items) < limit:
                break
            offset += limit
        return rows


def _response_value(raw: bytes) -> dict[str, Any] | list[Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    return {}

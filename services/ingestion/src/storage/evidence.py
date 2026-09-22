"""Private Supabase Storage evidence for raw fetched bodies (HTML, JSON, PDF).

Objects are immutable and deduplicated by SHA-256: the object key *is* the
digest. A storage failure raises so the enclosing source run is marked failed
and never completes.
"""

from __future__ import annotations

import json
import os
import ssl
from hashlib import sha256
from typing import Any
from urllib.parse import quote
import urllib.error
import urllib.request

DEFAULT_BUCKET = "source-evidence"


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
    ) -> dict[str, Any]:
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
                return _response_json(raw)
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

    def put(self, body: bytes, content_type: str = "text/html; charset=utf-8") -> str:
        key = sha256(body).hexdigest()
        return self.upload(key, body, content_type)

    def upload(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> str:
        path = f"{self.bucket}/{key}"
        if key in self._objects:
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
        return path

    def put_text(self, text: str) -> str | None:
        if not text or not text.strip():
            return None
        return self.put(text.encode("utf-8"), "text/plain; charset=utf-8")


def _response_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
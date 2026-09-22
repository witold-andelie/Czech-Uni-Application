"""Supabase Data API store over HTTPS. Used on GitHub Actions so we never need paid IPv4."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4
from urllib.parse import quote
import json
import os
import ssl
import urllib.error
import urllib.request

from storage.evidence import EvidenceStore
from storage.facts import job_fact_hash


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_lease_owner() -> str:
    run = os.environ.get("GITHUB_RUN_ID")
    if run:
        return f"github-actions-{run}"
    host = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown"
    return f"local-{host}"


class RestStore:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url or os.environ.get("SUPABASE_URL") or "").rstrip("/")
        self.key = (
            key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SECRET_KEY")
            or ""
        )
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required for HTTPS ingest")
        self.runs: dict[str, dict[str, Any]] = {}
        self.evidence = EvidenceStore(self.url, self.key)
        self._ctx = ssl.create_default_context()

    def close(self) -> None:
        return None

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method: str, path: str, payload: Any = None, extra: dict[str, str] | None = None) -> Any:
        body = None if payload is None else json.dumps(payload, default=str).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{path.lstrip('/')}",
            data=body,
            headers=self._headers(extra),
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=self._ctx) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            snippet = exc.read().decode("utf-8", errors="replace")[:300].replace(self.key, "[redacted]")
            raise RuntimeError(f"supabase REST {method} {path} -> {exc.code}: {snippet}") from None

    def ping(self) -> dict[str, Any]:
        rows = self._request("GET", "ingest_source?select=id&limit=1")
        return {"ok": True, "transport": "https-data-api", "sourcesSample": len(rows or [])}

    def source_count(self) -> int:
        extra = {"Prefer": "count=exact", "Range": "0-0"}
        req = urllib.request.Request(
            f"{self.url}/rest/v1/ingest_source?select=id",
            headers=self._headers(extra),
            method="HEAD",
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=self._ctx) as resp:
                content_range = resp.headers.get("content-range") or "*/0"
                return int(content_range.rsplit("/", 1)[-1])
        except urllib.error.HTTPError as exc:
            content_range = exc.headers.get("content-range") if exc.headers else None
            if content_range and "/" in content_range:
                return int(content_range.rsplit("/", 1)[-1])
            raise

    def upsert_source(self, row: dict[str, Any]) -> None:
        payload = dict(row)
        if isinstance(payload.get("config"), str):
            payload["config"] = json.loads(payload["config"] or "{}")
        self._request(
            "POST",
            "ingest_source?on_conflict=id",
            payload,
            extra={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    def ensure_source(self, source_id: str) -> None:
        found = self._request("GET", f"ingest_source?id=eq.{quote(source_id, safe='')}&select=id")
        if found:
            return
        self.upsert_source(
            {
                "id": source_id,
                "institution_id": None,
                "entity_kind": "research_job",
                "source_kind": "official_job_listing",
                "adapter_key": "unknown",
                "entry_url": "https://invalid.example/missing-registry",
                "official_host": "invalid.example",
                "allowed_hosts": ["invalid.example"],
                "coverage_scope": "unspecified",
                "coverage_claim": "not_asserted",
                "cadence_seconds": 14400,
                "config": {},
                "enabled": True,
            }
        )

    def claim_run(self, run_id: str, owner: str | None = None, lease_seconds: int = 900) -> str | None:
        payload = {
            "p_run": run_id,
            "p_owner": owner or _default_lease_owner(),
            "p_lease_seconds": lease_seconds,
        }
        rows = self._request("POST", "rpc/rpc_claim_run", payload, extra={"Prefer": "return=representation"})
        if not rows:
            return None
        token = rows.get("token")
        return str(token) if token else None

    def heartbeat_run(self, run_id: str, token: str, lease_seconds: int = 900) -> bool:
        rows = self._request(
            "POST",
            "rpc/rpc_heartbeat_run",
            {"p_run": run_id, "p_token": token, "p_lease_seconds": lease_seconds},
            extra={"Prefer": "return=representation"},
        )
        return bool(rows and rows.get("ok") is True)

    def release_run(self, run_id: str, token: str) -> bool:
        rows = self._request(
            "POST",
            "rpc/rpc_release_run",
            {"p_run": run_id, "p_token": token},
            extra={"Prefer": "return=representation"},
        )
        return bool(rows and rows.get("ok") is True)

    def start_run(self, source: dict, scheduled_for: datetime | None = None, lease_seconds: int = 900) -> dict[str, Any]:
        source_id = source["id"]
        self.ensure_source(source_id)
        run_id = str(uuid4())
        scheduled = scheduled_for or _now()
        payload = {
            "id": run_id,
            "source_id": source_id,
            "scheduled_for": scheduled.isoformat(),
            "started_at": _now().isoformat(),
            "status": "running",
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "git_commit": os.environ.get("GITHUB_SHA"),
        }
        self._request("POST", "ingest_source_run", payload, extra={"Prefer": "return=minimal"})
        token = self.claim_run(run_id, lease_seconds=lease_seconds)
        if token is None:
            self._request(
                "PATCH",
                f"ingest_source_run?id=eq.{run_id}",
                {"status": "failed", "error_class": "lease-conflict"},
                extra={"Prefer": "return=minimal"},
            )
            raise RuntimeError(f"could not claim run lease for source {source_id}")
        run = {
            "id": run_id,
            "source_id": source_id,
            "scheduled_for": payload["scheduled_for"],
            "status": "running",
            "listing_complete": False,
            "listed_count": 0,
            "parsed_count": 0,
            "error_class": None,
            "lease_token": token,
        }
        self.runs[run_id] = run
        return run

    def save_document(
        self,
        run_id: str,
        url: str,
        body: str,
        status: int = 200,
        content_type: str | None = None,
        raw: bytes | None = None,
        aux: str | None = None,
    ) -> dict[str, Any]:
        digest = sha256((body or "").encode("utf-8")).hexdigest()
        source_id = (self.runs.get(run_id) or {}).get("source_id")
        if raw is not None:
            storage_path = self.evidence.put(raw, content_type or "application/pdf")
            aux_path = self.evidence.put_text(aux if aux is not None else body)
        else:
            storage_path = self.evidence.put(
                (body or "").encode("utf-8"),
                content_type or "text/html; charset=utf-8",
            )
            aux_path = None
        self._request(
            "POST",
            "ingest_raw_document?on_conflict=sha256",
            {
                "source_id": source_id,
                "run_id": run_id,
                "requested_url": url,
                "final_url": url,
                "http_status": status,
                "content_type": content_type or "text/html",
                "sha256": digest,
                "storage_path": storage_path,
                "aux_object_path": aux_path,
            },
            extra={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        return {
            "sha256": digest,
            "url": url,
            "status": status,
            "storage_path": storage_path,
            "aux_object_path": aux_path,
        }

    def save_observation(self, run_id: str, remote_id: str, detail_url: str, title: str, present: bool = True) -> None:
        self._request(
            "POST",
            "ingest_listing_observation",
            {
                "run_id": run_id,
                "remote_key": remote_id,
                "detail_url": detail_url,
                "title": title,
                "present": present,
            },
            extra={"Prefer": "return=minimal"},
        )

    def upsert_job(
        self,
        *,
        source_id: str,
        employer_id: str | None,
        remote_id: str,
        official_detail_url: str,
        facts: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        external_id = f"{employer_id or source_id}:{remote_id}"
        digest = job_fact_hash(facts, official_detail_url)
        self._request(
            "POST",
            "catalog_research_job?on_conflict=external_id",
            {
                "external_id": external_id,
                "employer_id": employer_id,
                "remote_id": remote_id,
                "official_detail_url": official_detail_url,
                "lifecycle": "discovered",
                "visibility": "private",
                "consecutive_complete_run_absence": 0,
            },
            extra={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        rows = self._request("GET", f"catalog_research_job?external_id=eq.{quote(external_id, safe='')}&select=id")
        job_id = rows[0]["id"]
        existing_versions = (
            self._request(
                "GET",
                f"catalog_research_job_version?job_id=eq.{job_id}&select=id,fact_hash",
            )
            or []
        )
        known_hashes = {row.get("fact_hash") for row in existing_versions}
        self._request(
            "POST",
            "catalog_research_job_version?on_conflict=job_id,fact_hash",
            {
                "job_id": job_id,
                "source_run_id": run_id,
                "fact_hash": digest,
                "source_title": facts.get("title"),
                "official_detail_url": official_detail_url,
                "application_url": facts.get("application_url"),
                "scope_classification": facts.get("scope_classification"),
                "paid_status": facts.get("paid_status"),
                "url_directness": facts.get("url_directness"),
                "facts": facts,
                "review_state": "required",
            },
            extra={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        versions = self._request(
            "GET",
            f"catalog_research_job_version?job_id=eq.{job_id}&fact_hash=eq.{digest}&select=id",
        )
        version_id = versions[0]["id"]
        if digest not in known_hashes:
            self._request(
                "PATCH",
                f"catalog_research_job_version?job_id=eq.{job_id}&fact_hash=neq.{quote(digest, safe='')}",
                {"review_state": "stale"},
                extra={"Prefer": "return=minimal"},
            )
        self._request(
            "PATCH",
            f"catalog_research_job?id=eq.{job_id}",
            {"preferred_version_id": version_id, "last_seen_at": _now().isoformat(), "consecutive_complete_run_absence": 0},
            extra={"Prefer": "return=minimal"},
        )
        return {"id": external_id, "job_id": str(job_id), "version_id": str(version_id)}

    def upsert_programme(
        self,
        *,
        source_id: str,
        institution_id: str | None,
        remote_id: str,
        official_detail_url: str,
        facts: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        external_id = f"{institution_id or source_id}:{remote_id}"
        digest = job_fact_hash(facts, official_detail_url)
        self._request(
            "POST",
            "catalog_programme?on_conflict=external_id",
            {
                "external_id": external_id,
                "institution_id": institution_id,
                "official_code": remote_id,
                "official_detail_url": official_detail_url,
                "lifecycle": "discovered",
                "visibility": "private",
            },
            extra={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        rows = self._request("GET", f"catalog_programme?external_id=eq.{quote(external_id, safe='')}&select=id")
        programme_id = rows[0]["id"]
        existing_versions = (
            self._request(
                "GET",
                f"catalog_programme_version?programme_id=eq.{programme_id}&select=id,fact_hash",
            )
            or []
        )
        known_hashes = {row.get("fact_hash") for row in existing_versions}
        self._request(
            "POST",
            "catalog_programme_version?on_conflict=programme_id,fact_hash",
            {
                "programme_id": programme_id,
                "source_run_id": run_id,
                "fact_hash": digest,
                "source_title": facts.get("title"),
                "official_detail_url": official_detail_url,
                "degree": facts.get("degree"),
                "facts": facts,
                "review_state": "required",
            },
            extra={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        versions = self._request(
            "GET",
            f"catalog_programme_version?programme_id=eq.{programme_id}&fact_hash=eq.{digest}&select=id",
        )
        version_id = versions[0]["id"]
        if digest not in known_hashes:
            self._request(
                "PATCH",
                f"catalog_programme_version?programme_id=eq.{programme_id}&fact_hash=neq.{quote(digest, safe='')}",
                {"review_state": "stale"},
                extra={"Prefer": "return=minimal"},
            )
        self._request(
            "PATCH",
            f"catalog_programme?id=eq.{programme_id}",
            {"preferred_version_id": version_id, "last_seen_at": _now().isoformat()},
            extra={"Prefer": "return=minimal"},
        )
        return {"id": external_id, "programme_id": str(programme_id), "version_id": str(version_id)}

    def list_external_ids(self, *, employer_id: str | None = None) -> list[str]:
        path = "catalog_research_job?select=external_id"
        if employer_id:
            path += f"&employer_id=eq.{quote(employer_id, safe='')}"
        rows = self._request("GET", path) or []
        return [str(row["external_id"]) for row in rows if row.get("external_id")]

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        listing_complete: bool,
        listed_count: int,
        parsed_count: int,
        error_class: str | None = None,
    ) -> None:
        self._request(
            "PATCH",
            f"ingest_source_run?id=eq.{run_id}",
            {
                "finished_at": _now().isoformat(),
                "status": status,
                "listing_complete": listing_complete,
                "listed_count": listed_count,
                "parsed_count": parsed_count,
                "error_class": error_class,
            },
            extra={"Prefer": "return=minimal"},
        )
        token = (self.runs.get(run_id) or {}).get("lease_token")
        if token:
            self.release_run(run_id, str(token))
        if run_id in self.runs:
            self.runs[run_id].update(
                {
                    "status": status,
                    "listing_complete": listing_complete,
                    "listed_count": listed_count,
                    "parsed_count": parsed_count,
                    "error_class": error_class,
                }
            )

    def mark_absent(self, job_id: str) -> None:
        rows = self._request(
            "GET",
            f"catalog_research_job?external_id=eq.{quote(job_id, safe='')}&select=consecutive_complete_run_absence",
        )
        current = int((rows or [{}])[0].get("consecutive_complete_run_absence") or 0)
        self._request(
            "PATCH",
            f"catalog_research_job?external_id=eq.{quote(job_id, safe='')}",
            {"consecutive_complete_run_absence": current + 1},
            extra={"Prefer": "return=minimal"},
        )

    def list_source_runs(self, source_id: str | None = None) -> list[dict[str, Any]]:
        path = "ingest_source_run?select=id,source_id,started_at,scheduled_for,status&order=started_at.desc&limit=1000"
        if source_id:
            path = (
                "ingest_source_run?source_id=eq."
                + quote(source_id, safe="")
                + "&select=id,source_id,started_at,scheduled_for,status&order=started_at.desc&limit=1000"
            )
        return self._request("GET", path) or []

    def delete_run(self, run_id: str) -> None:
        ident = quote(run_id, safe="")
        extra = {"Prefer": "return=minimal"}
        self._request("DELETE", f"ingest_listing_observation?run_id=eq.{ident}", extra=extra)
        self._request(
            "PATCH",
            f"catalog_research_job_version?source_run_id=eq.{ident}",
            {"source_run_id": None},
            extra=extra,
        )
        self._request(
            "PATCH",
            f"ingest_raw_document?run_id=eq.{ident}",
            {"run_id": None},
            extra=extra,
        )
        self._request("DELETE", f"ingest_source_run?id=eq.{ident}", extra=extra)
        self.runs.pop(run_id, None)

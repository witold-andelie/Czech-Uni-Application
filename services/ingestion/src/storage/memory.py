"""In-memory ingest store used by adapter tests. No records are closed here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from storage.facts import job_fact_hash


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class MemoryStore:
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    documents: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    programmes: dict[str, dict[str, Any]] = field(default_factory=dict)
    versions: list[dict[str, Any]] = field(default_factory=list)

    def start_run(self, source: dict, scheduled_for: str | None = None) -> dict[str, Any]:
        run = {
            "id": str(uuid4()),
            "source_id": source["id"],
            "scheduled_for": scheduled_for or _now(),
            "started_at": _now(),
            "finished_at": None,
            "status": "running",
            "listing_complete": False,
            "listed_count": 0,
            "parsed_count": 0,
            "error_class": None,
        }
        self.runs[run["id"]] = run
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
        digest = sha256(body.encode("utf-8")).hexdigest()
        row = {
            "id": str(uuid4()),
            "run_id": run_id,
            "url": url,
            "status": status,
            "sha256": digest,
            "bytes": len(body.encode("utf-8")),
            "content_type": content_type or "text/html",
            "storage_path": None,
            "aux_object_path": None,
        }
        self.documents.append(row)
        return row

    def save_observation(self, run_id: str, remote_id: str, detail_url: str, title: str, present: bool = True) -> None:
        self.observations.append(
            {
                "run_id": run_id,
                "remote_id": remote_id,
                "detail_url": detail_url,
                "title": title,
                "present": present,
            }
        )

    def list_external_ids(self, *, employer_id: str | None = None) -> list[str]:
        if employer_id is None:
            return list(self.jobs)
        return [key for key, job in self.jobs.items() if job.get("employer_id") == employer_id]

    def upsert_job(self, *, source_id: str, employer_id: str | None, remote_id: str, official_detail_url: str, facts: dict[str, Any], run_id: str | None = None) -> dict[str, Any]:
        key = f"{employer_id or source_id}:{remote_id}"
        existing = self.jobs.get(key)
        digest = job_fact_hash(facts, official_detail_url)
        if existing is None:
            job = {
                "id": key,
                "remote_id": remote_id,
                "employer_id": employer_id,
                "official_detail_url": official_detail_url,
                "first_seen_at": _now(),
                "last_seen_at": _now(),
                "preferred_version_id": None,
                "consecutive_absence": 0,
            }
            self.jobs[key] = job
        else:
            job = existing
            job["last_seen_at"] = _now()
            job["official_detail_url"] = official_detail_url
        prior = next((item for item in reversed(self.versions) if item["job_id"] == job["id"]), None)
        if prior is None or prior["fact_hash"] != digest:
            version = {
                "id": str(uuid4()),
                "job_id": job["id"],
                "fact_hash": digest,
                "facts": dict(facts),
                "created_at": _now(),
            }
            self.versions.append(version)
            job["preferred_version_id"] = version["id"]
            if prior is not None:
                prior["review_stale"] = True
        return job

    def finish_run(self, run_id: str, *, status: str, listing_complete: bool, listed_count: int, parsed_count: int, error_class: str | None = None) -> None:
        run = self.runs[run_id]
        run["finished_at"] = _now()
        run["status"] = status
        run["listing_complete"] = listing_complete
        run["listed_count"] = listed_count
        run["parsed_count"] = parsed_count
        run["error_class"] = error_class

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
        existing = self.programmes.get(external_id)
        if existing is None:
            row = {
                "id": external_id,
                "remote_id": remote_id,
                "institution_id": institution_id,
                "official_detail_url": official_detail_url,
                "first_seen_at": _now(),
                "last_seen_at": _now(),
                "preferred_version_id": None,
                "lifecycle": "discovered",
                "visibility": "private",
            }
            self.programmes[external_id] = row
        else:
            row = existing
            row["last_seen_at"] = _now()
            row["official_detail_url"] = official_detail_url
        prior = next((item for item in reversed(self.versions) if item.get("prog_id") == row["id"]), None)
        if prior is None or prior["fact_hash"] != digest:
            version = {
                "id": str(uuid4()),
                "prog_id": row["id"],
                "fact_hash": digest,
                "facts": dict(facts),
                "created_at": _now(),
            }
            self.versions.append(version)
            row["preferred_version_id"] = version["id"]
            if prior is not None:
                prior["review_stale"] = True
        return row

    def mark_absent(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job["consecutive_absence"] = int(job.get("consecutive_absence") or 0) + 1

    def list_source_runs(self, source_id: str | None = None) -> list[dict[str, Any]]:
        rows = list(self.runs.values())
        if source_id:
            rows = [row for row in rows if row.get("source_id") == source_id]
        rows.sort(key=lambda row: row.get("started_at") or "", reverse=True)
        return rows

    def delete_run(self, run_id: str) -> None:
        self.observations = [row for row in self.observations if row.get("run_id") != run_id]
        self.documents = [row for row in self.documents if row.get("run_id") != run_id]
        self.runs.pop(run_id, None)

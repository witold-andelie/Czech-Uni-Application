"""Postgres store for ingest runs. Credentials come from the environment only."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4
import json
import os

from storage.facts import job_fact_hash

ROOT = Path(__file__).resolve().parents[4]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _programme_facts_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Facts dict for one studyin listing row, matching the shape
    ``RestStore.upsert_programme`` receives so fact hashes stay canonical."""
    return {
        "title": str(row.get("title") or ""),
        "official_detail_url": str(row.get("sourceUrl") or ""),
        "degree": row.get("degree"),
        "application_url": row.get("applicationUrl"),
        "catalogue": row.get("catalogue"),
        "evidenceRecordSha256": row.get("evidenceRecordSha256"),
        "educationalDegree": row.get("degree"),
        "study_form": row.get("studyForms"),
        "study_language": row.get("studyLanguage"),
        "institution_names": row.get("institutionNames"),
        "faculty_names": row.get("facultyNames"),
        "fields": row.get("fields"),
        "duration": row.get("durationYears"),
        "credit_note": row.get("credits"),
        "official_title": {row.get("studyLanguage") or "cs": str(row.get("title") or "")},
    }


def env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def load_database_env(path: Path | None = None) -> None:
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def dsn_from_env() -> str:
    explicit = os.environ.get("SUPABASE_DB_URL", "").strip()
    if explicit:
        return explicit
    password = os.environ.get("SUPABASE_DB_PASSWORD", "")
    ref = os.environ.get("SUPABASE_PROJECT_REF", "")
    if not password or not ref:
        raise RuntimeError("SUPABASE_DB_URL or SUPABASE_DB_PASSWORD + SUPABASE_PROJECT_REF required")
    return (
        f"postgresql://postgres:{quote(password, safe='')}@"
        f"db.{ref}.supabase.co:5432/postgres?sslmode=require"
    )


def postgres_configured() -> bool:
    load_database_env()
    if os.environ.get("SUPABASE_DB_URL", "").strip():
        return True
    return bool(os.environ.get("SUPABASE_DB_PASSWORD", "").strip() and os.environ.get("SUPABASE_PROJECT_REF", "").strip())


def rest_configured() -> bool:
    load_database_env()
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
        or ""
    ).strip()
    return bool(url and key)


def configured() -> bool:
    return rest_configured() or postgres_configured()


def persist_enabled() -> bool:
    """GitHub Actions and explicit local writes. Pytest never talks to production."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    if env_flag("SUPABASE_REQUIRED") or env_flag("SUPABASE_WRITE"):
        return True
    return os.environ.get("GITHUB_ACTIONS") == "true"


def require_database() -> None:
    if env_flag("SUPABASE_REQUIRED") and not configured():
        raise SystemExit(
            "Supabase is required on this runner (SUPABASE_REQUIRED=1) "
            "but SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are missing. "
            "Do not buy Dedicated IPv4; GitHub Actions uses the HTTPS Data API."
        )


def store_from_env():
    require_database()
    if not configured():
        return None
    use_rest = env_flag("SUPABASE_USE_REST") or os.environ.get("GITHUB_ACTIONS") == "true"
    if rest_configured() and (use_rest or not postgres_configured()):
        from storage.rest import RestStore

        return RestStore()
    if postgres_configured():
        return PostgresStore()
    from storage.rest import RestStore

    return RestStore()


def job_title(job: dict[str, Any]) -> str:
    title = job.get("title")
    if isinstance(title, dict):
        return str(title.get("en") or title.get("cs") or title.get("zh-CN") or next(iter(title.values()), "") or "")
    if title:
        return str(title)
    return str(job.get("originalText") or "")


class PostgresStore:
    def __init__(self, dsn: str | None = None):
        import psycopg

        self._psycopg = psycopg
        self._conn = psycopg.connect(dsn or dsn_from_env(), autocommit=True)
        self.runs: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        self._conn.close()

    def ping(self) -> dict[str, Any]:
        user, database = self._conn.execute("select current_user, current_database()").fetchone()
        sources = int(self._conn.execute("select count(*) from ingest.source").fetchone()[0])
        return {"ok": True, "user": user, "database": database, "sources": sources}

    def upsert_source(self, row: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO ingest.source (
              id, institution_id, entity_kind, source_kind, adapter_key,
              entry_url, official_host, allowed_hosts, coverage_scope,
              coverage_claim, cadence_seconds, config, enabled, updated_at
            ) VALUES (
              %(id)s, %(institution_id)s, %(entity_kind)s, %(source_kind)s, %(adapter_key)s,
              %(entry_url)s, %(official_host)s, %(allowed_hosts)s, %(coverage_scope)s,
              %(coverage_claim)s, %(cadence_seconds)s, %(config)s::jsonb, %(enabled)s, now()
            )
            ON CONFLICT (id) DO UPDATE SET
              institution_id = EXCLUDED.institution_id,
              entity_kind = EXCLUDED.entity_kind,
              source_kind = EXCLUDED.source_kind,
              adapter_key = EXCLUDED.adapter_key,
              entry_url = EXCLUDED.entry_url,
              official_host = EXCLUDED.official_host,
              allowed_hosts = EXCLUDED.allowed_hosts,
              coverage_scope = EXCLUDED.coverage_scope,
              coverage_claim = EXCLUDED.coverage_claim,
              cadence_seconds = EXCLUDED.cadence_seconds,
              config = EXCLUDED.config,
              enabled = EXCLUDED.enabled,
              updated_at = now()
            """,
            row,
        )

    def patch_source(self, source_id: str, fields: dict[str, Any]) -> None:
        self._conn.execute(
            "UPDATE ingest.source SET updated_at = now() WHERE id = %s",
            (source_id,),
        )
        for key, value in fields.items():
            self._conn.execute(
                f"UPDATE ingest.source SET {key} = %s WHERE id = %s",
                (value, source_id),
            )

    def source_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM ingest.source").fetchone()[0])

    def ensure_source(self, source_id: str) -> None:
        exists = self._conn.execute("select 1 from ingest.source where id = %s", (source_id,)).fetchone()
        if exists:
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
                "config": "{}",
                "enabled": True,
            }
        )

    def start_run(self, source: dict, scheduled_for: datetime | None = None) -> dict[str, Any]:
        source_id = source["id"]
        self.ensure_source(source_id)
        run_id = str(uuid4())
        scheduled = scheduled_for or _now()
        github_run = os.environ.get("GITHUB_RUN_ID")
        git_commit = os.environ.get("GITHUB_SHA")
        self._conn.execute(
            """
            INSERT INTO ingest.source_run (
              id, source_id, scheduled_for, started_at, status,
              github_run_id, git_commit
            ) VALUES (%s, %s, %s, now(), 'running', %s, %s)
            """,
            (run_id, source_id, scheduled, github_run, git_commit),
        )
        run = {
            "id": run_id,
            "source_id": source_id,
            "scheduled_for": scheduled.isoformat(),
            "status": "running",
            "listing_complete": False,
            "listed_count": 0,
            "parsed_count": 0,
            "error_class": None,
        }
        self.runs[run_id] = run
        return run

    def save_document(self, run_id: str, url: str, body: str, status: int = 200) -> dict[str, Any]:
        digest = sha256((body or "").encode("utf-8")).hexdigest()
        source_id = (self.runs.get(run_id) or {}).get("source_id")
        if source_id is None:
            source_id = self._conn.execute(
                "select source_id from ingest.source_run where id = %s", (run_id,)
            ).fetchone()[0]
        self._conn.execute(
            """
            INSERT INTO ingest.raw_document (
              source_id, run_id, requested_url, final_url, http_status, sha256
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (sha256) DO UPDATE SET
              run_id = EXCLUDED.run_id,
              http_status = EXCLUDED.http_status
            """,
            (source_id, run_id, url, url, status, digest),
        )
        return {"sha256": digest, "url": url, "status": status}

    def save_observation(self, run_id: str, remote_id: str, detail_url: str, title: str, present: bool = True) -> None:
        self._conn.execute(
            """
            INSERT INTO ingest.listing_observation (
              run_id, remote_key, detail_url, title, present
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (run_id, remote_id, detail_url, title, present),
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
        row = self._conn.execute(
            """
            INSERT INTO catalog.research_job (
              external_id, employer_id, remote_id, official_detail_url,
              first_seen_at, last_seen_at, last_complete_run_at,
              lifecycle, visibility, consecutive_complete_run_absence
            ) VALUES (%s, %s, %s, %s, now(), now(), now(), 'discovered', 'private', 0)
            ON CONFLICT (external_id) DO UPDATE SET
              official_detail_url = EXCLUDED.official_detail_url,
              last_seen_at = now(),
              last_complete_run_at = now(),
              consecutive_complete_run_absence = 0
            RETURNING id
            """,
            (external_id, employer_id, remote_id, official_detail_url),
        ).fetchone()
        job_id = row[0]
        known = {
            item[0]
            for item in self._conn.execute(
                "select fact_hash from catalog.research_job_version where job_id = %s",
                (job_id,),
            ).fetchall()
        }
        version = self._conn.execute(
            """
            INSERT INTO catalog.research_job_version (
              job_id, source_run_id, fact_hash, source_title, official_detail_url,
              application_url, scope_classification, paid_status, facts, review_state
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'required')
            ON CONFLICT (job_id, fact_hash) DO UPDATE SET
              source_run_id = COALESCE(EXCLUDED.source_run_id, catalog.research_job_version.source_run_id)
            RETURNING id
            """,
            (
                job_id,
                run_id,
                digest,
                facts.get("title"),
                official_detail_url,
                facts.get("application_url"),
                facts.get("scope_classification"),
                facts.get("paid_status"),
                json.dumps(facts, ensure_ascii=False, default=str),
            ),
        ).fetchone()
        self._conn.execute(
            "UPDATE catalog.research_job SET preferred_version_id = %s WHERE id = %s",
            (version[0], job_id),
        )
        if digest not in known:
            self._conn.execute(
                "update catalog.research_job_version set review_state = 'stale' where job_id = %s and fact_hash <> %s",
                (job_id, digest),
            )
        return {"id": external_id, "job_id": str(job_id), "version_id": str(version[0])}

    def list_external_ids(self, *, employer_id: str | None = None) -> list[str]:
        if employer_id:
            rows = self._conn.execute(
                "select external_id from catalog.research_job where employer_id = %s",
                (employer_id,),
            ).fetchall()
        else:
            rows = self._conn.execute("select external_id from catalog.research_job").fetchall()
        return [row[0] for row in rows]

    def bulk_upsert_programmes(
        self,
        *,
        source: dict[str, Any],
        rows: list[dict[str, Any]],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Bulk write of offline programme catalogue identities in one transaction.

        Mirrors ``RestStore.upsert_programme`` semantics (external id
        ``{institutionId}:{remoteId}`` with the source-level ``employerId``,
        canonical job fact hash over the variant title, private/discovered/
        required defaults) but executes each step as a single set-based
        statement over ``UNNEST`` arrays instead of RPC per record (or per-row
        round-trip), so a 5k-row catalogue needs only a handful of round-trips.
        Stale tiering and preferred-version pointing are preserved so a re-run
        over the same evidence is idempotent.
        """
        if not rows:
            return {"written": 0, "created": 0, "stale": 0}
        account = source.get("employerId") or source.get("id") or "studyin"
        program_cols: list[list[Any]] = [[], [], [], []]
        version_cols: list[list[Any]] = [[], [], [], [], []]
        for row in rows:
            remote_id = str(row.get("code") or row.get("sourceStableId") or "")
            detail_url = str(row.get("sourceUrl") or "")
            external_id = f"{account}:{remote_id}"
            facts = _programme_facts_from_row(row)
            digest = job_fact_hash(facts, detail_url)
            program_cols[0].append(external_id)
            program_cols[1].append(account)
            program_cols[2].append(remote_id)
            program_cols[3].append(detail_url)
            version_cols[0].append(external_id)
            version_cols[1].append(digest)
            version_cols[2].append(str(facts.get("title") or ""))
            version_cols[3].append(detail_url)
            version_cols[4].append(facts.get("degree"))
        external_ids = program_cols[0]
        with self._conn.transaction():
            existing = {
                str(r[0])
                for r in self._conn.execute(
                    "select external_id from catalog.programme where external_id = any(%s)",
                    (external_ids,),
                ).fetchall()
            }
            created = [external_id for external_id in external_ids if external_id not in existing]
            self._conn.execute(
                """
                INSERT INTO catalog.programme (
                  external_id, institution_id, official_code, official_detail_url,
                  lifecycle, visibility
                )
                SELECT x.external_id, x.institution_id, x.official_code, x.official_detail_url,
                       'discovered', 'private'
                FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[])
                  AS x(external_id, institution_id, official_code, official_detail_url)
                ON CONFLICT (external_id) DO UPDATE SET
                  official_detail_url = EXCLUDED.official_detail_url,
                  last_seen_at = now()
                RETURNING id, external_id
                """,
                (*program_cols,),
            ).fetchall()
            known_by_external: dict[str, set[str]] = {}
            for external_id, fact_hash in self._conn.execute(
                """
                select p.external_id, pv.fact_hash
                from catalog.programme_version pv
                join catalog.programme p on p.id = pv.programme_id
                where p.external_id = any(%s)
                """,
                (external_ids,),
            ).fetchall():
                known_by_external.setdefault(str(external_id), set()).add(str(fact_hash))
            self._conn.execute(
                """
                INSERT INTO catalog.programme_version (
                  programme_id, source_run_id, fact_hash, source_title,
                  official_detail_url, degree, review_state
                )
                SELECT p.id, %s, v.fact_hash, v.source_title, v.official_detail_url,
                       v.degree, 'required'
                FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[], %s::text[])
                  AS v(external_id, fact_hash, source_title, official_detail_url, degree)
                JOIN catalog.programme p ON p.external_id = v.external_id
                ON CONFLICT (programme_id, fact_hash) DO UPDATE SET
                  official_detail_url = EXCLUDED.official_detail_url
                """,
                (run_id, *version_cols),
            )
            version_by_external = dict(
                self._conn.execute(
                    """
                    select w.external_id, pv.id
                    from unnest(%s::text[], %s::text[])
                      as w(external_id, wanted_hash)
                    join catalog.programme p on p.external_id = w.external_id
                    join catalog.programme_version pv on pv.programme_id = p.id and pv.fact_hash = w.wanted_hash
                    """,
                    (external_ids, version_cols[1]),
                ).fetchall()
            )
            stale_ids = self._conn.execute(
                """
                UPDATE catalog.programme_version pv SET review_state = 'stale'
                FROM catalog.programme p,
                     unnest(%s::text[], %s::text[])
                       AS s(external_id, wanted_hash)
                WHERE p.id = pv.programme_id
                  AND p.external_id = s.external_id
                  AND pv.fact_hash <> s.wanted_hash
                  AND pv.review_state <> 'stale'
                RETURNING p.external_id
                """,
                (external_ids, version_cols[1]),
            ).fetchall()
            self._conn.execute(
                """
                UPDATE catalog.programme p SET preferred_version_id = v.version_id, last_seen_at = now()
                FROM unnest(%s::text[], %s::uuid[])
                  AS v(external_id, version_id)
                WHERE p.external_id = v.external_id
                """,
                (
                    list(version_by_external.keys()),
                    [str(vid) for vid in version_by_external.values()],
                ),
            )
        return {"written": len(rows), "created": len(created), "stale": len(stale_ids)}

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
        self._conn.execute(
            """
            UPDATE ingest.source_run SET
              finished_at = now(),
              status = %s,
              listing_complete = %s,
              listed_count = %s,
              parsed_count = %s,
              error_class = %s
            WHERE id = %s
            """,
            (status, listing_complete, listed_count, parsed_count, error_class, run_id),
        )
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
        self._conn.execute(
            """
            UPDATE catalog.research_job
            SET consecutive_complete_run_absence = consecutive_complete_run_absence + 1
            WHERE external_id = %s
            """,
            (job_id,),
        )

    def list_source_runs(self, source_id: str | None = None) -> list[dict[str, Any]]:
        if source_id:
            rows = self._conn.execute(
                """
                select id, source_id, started_at, scheduled_for, status
                from ingest.source_run
                where source_id = %s
                order by started_at desc nulls last
                """,
                (source_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                select id, source_id, started_at, scheduled_for, status
                from ingest.source_run
                order by started_at desc nulls last
                """
            ).fetchall()
        return [
            {
                "id": str(row[0]),
                "source_id": row[1],
                "started_at": row[2].isoformat() if row[2] else None,
                "scheduled_for": row[3].isoformat() if row[3] else None,
                "status": row[4],
            }
            for row in rows
        ]

    def delete_run(self, run_id: str) -> None:
        self._conn.execute("delete from ingest.listing_observation where run_id = %s", (run_id,))
        self._conn.execute(
            "update catalog.research_job_version set source_run_id = null where source_run_id = %s",
            (run_id,),
        )
        self._conn.execute("update ingest.raw_document set run_id = null where run_id = %s", (run_id,))
        self._conn.execute("delete from ingest.source_run where id = %s", (run_id,))
        self.runs.pop(run_id, None)

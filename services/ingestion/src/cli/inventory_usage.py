"""Read-only inventory of Supabase table counts and Storage bytes. Prints no secrets."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from cli.apply_schema import _load_env  # noqa: E402
from storage.budgets import (  # noqa: E402
    DB_HIGH_BYTES,
    DB_WARN_BYTES,
    STORAGE_HIGH_BYTES,
    STORAGE_WARN_BYTES,
    watermark,
)
from storage.postgres import load_database_env, rest_configured  # noqa: E402

TABLES = (
    "ingest_source",
    "ingest_source_run",
    "ingest_raw_document",
    "ingest_listing_observation",
    "catalog_research_job",
    "catalog_research_job_version",
    "catalog_programme",
    "catalog_programme_version",
    "catalog_offering",
    "catalog_offering_version",
    "catalog_admission_window",
    "catalog_tuition",
    "catalog_requirement",
)


def _storage_bytes(items: list[dict]) -> int:
    total = 0
    for item in items:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        total += int(meta.get("size") or item.get("size") or 0)
    return total


def main() -> None:
    _load_env(ROOT / ".env")
    load_database_env()
    if not rest_configured():
        raise SystemExit("SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY required")
    from storage.evidence import EvidenceStore
    from storage.rest import RestStore

    store = RestStore()
    counts: dict[str, int] = {}
    for table in TABLES:
        try:
            counts[table] = store.rest_count(table)
        except Exception as exc:  # noqa: BLE001
            counts[table] = -1
            print(json.dumps({"table": table, "error": type(exc).__name__}), flush=True)

    evidence = EvidenceStore()
    objects: list[dict] = []
    storage_error = None
    try:
        if evidence.bucket_exists():
            objects = evidence.list_objects()
        else:
            storage_error = "bucket-missing"
    except Exception as exc:  # noqa: BLE001
        storage_error = type(exc).__name__

    storage_used = _storage_bytes(objects)
    report = {
        "ok": True,
        "transport": "https-data-api",
        "tables": counts,
        "identitiesKept": {
            "researchJobs": counts.get("catalog_research_job"),
            "programmes": counts.get("catalog_programme"),
        },
        "storage": {
            "bucket": evidence.bucket,
            "objects": len(objects),
            "bytes": storage_used,
            "watermark": watermark(storage_used, STORAGE_WARN_BYTES, STORAGE_HIGH_BYTES),
            "warnBytes": STORAGE_WARN_BYTES,
            "highBytes": STORAGE_HIGH_BYTES,
            "error": storage_error,
        },
        "databaseWatermarks": {
            "warnBytes": DB_WARN_BYTES,
            "highBytes": DB_HIGH_BYTES,
            "note": "row counts only over REST; relation size needs a Postgres probe",
        },
        "policy": "identities stay; do not drop open vacancies or HEI coverage to save space",
    }

    dsn = os.environ.get("SUPABASE_DB_URL", "").strip()
    if dsn:
        try:
            import psycopg

            with psycopg.connect(dsn) as conn:
                rows = conn.execute(
                    """
                    select n.nspname || '.' || c.relname as name,
                           pg_total_relation_size(c.oid) as bytes
                    from pg_class c
                    join pg_namespace n on n.oid = c.relnamespace
                    where n.nspname in ('ingest','catalog','review','publish','ops')
                      and c.relkind in ('r','i','m')
                    order by pg_total_relation_size(c.oid) desc
                    """
                ).fetchall()
            used = sum(int(row[1]) for row in rows)
            report["database"] = {
                "bytes": used,
                "watermark": watermark(used, DB_WARN_BYTES, DB_HIGH_BYTES),
                "relations": [{"name": row[0], "bytes": int(row[1])} for row in rows[:30]],
            }
        except Exception as exc:  # noqa: BLE001
            report["database"] = {"error": type(exc).__name__, "probed": True}

    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

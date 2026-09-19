"""Connectivity and grant check. Prints no secrets."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))
from cli.apply_schema import _dsn, _load_env, _redact  # noqa: E402
from storage.postgres import postgres_configured  # noqa: E402


def _rest_status(url: str, key: str) -> dict:
    req = urllib.request.Request(
        url.rstrip("/") + "/rest/v1/",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        method="GET",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            return {"status": resp.status, "ok": True}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        return {"status": exc.code, "ok": False, "snippet": body.replace(key, "[redacted]")}
    except Exception as exc:  # noqa: BLE001
        return {"status": 0, "ok": False, "error": type(exc).__name__}


def _table_status(url: str, key: str, table: str) -> dict:
    req = urllib.request.Request(
        url.rstrip("/") + f"/rest/v1/{table}?select=id&limit=1",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
        method="GET",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            return {"status": resp.status, "ok": True}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        return {"status": exc.code, "ok": False, "snippet": body.replace(key, "[redacted]")}
    except Exception as exc:  # noqa: BLE001
        return {"status": 0, "ok": False, "error": type(exc).__name__}


def main() -> int:
    _load_env(ROOT / ".env")
    url = os.environ.get("SUPABASE_URL", "")
    publishable = os.environ.get("SUPABASE_PUBLISHABLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
    service = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    report: dict = {
        "projectRef": os.environ.get("SUPABASE_PROJECT_REF"),
        "transport": "https-data-api",
        "restPublishableRoot": _rest_status(url, publishable) if publishable else {"ok": False, "error": "missing-publishable"},
        "restServiceIngest": _table_status(url, service, "ingest_source") if service else {"ok": False, "error": "missing-service"},
        "restAnonIngest": _table_status(url, publishable, "ingest_source") if publishable else {"ok": False, "error": "missing-publishable"},
    }
    if not postgres_configured():
        report["postgres"] = {"ok": False, "skipped": "https-data-api-only"}
    else:
      try:
        import psycopg

        conn = psycopg.connect(_dsn(), connect_timeout=20)
        schemas = [
            row[0]
            for row in conn.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname IN ('ingest','catalog','review','publish','ops') ORDER BY 1"
            )
        ]
        tables = [
            f"{row[0]}.{row[1]}"
            for row in conn.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema IN ('ingest','catalog','review','publish','ops')
                ORDER BY 1, 2
                """
            )
        ]
        anon_has = conn.execute(
            """
            SELECT COUNT(*) FROM information_schema.role_table_grants
            WHERE grantee = 'anon'
              AND table_schema IN ('ingest','catalog','review','publish','ops')
            """
        ).fetchone()[0]
        report["postgres"] = {
            "ok": True,
            "schemas": schemas,
            "tables": tables,
            "anonTableGrants": int(anon_has),
        }
        conn.close()
      except Exception as exc:  # noqa: BLE001
        report["postgres"] = {"ok": False, "error": _redact(str(exc))}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    https_ok = bool(report.get("restServiceIngest", {}).get("ok"))
    anon_blocked = not bool(report.get("restAnonIngest", {}).get("ok"))
    if https_ok and anon_blocked:
        return 0
    if report.get("postgres", {}).get("ok") and anon_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

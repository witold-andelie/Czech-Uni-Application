"""Apply supabase/migrations against the linked project. Secrets stay in .env."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "supabase" / "migrations"


def _load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _dsn() -> str:
    explicit = os.environ.get("SUPABASE_DB_URL", "").strip()
    if explicit:
        return explicit
    password = os.environ.get("SUPABASE_DB_PASSWORD", "")
    ref = os.environ.get("SUPABASE_PROJECT_REF", "")
    if not password or not ref:
        raise SystemExit("Missing SUPABASE_DB_URL or SUPABASE_DB_PASSWORD + SUPABASE_PROJECT_REF")
    return (
        f"postgresql://postgres:{quote(password, safe='')}@"
        f"db.{ref}.supabase.co:5432/postgres?sslmode=require"
    )


def split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or stripped == "":
            continue
        buf.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buf).strip().rstrip(";")
            if statement:
                statements.append(statement)
            buf = []
    trailing = "\n".join(buf).strip().rstrip(";")
    if trailing:
        statements.append(trailing)
    return statements


def _redact(message: str) -> str:
    dsn = os.environ.get("SUPABASE_DB_URL", "")
    password = os.environ.get("SUPABASE_DB_PASSWORD", "")
    text = message
    for secret in (dsn, password):
        if secret:
            text = text.replace(secret, "[redacted]")
            parsed = urlparse(secret) if "://" in secret else None
            if parsed and parsed.password:
                text = text.replace(parsed.password, "[redacted]")
    return text


def main() -> int:
    _load_env(ROOT / ".env")
    import psycopg

    files = sorted(p for p in MIGRATIONS.glob("*.sql") if p.is_file())
    if not files:
        print("No SQL migrations found")
        return 2
    try:
        conn = psycopg.connect(_dsn(), connect_timeout=20, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        print(_redact(f"connection failed: {exc}"))
        return 1
    applied: list[str] = []
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
              id text PRIMARY KEY,
              applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        done = {row[0] for row in conn.execute("SELECT id FROM public.schema_migrations")}
        for path in files:
            ident = path.name
            if ident in done:
                print(f"skip {ident}")
                continue
            for statement in split_statements(path.read_text(encoding="utf-8")):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO public.schema_migrations (id) VALUES (%s)",
                (ident,),
            )
            applied.append(ident)
            print(f"applied {ident}")
    except Exception as exc:  # noqa: BLE001
        print(_redact(f"migration failed: {exc}"))
        conn.close()
        return 1
    conn.close()

    verify = psycopg.connect(_dsn(), connect_timeout=20)
    try:
        schemas = [
            row[0]
            for row in verify.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname IN ('ingest','catalog','review','publish','ops') ORDER BY 1"
            )
        ]
        recorded = [
            row[0]
            for row in verify.execute("SELECT id FROM public.schema_migrations ORDER BY 1")
        ]
    finally:
        verify.close()
    print("schemas", ",".join(schemas) if schemas else "(none)")
    print("migrations", ",".join(recorded) if recorded else "(none)")
    print("applied_count", len(applied))
    if set(schemas) != {"catalog", "ingest", "ops", "publish", "review"}:
        print("verification failed: expected operational schemas missing after reconnect")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

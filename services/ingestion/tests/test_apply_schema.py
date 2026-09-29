from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cli.apply_schema import ensure_migration_table, split_statements  # noqa: E402


def test_split_statements_keeps_dollar_quoted_semicolons_together() -> None:
    sql = "\n".join(
        [
            "-- header",
            "CREATE OR REPLACE FUNCTION public.f(a int)",
            "RETURNS int LANGUAGE sql AS $$",
            "  WITH x AS (SELECT 1 WHERE 1 = 2; SELECT 2)",
            "  SELECT count(*) FROM x;",
            "$$;",
            "GRANT EXECUTE ON FUNCTION public.f(int) TO service_role;",
            "",
        ]
    )
    statements = split_statements(sql)
    assert len(statements) == 2
    assert statements[0].startswith("CREATE OR REPLACE FUNCTION public.f")
    assert statements[0].endswith("INTEGER; SELECT count(*) FROM x;$$") or statements[0].endswith("$$")
    assert "WITH x AS (SELECT 1 WHERE 1 = 2; SELECT 2)" in statements[0]
    assert statements[1].startswith("GRANT EXECUTE")


def test_split_statements_strips_comments_outside_bodies() -> None:
    statements = split_statements("-- comment\nSELECT 1;\n-- trailing")
    assert statements == ["SELECT 1"]


def test_migration_ledger_is_hardened_in_same_transaction() -> None:
    calls: list[str] = []

    class FakeTransaction:
        def __enter__(self) -> None:
            calls.append("begin")

        def __exit__(self, *args: object) -> None:
            calls.append("commit")

    class FakeConnection:
        def transaction(self) -> FakeTransaction:
            return FakeTransaction()

        def execute(self, statement: str) -> None:
            calls.append(statement.strip())

    ensure_migration_table(FakeConnection())
    assert calls[0] == "begin"
    assert calls[-1] == "commit"
    assert "CREATE TABLE IF NOT EXISTS public.schema_migrations" in calls[1]
    assert calls[2] == "ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY"
    assert calls[3] == (
        "REVOKE ALL ON TABLE public.schema_migrations FROM PUBLIC, anon, authenticated"
    )

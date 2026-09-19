from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cli.apply_schema import split_statements  # noqa: E402


def test_split_statements_skips_comments_and_keeps_create_schema() -> None:
    sql = """
-- comment
CREATE SCHEMA IF NOT EXISTS ingest;
CREATE TABLE ingest.source (id text PRIMARY KEY);
"""
    parts = split_statements(sql)
    assert parts[0].startswith("CREATE SCHEMA")
    assert "ingest.source" in parts[1]
    assert all(not item.startswith("--") for item in parts)

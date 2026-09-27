from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.facts import stored_facts  # noqa: E402


def test_stored_facts_drops_html_and_oversized_fields_without_truncating() -> None:
    payload, rejected = stored_facts(
        {
            "title": "Researcher",
            "html": "<html>whole page</html>",
            "body": "x" * 20,
            "request_id": "abc",
            "notes": "y" * 9000,
            "paid_status": "confirmed",
        }
    )
    assert payload["title"] == "Researcher"
    assert payload["paid_status"] == "confirmed"
    assert "html" not in payload
    assert "notes" not in payload
    assert "html" in rejected
    assert "notes" in rejected
    assert "request_id" in rejected

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from storage.postgres import store_from_env  # noqa: E402
from storage.rest import RestStore  # noqa: E402


def test_github_actions_uses_https_rest(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role")
    store = store_from_env()
    assert isinstance(store, RestStore)
    assert store.url == "https://example.supabase.co"

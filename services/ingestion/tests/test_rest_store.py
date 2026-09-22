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


def _store(monkeypatch) -> RestStore:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role")
    return RestStore()


def test_claim_run_posts_rpc_with_owner(monkeypatch) -> None:
    store = _store(monkeypatch)
    seen: dict[str, object] = {}

    def fake(method, path, payload=None, extra=None):
        seen.update(method=method, path=path, payload=payload)
        return {"token": "tok-1", "lease_until": "2026-09-22T12:00:00+00:00"}

    store._request = fake  # type: ignore[assignment]
    assert store.claim_run("run-1", owner="host-A") == "tok-1"
    assert seen["method"] == "POST"
    assert seen["path"] == "rpc/rpc_claim_run"
    assert seen["payload"] == {"p_run": "run-1", "p_owner": "host-A", "p_lease_seconds": 900}


def test_claim_run_returns_none_when_lease_held(monkeypatch) -> None:
    store = _store(monkeypatch)
    store._request = lambda *a, **k: {}  # type: ignore[assignment]
    assert store.claim_run("run-1", owner="host-B") is None


def test_release_requires_matching_fencing_token(monkeypatch) -> None:
    store = _store(monkeypatch)
    calls: list[dict] = []

    def fake(method, path, payload=None, extra=None):
        calls.append(payload or {})
        return {}

    store._request = fake  # type: ignore[assignment]
    assert store.release_run("run-1", "stale-token") is False
    assert calls[0]["p_token"] == "stale-token"

    store._request = lambda *a, **k: {"ok": True}  # type: ignore[assignment]
    assert store.release_run("run-1", "owner-token") is True


def test_heartbeat_wrong_token_is_rejected(monkeypatch) -> None:
    store = _store(monkeypatch)
    store._request = lambda *a, **k: {}  # type: ignore[assignment]
    assert store.heartbeat_run("run-1", "stale-token") is False
    store._request = lambda *a, **k: {"ok": True}  # type: ignore[assignment]
    assert store.heartbeat_run("run-1", "owner-token") is True


def test_start_run_claims_lease_and_finish_releases(monkeypatch) -> None:
    store = _store(monkeypatch)
    release_calls: list[dict] = []
    claim_calls: list[dict] = []

    def fake(method, path, payload=None, extra=None):
        if path.startswith("ingest_source?"):
            return []
        if path.startswith("rpc/rpc_claim_run"):
            claim_calls.append(payload or {})
            return {"token": "tok-claim", "lease_until": "2026-09-22T12:00:00+00:00"}
        if path.startswith("rpc/rpc_release_run"):
            release_calls.append(payload or {})
            return {"ok": True}
        return None

    store._request = fake  # type: ignore[assignment]
    run = store.start_run({"id": "src-lease", "employerId": "msmt-vs_10000"})
    assert run["lease_token"] == "tok-claim"
    assert claim_calls and claim_calls[0]["p_owner"]
    store.finish_run(run["id"], status="succeeded", listing_complete=True, listed_count=1, parsed_count=1)
    assert release_calls == [{"p_run": run["id"], "p_token": "tok-claim"}]

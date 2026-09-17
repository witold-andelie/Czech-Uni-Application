from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "checkout_inventory.py"
SPEC = importlib.util.spec_from_file_location("checkout_inventory", MODULE_PATH)
assert SPEC and SPEC.loader
checkout_inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checkout_inventory)


def test_provenance_records_github_commit_and_workflow(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")
    monkeypatch.setenv("GITHUB_RUN_ID", "456")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.example")

    payload = checkout_inventory.provenance()

    assert payload["buildEnvironment"] == "github_actions"
    assert payload["commitSha"] == "abc123"
    assert payload["commitUrl"] == "https://github.example/owner/repository/commit/abc123"
    assert payload["workflowRunUrl"] == "https://github.example/owner/repository/actions/runs/456"
    assert payload["hostedCICD"] == "workflow_run"


def test_local_provenance_does_not_claim_hosted_verification(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    payload = checkout_inventory.provenance()

    assert payload["buildEnvironment"] == "local"
    assert payload["commitSha"] is None
    assert payload["workflowRunUrl"] is None
    assert payload["hostedCICD"] == "not_verified"

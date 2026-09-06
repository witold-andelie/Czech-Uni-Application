"""Offline ingestion worker stub.

This process must not run inside a user request. It does not start a crawl
until a deployed scheduler supplies an anchor and a source registry. Network
failures must not be stored as closed vacancies.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "data" / "sources" / "registry.json"
POLICY = ROOT / "config" / "refresh-policy.json"


def load_registry() -> list[dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def load_policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def network_failure_means_closed(status_code: int | None, timeout: bool) -> bool:
    if timeout:
        return False
    if status_code in {403, 404, 429, 500, 502, 503}:
        return False
    return False


def main() -> None:
    policy = load_policy()
    registry = load_registry()
    print("ingestion worker is a stub; no crawl is started")
    print(f"policy_status={policy.get('status')} sources={len(registry)}")
    print("interval_hours=", policy.get("universityRefresh", {}).get("intervalHours"))
    print("network_failure_means_closed", network_failure_means_closed(429, False))


if __name__ == "__main__":
    main()

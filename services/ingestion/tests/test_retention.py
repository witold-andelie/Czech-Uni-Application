from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from storage.memory import MemoryStore  # noqa: E402
from storage.retention import prune_ingest_history  # noqa: E402


def _finished_run(store: MemoryStore, source_id: str, stamp: str) -> str:
    run = store.start_run({"id": source_id}, scheduled_for=stamp)
    run["started_at"] = stamp
    store.save_observation(run["id"], "1", "https://example.test/1", "Role")
    store.finish_run(run["id"], status="succeeded", listing_complete=True, listed_count=1, parsed_count=1)
    return run["id"]


def test_prune_keeps_identities_and_only_recent_runs() -> None:
    store = MemoryStore()
    source = {"id": "czu-central-jobs", "employerId": "msmt-vs_41000"}
    kept_ids = []
    for index in range(10):
        stamp = f"2026-09-{index + 1:02d}T00:00:00Z"
        run_id = _finished_run(store, source["id"], stamp)
        kept_ids.append(run_id)
        store.upsert_job(
            source_id=source["id"],
            employer_id="msmt-vs_41000",
            remote_id="1604",
            official_detail_url="https://jobs.czu.test/job/t1/",
            facts={"title": "TF T1", "paid_status": "confirmed", "catalogue_scope_status": "included"},
            run_id=run_id,
        )
    report = prune_ingest_history(store, keep=3)
    assert report["ok"] is True
    assert report["deletedRuns"] == 7
    assert len(store.runs) == 3
    assert len(store.observations) == 3
    assert len(store.jobs) == 1
    assert len(store.versions) == 1
    remaining = {row["started_at"] for row in store.runs.values()}
    assert remaining == {"2026-09-08T00:00:00Z", "2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"}


def test_prune_does_not_drop_a_running_run() -> None:
    store = MemoryStore()
    old = _finished_run(store, "cuni-central-open-positions", "2026-01-01T00:00:00Z")
    recent = _finished_run(store, "cuni-central-open-positions", "2026-09-18T00:00:00Z")
    live = store.start_run({"id": "cuni-central-open-positions"}, scheduled_for="2026-09-19T00:00:00Z")
    live["started_at"] = "2026-09-19T00:00:00Z"
    report = prune_ingest_history(store, keep=1)
    assert old not in store.runs
    assert recent in store.runs
    assert live["id"] in store.runs
    assert report["deletedRuns"] == 1

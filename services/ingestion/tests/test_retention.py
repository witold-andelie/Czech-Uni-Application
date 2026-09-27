from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from storage.memory import MemoryStore  # noqa: E402
from storage.retention import apply_evidence_gc, preview_evidence_gc, prune_ingest_history  # noqa: E402


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


def test_preview_gc_skips_referenced_and_recent_objects() -> None:
    store = MemoryStore()
    store.documents.append(
        {
            "storage_path": "source-evidence/aaaa.gz",
            "raw_sha256": "aaaa",
            "sha256": "bbbb",
        }
    )

    class Bucket:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def list_objects(self):
            return [
                {"name": "aaaa.gz", "metadata": {"size": 10}, "updated_at": "2020-01-01T00:00:00Z"},
                {"name": "orphan.gz", "metadata": {"size": 99}, "updated_at": "2020-01-01T00:00:00Z"},
                {"name": "fresh.gz", "metadata": {"size": 5}, "updated_at": "2026-09-20T00:00:00Z"},
            ]

        def delete(self, key: str) -> None:
            self.deleted.append(key)

    bucket = Bucket()
    preview = preview_evidence_gc(store, bucket, grace_days=30, now=__import__("datetime").datetime(2026, 9, 27, tzinfo=__import__("datetime").timezone.utc))
    keys = {item["key"] for item in preview["unreferenced"]}
    assert "orphan.gz" in keys
    assert "aaaa.gz" not in keys
    assert "fresh.gz" not in keys
    applied = apply_evidence_gc(bucket, preview)
    assert bucket.deleted == ["orphan.gz"]
    assert applied["deleted"] == 1


def test_rest_list_source_runs_pages_past_one_thousand() -> None:
    from storage.rest import RestStore

    store = RestStore(url="https://example.supabase.co", key="service-token")

    def fake(method: str, path: str, payload=None, extra=None):
        assert method == "GET"
        offset = 0
        if "offset=" in path:
            offset = int(path.split("offset=")[1].split("&")[0])
        if offset == 0:
            return [{"id": str(i), "source_id": "s", "status": "succeeded"} for i in range(1000)]
        if offset == 1000:
            return [{"id": "1000", "source_id": "s", "status": "succeeded"}]
        return []

    store._request = fake  # type: ignore[assignment]
    rows = store.list_source_runs()
    assert len(rows) == 1001

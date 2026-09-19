from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from storage.persist import persist_job_harvest  # noqa: E402
from storage.postgres import persist_enabled  # noqa: E402


def test_pytest_does_not_write_to_supabase() -> None:
    assert persist_enabled() is False
    result = persist_job_harvest(
        expected_source_ids=["czu-central-jobs"],
        complete_source_ids=["czu-central-jobs"],
        deferred_source_ids=[],
        attempts=[],
        jobs=[
            {
                "id": "job-41000-1604",
                "discoverySourceId": "czu-central-jobs",
                "sourceUrl": "https://jobs.czu.cz/job/tf_asistent-znalostniho-transferu-t1/",
                "employerId": "msmt-vs_41000",
            }
        ],
    )
    assert result["skipped"] == "supabase-write-disabled"
    assert result["jobs"] == 0


def test_failed_source_does_not_upsert_jobs(monkeypatch) -> None:
    class FakeStore:
        def __init__(self) -> None:
            self.jobs: list[dict] = []
            self.finished: list[dict] = []

        def start_run(self, source):
            return {"id": "run-1", "source_id": source["id"]}

        def upsert_job(self, **kwargs):
            self.jobs.append(kwargs)

        def finish_run(self, run_id, **kwargs):
            self.finished.append({"run_id": run_id, **kwargs})

        def close(self) -> None:
            return None

    fake = FakeStore()
    monkeypatch.setattr("storage.persist.persist_enabled", lambda: True)
    monkeypatch.setattr("storage.persist.store_from_env", lambda: fake)
    persist_job_harvest(
        expected_source_ids=["czu-central-jobs"],
        complete_source_ids=[],
        deferred_source_ids=[],
        attempts=[{"sourceId": "czu-central-jobs", "ok": False, "reason": "timeout"}],
        jobs=[
            {
                "id": "job-41000-1604",
                "discoverySourceId": "czu-central-jobs",
                "sourceUrl": "https://jobs.czu.cz/job/tf_asistent-znalostniho-transferu-t1/",
                "employerId": "msmt-vs_41000",
            }
        ],
    )
    assert fake.jobs == []
    assert fake.finished[0]["status"] == "failed"
    assert fake.finished[0]["listing_complete"] is False


def test_complete_source_upserts_official_detail_urls(monkeypatch) -> None:
    class FakeStore:
        def __init__(self) -> None:
            self.jobs: list[dict] = []

        def start_run(self, source):
            return {"id": "run-1"}

        def upsert_job(self, **kwargs):
            self.jobs.append(kwargs)

        def finish_run(self, run_id, **kwargs):
            self.status = kwargs["status"]

        def close(self) -> None:
            return None

    fake = FakeStore()
    monkeypatch.setattr("storage.persist.persist_enabled", lambda: True)
    monkeypatch.setattr("storage.persist.store_from_env", lambda: fake)
    persist_job_harvest(
        expected_source_ids=["czu-central-jobs"],
        complete_source_ids=["czu-central-jobs"],
        deferred_source_ids=[],
        attempts=[],
        jobs=[
            {
                "id": "job-41000-1604",
                "discoverySourceId": "czu-central-jobs",
                "sourceUrl": "https://jobs.czu.cz/job/tf_asistent-znalostniho-transferu-t1/",
                "employerId": "msmt-vs_41000",
                "title": "TF T1",
                "paidStatus": "confirmed",
            }
        ],
    )
    assert len(fake.jobs) == 1
    assert fake.jobs[0]["official_detail_url"].endswith("/tf_asistent-znalostniho-transferu-t1/")
    assert fake.status == "succeeded"

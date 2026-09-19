from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from engine.adapter_harvest import harvest_adapter_source  # noqa: E402
from storage.memory import MemoryStore  # noqa: E402
import worker  # noqa: E402
from test_adapter_pipeline import (  # noqa: E402
    ADMIN_URL,
    TECHNICAL_TITLE,
    TECHNICAL_URL,
    _fetch,
    _source,
)


def test_harvest_jobs_keeps_every_official_czu_vacancy(tmp_path: Path) -> None:
    target = tmp_path / "jobs.json"
    target.write_text("{}", encoding="utf-8")
    result = worker.harvest_jobs([], fetch_page=_fetch, jobs_path=target, registry=[_source()])
    payload = json.loads(target.read_text(encoding="utf-8"))
    ids = {job["id"] for job in payload["jobs"]}
    assert "job-41000-1604" in ids
    assert "job-41000-1605" in ids
    by_id = {job["id"]: job for job in payload["jobs"]}
    assert by_id["job-41000-1604"]["officialDetailUrl"] == TECHNICAL_URL
    assert by_id["job-41000-1604"]["catalogueScopeStatus"] == "included"
    assert by_id["job-41000-1605"]["officialDetailUrl"] == ADMIN_URL
    assert by_id["job-41000-1605"]["catalogueScopeStatus"] == "unspecified"
    assert result["discovery"]["completeSourceIds"] == ["czu-central-jobs"]
    assert result["supabase"]["jobs"] == 2


def test_incomplete_adapter_harvest_does_not_close_or_replace_jobs(tmp_path: Path) -> None:
    target = tmp_path / "jobs.json"
    target.write_text("{}", encoding="utf-8")
    worker.harvest_jobs([], fetch_page=_fetch, jobs_path=target, registry=[_source()])
    before = json.loads(target.read_text(encoding="utf-8"))

    def fetch_partial(url: str):
        if "get_listings" in url:
            return 503, ""
        return _fetch(url)

    result = worker.harvest_jobs([], fetch_page=fetch_partial, jobs_path=target, registry=[_source()])
    after = json.loads(target.read_text(encoding="utf-8"))
    assert result["complete"] is not True if "complete" in result else result["discovery"]["completeSourceIds"] == []
    assert {job["id"] for job in after["jobs"]} == {job["id"] for job in before["jobs"]}
    assert all(job.get("lifecycleStatus") != "closed" for job in after["jobs"])
    assert all(job.get("lifecycleStatus") != "unavailable" for job in after["jobs"] if job.get("id") in {item["id"] for item in before["jobs"]})
    assert result["supabase"]["jobs"] == 0


def test_second_unchanged_adapter_run_does_not_add_versions() -> None:
    store = MemoryStore()
    first = harvest_adapter_source(_source(), fetch_page=_fetch, previous={}, store=store)
    second = harvest_adapter_source(_source(), fetch_page=_fetch, previous=first["snapshot"], store=store)
    assert first["run"]["status"] == second["run"]["status"] == "succeeded"
    assert len(store.jobs) == 2
    assert len(store.versions) == 2
    assert len(store.runs) == 2


def test_complete_listing_absence_increments_counter_without_partial_run() -> None:
    store = MemoryStore()
    harvest_adapter_source(_source(), fetch_page=_fetch, previous={}, store=store)

    def only_technical(url: str):
        if url == _source()["url"]:
            return _fetch(url)
        if url.startswith(_source()["publicListUrl"]):
            return 200, json.dumps(
                {
                    "found_jobs": True,
                    "max_num_pages": 1,
                    "html": (
                        f'<li class="post-1604 job_listing status-publish">'
                        f'<a href="{TECHNICAL_URL}"><h3>{TECHNICAL_TITLE}</h3></a></li>'
                    ),
                },
                ensure_ascii=False,
            )
        if url.startswith(_source()["apiUrl"]):
            payload = json.loads(_fetch(url)[1])
            return 200, json.dumps([row for row in payload if row["id"] == 1604], ensure_ascii=False)
        return _fetch(url)

    harvest_adapter_source(_source(), fetch_page=only_technical, previous={}, store=store)
    admin = store.jobs["msmt-vs_41000:1605"]
    assert admin["consecutive_absence"] == 1
    assert store.jobs["msmt-vs_41000:1604"]["consecutive_absence"] == 0

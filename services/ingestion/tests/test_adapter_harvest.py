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


def test_harvest_jobs_keeps_every_official_czu_vacancy(tmp_path: Path, monkeypatch) -> None:
    # Fixture notices were written in September 2026; judge them on that day,
    # not on the real clock (past-deadline notices do not become identities).
    import engine.adapter_harvest as adapter_harvest

    monkeypatch.setattr(adapter_harvest, "_prague_today", lambda: __import__("datetime").date(2026, 9, 15))
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


def test_adapter_job_id_matches_the_discovery_id_for_the_same_code() -> None:
    """One vacancy, one identity: raw CUNI codes must fold like discovery ids."""
    from engine.adapter_harvest import snapshot_job_id
    from harvest_nine_hei_jobs import _stable_discovered_id

    for code in ("202610-L2-PřF-1300-104", "202610-VP1-FaF HK-KSKF-127", "202611-AP2-FF-ÚPOL-106", "1604"):
        discovered = _stable_discovered_id(
            {"employerId": "msmt-vs_11000", "code": code, "title": "x", "sourceUrl": "https://cuni.cz/x"}
        )
        assert snapshot_job_id("msmt-vs_11000", code) == discovered
    assert snapshot_job_id("msmt-vs_11000", "202610-L2-PřF-1300-104") == "job-11000-202610-l2-p-f-1300-104"


def test_a_listing_row_does_not_replace_a_reviewed_record() -> None:
    from engine.adapter_harvest import _keep_prior_review

    prior = {
        "id": "job-43000-492828",
        "sourceUrl": "https://mendelu.recruitis.io/492828",
        "publicationStatus": "approved",
        "translationStatus": "verified",
        "salary": {"amount": 40000, "currency": "CZK"},
        "sourceHash": "sha256:" + "a" * 64,
    }
    incoming = {"id": "job-43000-492828", "sourceUrl": prior["sourceUrl"], "publicationStatus": "review_pending"}
    assert _keep_prior_review(prior, incoming) == prior

    unreviewed = {**prior, "publicationStatus": "review_pending", "translationStatus": "unreviewed"}
    assert _keep_prior_review(unreviewed, incoming)["publicationStatus"] == "review_pending"


def test_a_listing_notice_keeps_its_stated_deadline() -> None:
    """2026-10-01: all 33 queued TUL notices had stated deadlines that had passed."""
    from datetime import date

    from adapters.base import Candidate
    from engine.adapter_harvest import candidate_window, merge_adapter_snapshot

    def candidate(remote: str, closes: str) -> Candidate:
        return Candidate(
            remote_id=remote,
            official_detail_url=f"https://doc.tul.cz/{remote}",
            application_url=f"https://doc.tul.cz/{remote}",
            title="Pracovník výzkumu",
            body_html="",
            facts={"closesAt": closes},
        )

    today = date(2026, 10, 1)
    past = candidate_window(candidate("15800", "2026-09-20"), "job-24000-15800", today)
    future = candidate_window(candidate("15900", "2026-10-31"), "job-24000-15900", today)
    assert past["closesAt"] == "2026-09-20" and past["status"] == "closed"
    assert future["status"] == "unknown"

    unreviewed_prior = {"id": "job-24000-15700", "sourceUrl": "https://doc.tul.cz/15700",
                        "discoverySourceId": "tul", "publicationStatus": "review_pending",
                        "translationStatus": "unreviewed", "lifecycleStatus": "unknown"}
    stale = candidate_window(candidate("15700", "2026-09-01"), "job-24000-15700", today)
    incoming = [
        {"id": "job-24000-15800", "sourceUrl": "https://doc.tul.cz/15800", "discoverySourceId": "tul"},
        {"id": "job-24000-15900", "sourceUrl": "https://doc.tul.cz/15900", "discoverySourceId": "tul",
         "lifecycleStatus": "unknown"},
        {"id": "job-24000-15700", "sourceUrl": "https://doc.tul.cz/15700", "discoverySourceId": "tul",
         "lifecycleStatus": "unknown"},
    ]
    merged = merge_adapter_snapshot(
        {"jobs": [unreviewed_prior], "windows": []},
        source_id="tul", jobs=incoming, complete=True, discovery={}, now_text="2026-10-01T00:00:00Z",
        windows=[past, future, stale],
    )
    by_id = {job["id"]: job for job in merged["jobs"]}
    assert "job-24000-15800" not in by_id  # new and already past: not an identity
    assert by_id["job-24000-15900"]["lifecycleStatus"] == "unknown"
    assert by_id["job-24000-15700"]["lifecycleStatus"] == "expired"  # identity kept, archived
    assert by_id["job-24000-15700"]["visibility"] == "archived"
    assert {w["ownerId"] for w in merged["windows"]} == {"job-24000-15900", "job-24000-15700"}
    assert {"id": "job-24000-15800", "reason": "past-deadline"} in merged["skipped"]


def test_roboprox_source_keeps_listed_open_rows_past_their_euraxess_deadline() -> None:
    page = "https://www.ciirc.cvut.cz/roboprox/job-positions/"
    detail = "https://euraxess.ec.europa.eu/jobs/189893"
    listing = (
        "<table><tr><td>02-PhD-Babuska</td>"
        f'<td><a href="{detail}">PhD position in Interactive task specification for HRI</a></td>'
        "<td>Open</td></tr></table>"
        '<a class="next" href="/en/roboprox/job-positions/?mo=11&amp;yr=2026">next month</a>'
    )
    notice = (
        "<main><h1>PhD position in Interactive task specification for HRI</h1>"
        "<p>Researcher Profile First Stage Researcher (R1) Application Deadline 31 Dec 2025 - 23:59 "
        "Job Status Full-time Hours Per Week 40. We seek a motivated PhD candidate with a master's degree "
        "in computer science. Net compensation of about 1,700 EUR monthly (includes salary and student "
        "stipends).</p></main>"
    )

    def fetch(url: str):
        return (200, listing) if url == page else (200, notice) if url == detail else (404, "")

    source = {
        "id": "ctu-ciirc-roboprox-positions",
        "url": page,
        "official": True,
        "employerId": "msmt-vs_21000",
        "parser": "roboprox_positions",
        "followDetails": True,
    }
    result = harvest_adapter_source(source, fetch_page=fetch, previous={})
    jobs = {job["id"]: job for job in result["snapshot"]["jobs"]}
    job = jobs["job-21000-02-phd-babuska"]
    assert job["applicationUrl"] == page
    assert job["sourceUrl"] == detail
    assert job["doctoralEnrollment"] == "required"
    assert job["employmentFte"] == 1.0
    windows = [w for w in result["snapshot"].get("windows") or [] if w.get("jobId") == job["id"]]
    assert all(w.get("closesAt") is None for w in windows)

"""Each EURAXESS notice is read once (owner decision 2026-10-08)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src" / "cli"))

import euraxess_source  # noqa: E402
import harvest_nine_hei_jobs as h  # noqa: E402

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
SOURCE_ID = "euraxess-cz-jobs"


def url(code: int) -> str:
    return f"https://euraxess.ec.europa.eu/jobs/{code}"


def row(code: int, title: str = "Postdoctoral researcher in robotics") -> dict:
    return {"code": f"eu{code}", "title": title, "sourceUrl": url(code)}


def notice(title: str = "Postdoctoral researcher in robotics", website: str = "https://www.cuni.cz/jobs/postdoc-robotics") -> str:
    return (
        f"<html><body><main><h1>{title}</h1>"
        "<p>Organisation/Company Charles University Department Faculty of Mathematics and Physics "
        "Research Field Computer science</p>"
        f"<p>Website {website}</p>"
        "<p>A postdoctoral research position in robotics. PhD required. Application Deadline 31 Dec 2026.</p>"
        "</main></body></html>"
    )


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_a_notice_read_before_is_not_read_again_and_a_new_one_is_read_once():
    notices = {"eu1": {"url": url(1), "title": "Postdoctoral researcher in robotics", "fetchedAt": iso(NOW - timedelta(days=1)),
                       "employerId": "msmt-vs_11000", "officialPostUrl": None}}
    stored = {url(1): {"id": "job-11000-eu1", "employerId": "msmt-vs_11000", "lifecycleStatus": "unknown"}}
    fetched: list[str] = []

    def fetch(target):
        fetched.append(target)
        if target == url(2):
            return 200, notice()
        if target == "https://www.cuni.cz/jobs/postdoc-robotics":
            return 200, "<h1>Postdoctoral researcher in robotics</h1><p>Apply by 31 December.</p>"
        return 404, ""

    rows, attempts, complete = h.enrich_euraxess_rows([row(1), row(2)], fetch, SOURCE_ID, notices=notices, stored=stored, now=NOW)
    assert complete
    assert fetched == [url(2), "https://www.cuni.cz/jobs/postdoc-robotics"]
    assert rows[0]["_unchangedJobId"] == "job-11000-eu1" and "_factHtml" not in rows[0]
    assert rows[1]["employerId"] == "msmt-vs_11000" and rows[1]["_factHtml"]
    assert notices["eu2"]["fetchedAt"] == iso(NOW)
    assert notices["eu2"]["officialPostUrl"] == "https://www.cuni.cz/jobs/postdoc-robotics"
    assert [a["kind"] for a in attempts] == ["detail-read-before", "detail"]


def test_a_notice_is_read_again_when_retitled_due_or_relisted_and_a_failed_refresh_keeps_the_first_read():
    old = iso(NOW - timedelta(days=30))
    notices = {
        "eu1": {"url": url(1), "title": "An older title", "fetchedAt": iso(NOW), "employerId": "msmt-vs_11000"},
        "eu2": {"url": url(2), "title": "Postdoctoral researcher in robotics", "fetchedAt": old, "employerId": "msmt-vs_11000"},
        "eu3": {"url": url(3), "title": "Postdoctoral researcher in robotics", "fetchedAt": iso(NOW), "employerId": "msmt-vs_11000"},
    }
    stored = {url(n): {"id": f"job-11000-eu{n}", "employerId": "msmt-vs_11000", "lifecycleStatus": "unknown"} for n in (1, 2)}
    stored[url(3)] = {"id": "job-11000-eu3", "employerId": "msmt-vs_11000", "lifecycleStatus": "unavailable"}
    fetched: list[str] = []

    def fetch(target):
        fetched.append(target)
        return (429, "") if target == url(2) else (200, notice())

    rows, _attempts, complete = h.enrich_euraxess_rows([row(1), row(2), row(3)], fetch, SOURCE_ID,
                                                       notices=notices, stored=stored, now=NOW)
    # Retitled (1), due a refresh (2) and relisted after being archived (3) are read.
    assert [target for target in fetched if "euraxess" in target] == [url(1), url(2), url(3)]
    # The refresh of 2 was throttled: the first read still holds.
    assert complete and rows[1]["_unchangedJobId"] == "job-11000-eu2"
    # A new notice that cannot be read leaves the pass incomplete.
    _rows, _attempts, complete = h.enrich_euraxess_rows([row(9)], lambda target: (429, ""), SOURCE_ID,
                                                        notices={}, stored={}, now=NOW)
    assert not complete


def test_a_notice_read_before_and_not_catalogued_stays_out_without_a_read():
    notices = {"eu5": {"url": url(5), "title": "Head of marketing", "fetchedAt": iso(NOW), "employerId": None}}
    rows, _attempts, _complete = h.enrich_euraxess_rows([row(5, "Head of marketing")], lambda target: (_ for _ in ()).throw(AssertionError(target)),
                                                        SOURCE_ID, notices=notices, stored={}, now=NOW)
    assert rows == [{**row(5, "Head of marketing"), "_quarantineReason": "unchanged-notice-not-catalogued"}]


def test_the_refresh_of_a_week_of_first_reads_is_spread_over_another_week():
    first = NOW - timedelta(days=7)
    due = [code for code in range(100, 170) if euraxess_source.notice_due({"title": "t", "fetchedAt": iso(first)}, "t", f"eu{code}", NOW)]
    assert 5 <= len(due) <= 15


def test_the_listing_adapter_keeps_an_unread_notice_listed_without_a_request():
    from adapters.base import ListingReference
    from adapters.jobs.registered_listing import HarvestListingAdapter

    adapter = HarvestListingAdapter({"id": SOURCE_ID, "url": "https://euraxess.ec.europa.eu/jobs/search", "parser": "euraxess_search"})
    ref = ListingReference(remote_id="eu1", detail_url=url(1), title="Postdoc", listing_url=url(0),
                           extra={"listing": {"_unchangedJobId": "job-11000-eu1"}})
    assert adapter.fetch_detail(ref, {"fetch_page": lambda target: (_ for _ in ()).throw(AssertionError(target))}) == []
    assert adapter.unchanged_job_ids == {"job-11000-eu1"} and adapter._details_ok == 1


def test_a_full_pass_reads_only_the_new_notice_and_keeps_the_read_one(tmp_path, monkeypatch):
    from engine.adapter_harvest import harvest_adapter_source
    from storage.memory import MemoryStore

    search = "https://euraxess.ec.europa.eu/jobs/search?f%5B0%5D=job_country%3A747"
    listing = (
        "<p>Search results (2)</p>"
        '<article><a href="/jobs/1">Postdoctoral researcher in robotics</a></article>'
        '<article><a href="/jobs/2">Postdoctoral researcher in vision</a></article>'
    )
    euraxess_source.save_notices({"eu1": {"url": url(1), "title": "Postdoctoral researcher in robotics", "fetchedAt": iso(NOW),
                                          "employerId": "msmt-vs_11000", "officialPostUrl": None}})
    prior = {"id": "job-11000-eu1", "employerId": "msmt-vs_11000", "discoverySourceId": SOURCE_ID, "sourceUrl": url(1),
             "visibility": "public", "lifecycleStatus": "unknown", "title": {"en": "Postdoctoral researcher in robotics"}}
    (tmp_path / "no-candidates.json").write_text(json.dumps({"jobs": [prior]}), encoding="utf-8")
    fetched: list[str] = []

    def fetch(target):
        fetched.append(target)
        if target == search:
            return 200, listing
        if target == url(2):
            return 200, notice("Postdoctoral researcher in vision", "https://www.cuni.cz/jobs/postdoc-vision")
        return 200, "<h1>Postdoctoral researcher in vision</h1>"

    source = {"id": SOURCE_ID, "url": search, "official": True, "sourceType": "official_job_listing_supplemental",
              "parser": "euraxess_search", "followDetails": False, "maxListingPages": 60}
    result = harvest_adapter_source(source, fetch_page=fetch, previous={"jobs": [prior], "windows": []}, store=MemoryStore())
    assert url(1) not in fetched and url(2) in fetched
    jobs = {job["id"]: job for job in result["snapshot"]["jobs"]}
    assert jobs["job-11000-eu1"] == prior  # listed, not read again, kept as it was
    assert any(job.get("sourceUrl") == url(2) for job in jobs.values())
    listing_file = json.loads(euraxess_source.LISTING_PATH.read_text(encoding="utf-8"))
    assert listing_file["complete"] and set(listing_file["notices"]) == {url(1), url(2)}


def test_the_recheck_reads_the_day_listing_or_the_employer_page_not_the_notice(tmp_path):
    import worker
    from schedule import ScheduleManager

    euraxess_source.save_listing({url(1): "Postdoc"}, True, NOW - timedelta(hours=2))
    euraxess_source.save_notices({"eu3": {"url": url(3), "title": "PhD", "fetchedAt": iso(NOW), "officialPostUrl": "https://lab.cvut.cz/open-positions/"}})
    jobs = [
        {"id": "listed", "sourceUrl": url(1), "lifecycleStatus": "unknown", "visibility": "public", "originalText": "Postdoc"},
        {"id": "gone", "sourceUrl": url(2), "lifecycleStatus": "unknown", "visibility": "public", "originalText": "Postdoc 2"},
        {"id": "own-page", "sourceUrl": url(3), "lifecycleStatus": "unknown", "visibility": "public", "originalText": "PhD"},
    ]
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(json.dumps({"jobs": jobs, "windows": []}), encoding="utf-8")
    fetched: list[str] = []

    def fetch(target):
        fetched.append(target)
        return 200, "<h1>PhD</h1><p>Call is open.</p>"

    worker.recheck_open_jobs(fetch_page=fetch, now=NOW, jobs_path=jobs_path, schedule_manager=ScheduleManager(tmp_path / "s.json"),
                             use_lock=False, safety_dir=tmp_path / "safety")
    stored = {job["id"]: job for job in json.loads(jobs_path.read_text(encoding="utf-8"))["jobs"]}
    assert fetched == ["https://lab.cvut.cz/open-positions/"]
    assert stored["listed"]["lastAttemptReason"] == "listed_on_euraxess"
    assert stored["gone"]["lastAttemptReason"] == "not_on_euraxess_listing" and stored["gone"]["visibility"] == "public"
    assert stored["own-page"]["lastAttemptReason"] == "recheck_ok"


def test_the_live_check_uses_the_day_listing_and_never_fetches_the_notice():
    import verify_live_titles as v

    task = {"candidateId": "job-x", "employerId": "msmt-vs_11000", "sourceUrl": url(1), "applicationUrl": url(1),
            "sourceHash": "sha256:x", "titles": [{"locale": "en", "title": "Postdoctoral researcher in robotics"}]}
    target, row = v.euraxess_evidence(task, None, None, NOW)
    assert row["status"] == "skipped_budget"  # no listing yet: nothing fetched
    confirmed = {"candidateId": "job-x", "status": "matched", "checkedAt": iso(NOW - timedelta(days=2))}
    assert v.euraxess_evidence(task, confirmed, "gen-1", NOW)[1]["carriedFrom"] == "gen-1"
    euraxess_source.save_listing({url(1): "Postdoctoral researcher in robotics"}, True, NOW - timedelta(hours=1))
    target, row = v.euraxess_evidence(task, None, None, NOW)
    assert (row["status"], row["tool"], row["checkedAt"]) == ("matched", "euraxess_listing", iso(NOW - timedelta(hours=1)))
    euraxess_source.save_listing({}, True, NOW - timedelta(hours=1))
    assert v.euraxess_evidence(task, None, None, NOW)[1]["status"] == "source_change_noted"
    euraxess_source.save_notices({"eu1": {"url": url(1), "title": "t", "fetchedAt": iso(NOW), "officialPostUrl": "https://www.cuni.cz/p"}})
    assert v.euraxess_evidence(task, None, None, NOW) == ("https://www.cuni.cz/p", None)


def test_the_day_listing_names_every_listed_notice_even_one_not_read_yet():
    """2026-10-08 replay: notices the throttle kept unread were left out of the day's listing."""
    search = "https://euraxess.ec.europa.eu/jobs/search?f%5B0%5D=job_country%3A747"
    listing = (
        "<p>Search results (2)</p>"
        '<article><a href="/jobs/1">Postdoctoral researcher in robotics</a></article>'
        '<article><a href="/jobs/2">Postdoctoral researcher in vision</a></article>'
    )
    source = {"id": SOURCE_ID, "url": search, "official": True, "sourceType": "official_job_listing_supplemental",
              "parser": "euraxess_search", "followDetails": False, "maxListingPages": 60}
    result = h.discover_registered_candidates(lambda target: (200, listing) if target == search else (429, ""), registry=[source])
    assert SOURCE_ID not in result["completeSourceIds"]
    listing_file = json.loads(euraxess_source.LISTING_PATH.read_text(encoding="utf-8"))
    assert listing_file["complete"] and set(listing_file["notices"]) == {url(1), url(2)}

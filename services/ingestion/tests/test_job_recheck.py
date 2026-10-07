from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import worker  # noqa: E402
from schedule import ScheduleManager, to_iso  # noqa: E402


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def job() -> dict:
    return {
        "id": "job-test",
        "sourceUrl": "https://example.invalid/job",
        "title": {"zh-CN": "研究助理", "en": "Research assistant", "cs": "Research assistant"},
        "lifecycleStatus": "open",
        "wholeOpportunityClosed": False,
        "publicationStatus": "approved",
        "visibility": "public",
    }


def window(ident: str, closes_at: str | None, *, precision: str = "date", status: str = "unknown") -> dict:
    return {
        "id": ident,
        "ownerType": "research_job",
        "ownerId": "job-test",
        "opensAt": None,
        "closesAt": closes_at,
        "timezone": "Europe/Prague",
        "datePrecision": precision,
        "status": status,
    }


def run_recheck(tmp_path: Path, windows: list[dict], fetch, now: datetime = NOW):
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(json.dumps({"jobs": [job()], "windows": windows}), encoding="utf-8")
    manager = ScheduleManager(tmp_path / "schedule.json")
    result = worker.recheck_open_jobs(
        fetch_page=fetch,
        now=now,
        jobs_path=jobs_path,
        schedule_manager=manager,
        use_lock=False,
    )
    return result, json.loads(jobs_path.read_text(encoding="utf-8")), manager.load_state(now)


@pytest.mark.parametrize(
    "windows",
    [
        [window("active", "2026-09-30"), window("old", "2026-09-01")],
        [window("old", "2026-09-01"), window("active", "2026-09-30")],
    ],
)
def test_one_expired_round_does_not_close_job_or_delete_active_round(tmp_path: Path, windows: list[dict]) -> None:
    result, payload, state = run_recheck(tmp_path, windows, lambda _url: (503, ""))
    assert result["status"] == "failed"
    assert result["failed"] == 1
    assert len(payload["windows"]) == 2
    assert {item["id"] for item in payload["windows"]} == {"active", "old"}
    assert next(item for item in payload["windows"] if item["id"] == "old")["status"] == "closed"
    assert next(item for item in payload["windows"] if item["id"] == "active")["status"] != "closed"
    assert payload["jobs"][0]["lifecycleStatus"] == "open"
    assert payload["jobs"][0]["wholeOpportunityClosed"] is False
    assert state["jobRecheck"]["lastSuccessAt"] is None
    assert state["jobRecheck"]["status"] == "failed"


def test_all_expired_rounds_archive_as_expired_without_fabricating_whole_closure(tmp_path: Path) -> None:
    result, payload, _state = run_recheck(
        tmp_path,
        [window("one", "2026-09-01"), window("two", "2026-09-06")],
        lambda _url: (200, "<h1>Research assistant</h1><p>Archived vacancy notice.</p>"),
    )
    assert result["closed"] == 1
    assert payload["jobs"][0]["lifecycleStatus"] == "expired"
    assert payload["jobs"][0]["visibility"] == "archived"
    assert payload["jobs"][0]["wholeOpportunityClosed"] is False
    assert all(item["status"] == "closed" for item in payload["windows"])


def test_future_and_unknown_windows_keep_opportunity_available(tmp_path: Path) -> None:
    _result, payload, _state = run_recheck(
        tmp_path,
        [window("old", "2026-09-01"), window("future-supplement", "2026-12-01"), window("unknown", None)],
        lambda _url: (200, "<h1>Research assistant</h1><p>No closure announcement.</p>"),
    )
    assert payload["jobs"][0]["lifecycleStatus"] == "open"
    assert len(payload["windows"]) == 3


def test_datetime_precision_uses_prague_timezone(tmp_path: Path) -> None:
    now = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)
    _result, payload, _state = run_recheck(
        tmp_path,
        [window("precise", "2026-09-07T14:00:00", precision="datetime")],
        lambda _url: (200, "<h1>Research assistant</h1><p>No closure announcement.</p>"),
        now,
    )
    assert payload["windows"][0]["status"] == "closed"
    assert payload["jobs"][0]["lifecycleStatus"] == "expired"


def test_official_whole_closure_overrides_future_round(tmp_path: Path) -> None:
    result, payload, _state = run_recheck(
        tmp_path,
        [window("future", "2026-12-01")],
        lambda _url: (200, "<h1>Research assistant</h1><p>This position has been filled. Applications are closed.</p>"),
    )
    assert result["status"] == "succeeded"
    assert payload["jobs"][0]["wholeOpportunityClosed"] is True
    assert payload["jobs"][0]["lifecycleStatus"] == "closed"
    assert payload["windows"][0]["status"] == "closed"


def test_mixed_http_results_complete_the_hourly_sweep(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    gone = job()
    gone["id"] = "job-gone"
    gone["sourceUrl"] = "https://example.invalid/gone"
    jobs_path.write_text(
        json.dumps({"jobs": [job(), gone], "windows": []}),
        encoding="utf-8",
    )
    manager = ScheduleManager(tmp_path / "schedule.json")

    def fetch(url: str):
        if url.endswith("/gone"):
            return 404, ""
        return 200, "<h1>Research assistant</h1><p>Applications remain open.</p>"

    result = worker.recheck_open_jobs(
        fetch_page=fetch,
        now=NOW,
        jobs_path=jobs_path,
        schedule_manager=manager,
        use_lock=False,
    )
    state = manager.load_state(NOW)
    assert result["status"] == "partial"
    assert result["httpSucceeded"] == 1
    assert result["failed"] == 1
    assert state["jobRecheck"]["status"] == "completed"
    assert state["jobRecheck"]["lastSuccessAt"] == to_iso(NOW)
    assert state["jobRecheck"]["lastError"] == "1/2 job status checks failed"
    assert state["jobRecheck"]["retryAt"] is None


def test_failed_recheck_keeps_previous_success_timestamp(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(json.dumps({"jobs": [job()], "windows": []}), encoding="utf-8")
    manager = ScheduleManager(tmp_path / "schedule.json")
    previous_success = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    manager.record_job_recheck_success(1, 0, previous_success)
    worker.recheck_open_jobs(
        fetch_page=lambda _url: (503, ""),
        now=NOW,
        jobs_path=jobs_path,
        schedule_manager=manager,
        use_lock=False,
    )
    state = manager.load_state(NOW)
    assert state["jobRecheck"]["lastSuccessAt"] == to_iso(previous_success)
    assert state["jobRecheck"]["lastAttemptAt"] == to_iso(NOW)


def test_archived_job_without_windows_is_not_resurrected_or_refetched(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    archived = job()
    archived.update(
        {
            "lifecycleStatus": "expired",
            "visibility": "archived",
            "publicationStatus": "review_pending",
            "lastAttemptReason": "past-deadline-archived",
        }
    )
    jobs_path.write_text(json.dumps({"jobs": [archived], "windows": []}), encoding="utf-8")
    manager = ScheduleManager(tmp_path / "schedule.json")
    calls = []
    result = worker.recheck_open_jobs(
        fetch_page=lambda url: calls.append(url) or (200, "should not be fetched"),
        now=NOW,
        jobs_path=jobs_path,
        schedule_manager=manager,
        use_lock=False,
    )
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert calls == []
    assert result["checked"] == 0
    assert payload["jobs"][0]["lifecycleStatus"] == "expired"
    assert payload["jobs"][0]["visibility"] == "archived"


def test_lmc_job_recheck_reads_the_official_widget_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs_path = tmp_path / "jobs.json"
    current = job()
    current.update(
        {
            "sourceUrl": "https://vut.test/detail-pozice?r=detail&id=2001",
            "sourceItemId": "2001",
            "discoverySourceId": "vut-test",
        }
    )
    jobs_path.write_text(json.dumps({"jobs": [current], "windows": []}), encoding="utf-8")
    manager = ScheduleManager(tmp_path / "schedule.json")
    source = {
        "id": "vut-test",
        "url": "https://vut.test/",
        "apiUrl": "https://api.vut.test/graphql",
        "parser": "lmc_graphql",
    }
    monkeypatch.setattr(worker, "load_registry", lambda: [source])
    landing = (
        '<script>window.__LMC_CAREER_WIDGET__.push('
        '{"apiKey":"public-key","widgetId":"widget-1","host":"vut.test"});</script>'
    )
    post_calls: list[str] = []

    def post_json(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, str]:
        post_calls.append(payload["variables"]["jobAdId"])
        assert url == source["apiUrl"]
        assert headers == {"X-Api-Key": "public-key"}
        return 200, json.dumps(
            {
                "data": {
                    "widget": {
                        "jobAd": {
                            "id": "2001",
                            "title": "Research assistant",
                            "content": {"htmlContent": "<p>Applications remain open.</p>"},
                        }
                    }
                }
            }
        )

    result = worker.recheck_open_jobs(
        fetch_page=lambda url: (200, landing) if url == source["url"] else (404, ""),
        post_json=post_json,
        now=NOW,
        jobs_path=jobs_path,
        schedule_manager=manager,
        use_lock=False,
    )
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert result == {"checked": 1, "httpSucceeded": 1, "failed": 0, "closed": 0, "status": "succeeded"}
    assert post_calls == ["2001"]
    assert payload["jobs"][0]["lifecycleStatus"] == "open"
    assert payload["jobs"][0]["lastAttemptReason"] == "recheck_ok"


def test_lmc_authoritative_missing_detail_is_hidden_as_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs_path = tmp_path / "jobs.json"
    current = job()
    current.update(
        {
            "sourceUrl": "https://vut.test/detail-pozice?r=detail&id=2001",
            "sourceItemId": "2001",
            "discoverySourceId": "vut-test",
        }
    )
    jobs_path.write_text(
        json.dumps({"jobs": [current], "windows": [window("future", "2026-12-01")]}),
        encoding="utf-8",
    )
    manager = ScheduleManager(tmp_path / "schedule.json")
    monkeypatch.setattr(
        worker,
        "load_registry",
        lambda: [
            {
                "id": "vut-test",
                "url": "https://vut.test/",
                "apiUrl": "https://api.vut.test/graphql",
                "parser": "lmc_graphql",
            }
        ],
    )
    landing = (
        '<script>window.__LMC_CAREER_WIDGET__.push('
        '{"apiKey":"public-key","widgetId":"widget-1","host":"vut.test"});</script>'
    )
    result = worker.recheck_open_jobs(
        fetch_page=lambda _url: (200, landing),
        post_json=lambda *_args: (200, '{"data":{"widget":{"jobAd":null}}}'),
        now=NOW,
        jobs_path=jobs_path,
        schedule_manager=manager,
        use_lock=False,
    )
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert result["status"] == "succeeded"
    assert result["closed"] == 1
    assert payload["jobs"][0]["lifecycleStatus"] == "unavailable"
    assert payload["jobs"][0]["visibility"] == "archived"
    assert payload["jobs"][0]["wholeOpportunityClosed"] is False
    assert payload["windows"][0]["closedReason"] == "official_application_unavailable"


def test_partial_shard_is_recorded_as_done_not_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Owner decision 2026-10-04: individual source failures are dropped, not retried."""
    calls: list[str] = []

    class FakeSchedule:
        def record_source_result(self, *_args, **_kwargs):
            return None

        def record_shard_success(self, *_args, **_kwargs):
            calls.append("success")

        def record_shard_failure(self, *_args, **_kwargs):
            calls.append("failure")

        def record_shard_partial(self, *_args, **_kwargs):
            calls.append("partial")

    plan = {
        "date": "2026-09-07",
        "shard": 1,
        "shardCount": 5,
        "institutionIds": ["school"],
        "jobIds": [],
        "counts": {},
        "schools": [{"id": "school", "msmtCode": "VS_TEST"}],
        "jobs": [],
    }
    monkeypatch.setattr(worker, "plan_for_day", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(worker, "RunLock", lambda: nullcontext())
    monkeypatch.setattr(worker, "ScheduleManager", FakeSchedule)
    monkeypatch.setattr(worker, "harvest_programmes", lambda *_args: [{"msmtCode": "VS_TEST", "status": "http_503", "parsedProgrammes": 0}])
    monkeypatch.setattr(worker, "rebuild_inventory", lambda: {})
    monkeypatch.setattr(worker, "atomic_write", lambda *_args: None)
    monkeypatch.setattr(worker, "RUNS", tmp_path)
    result = worker.run_once(skip_portals=True, now=NOW)
    assert result["status"] == "partial"
    assert result["failed"] == 1
    assert calls == ["partial"]


def test_a_recheck_stops_at_its_budget_and_keeps_the_rest(tmp_path, monkeypatch):
    import json as _json

    import worker

    jobs_path = tmp_path / "jobs.json"
    jobs = [
        {"id": f"job-{index}", "sourceUrl": f"https://example.cz/{index}", "lifecycleStatus": "unknown",
         "visibility": "public", "lastStatusCheckedAt": f"2026-10-0{index}T00:00:00Z"}
        for index in (3, 1, 2)
    ]
    jobs_path.write_text(_json.dumps({"jobs": jobs, "windows": []}), encoding="utf-8")
    monkeypatch.setenv("WORKER_TASK_BUDGET_SECONDS", "0.000001")
    clock = iter([0.0] + [10.0] * 100)
    monkeypatch.setattr(worker.time, "monotonic", lambda: next(clock))
    result = worker.recheck_open_jobs(
        fetch_page=lambda url: (200, "<h1>Open</h1>"),
        jobs_path=jobs_path,
        schedule_manager=worker.ScheduleManager(tmp_path / "state.json"),
        use_lock=False,
        safety_dir=tmp_path / "safety",
    )
    written = _json.loads(jobs_path.read_text(encoding="utf-8"))
    assert [job["id"] for job in written["jobs"]] == ["job-3", "job-1", "job-2"]
    assert written["lastRecheckResult"]["deferredToNextRun"] == 3
    assert isinstance(result, dict)


def test_a_shard_out_of_time_stops_between_schools_and_is_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-10-06: every shard was killed in its portal probes and retried behind other work."""
    import worker

    calls: list[tuple[str, str]] = []

    class FakeSchedule:
        def record_source_result(self, *_args, **_kwargs):
            return None

        def record_shard_success(self, *_args, **_kwargs):
            calls.append(("success", ""))

        def record_shard_partial(self, _shard, error, *_args, **_kwargs):
            calls.append(("partial", error))

        def record_shard_failure(self, *_args, **_kwargs):
            calls.append(("failure", ""))

    schools = [{"id": "a", "msmtCode": "VS_A", "officialUrl": "https://a.cz"}, {"id": "b", "msmtCode": "VS_B", "officialUrl": "https://b.cz"}]
    plan = {"date": "2026-10-06", "shard": 2, "shardCount": 5, "institutionIds": ["a", "b"], "jobIds": [],
            "counts": {}, "schools": schools, "jobs": []}
    order: list[str] = []
    monkeypatch.setattr(worker, "plan_for_day", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(worker, "RunLock", lambda: nullcontext())
    monkeypatch.setattr(worker, "ScheduleManager", FakeSchedule)
    monkeypatch.setattr(worker, "harvest_jobs", lambda *_args, **_kwargs: order.append("jobs") or {})
    monkeypatch.setattr(worker, "baseline_schools", lambda: schools)
    monkeypatch.setattr(worker, "rebuild_inventory", lambda: {})
    monkeypatch.setattr(worker, "atomic_write", lambda *_args: None)
    monkeypatch.setattr(worker, "RUNS", tmp_path)
    monkeypatch.setenv("WORKER_TASK_BUDGET_SECONDS", "1")
    clock = iter([0.0] + [100.0] * 100)
    monkeypatch.setattr(worker.time, "monotonic", lambda: next(clock))
    result = worker.run_once(now=NOW)
    assert order == ["jobs"]
    assert result["programmes"] == [] and result["portals"]["attempts"] == []
    assert result["deferredSchools"] == ["a", "b"]
    assert result["status"] == "partial"
    assert calls == [("partial", "2 schools not reached in the time budget in shard 2")]


def _stated_deadline_case(tmp_path, page_text, opens_at="2026-08-26"):
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(json.dumps({
        "jobs": [{"id": "job-x", "sourceUrl": "https://example.cz/x", "lifecycleStatus": "open", "visibility": "public",
                  "publicationStatus": "approved", "originalText": "Odborný asistent", "title": {"en": "Assistant professor"}}],
        "windows": [{"id": "w-x", "ownerId": "job-x", "opensAt": opens_at, "closesAt": None, "status": "unknown"}],
    }), encoding="utf-8")
    worker.recheck_open_jobs(
        fetch_page=lambda url: (200, f"<h1>Odborný asistent</h1><p>{page_text}</p>"),
        now=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
        jobs_path=jobs_path,
        schedule_manager=ScheduleManager(tmp_path / "state.json"),
        use_lock=False,
        safety_dir=tmp_path / "safety",
    )
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    return payload["jobs"][0], payload["windows"][0]


def test_a_stated_deadline_that_passed_archives_the_vacancy(tmp_path):
    """2026-10-06: six VUT adverts past their 18-25 Sept deadlines stayed open with no closing date."""
    job, window = _stated_deadline_case(tmp_path, "Přihlášky odešlete pomocí formuláře do 25.9.2026.")
    assert (job["lifecycleStatus"], job["visibility"], job["lastAttemptReason"]) == ("expired", "archived", "stated_deadline_passed")
    assert (window["closesAt"], window["status"], window["closedReason"]) == ("2026-09-25", "closed", "deadline_expired")


def test_a_future_or_earlier_stated_date_leaves_the_vacancy_open(tmp_path):
    job, window = _stated_deadline_case(tmp_path, "Přihlášky odešlete do 25.10.2026.")
    assert (job["lifecycleStatus"], job["visibility"], window["closesAt"]) == ("open", "public", None)
    # A date before this round opened is not its deadline.
    job, window = _stated_deadline_case(tmp_path, "Přihlášky odešlete do 25.6.2026.")
    assert (job["lifecycleStatus"], window["closesAt"]) == ("open", None)


def test_the_shard_reads_only_live_stored_vacancies_and_keeps_their_scope(tmp_path, monkeypatch):
    """2026-10-03: a delisted VUT advert archived the day before was rebuilt as open by the shard re-read."""
    import harvest_nine_hei_jobs

    jobs_path = tmp_path / "jobs.json"
    base = {"employerId": "msmt-vs_26000", "sourceUrl": "https://vutbr.jobs.cz/x", "track": "post_master",
            "title": {"cs": "Odborný asistent"}, "sourceLanguage": "cs"}
    jobs_path.write_text(json.dumps({"jobs": [
        {**base, "id": "live", "visibility": "public", "lifecycleStatus": "open", "catalogueScopeStatus": "unspecified"},
        {**base, "id": "gone", "visibility": "archived", "lifecycleStatus": "unavailable"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(worker, "JOBS_OUT", jobs_path)
    school = {"id": "msmt-vs_26000", "msmtCode": "VS_26000"}
    plan = worker.plan_for_day(datetime(2026, 10, 6).date(), [school], shard=0, assignments_path=tmp_path / "a.json")
    assert plan["jobIds"] == ["live"]
    assert plan["jobs"][0]["_keepStoredScope"] is True
    html = "<h1>Odborný asistent</h1><p>Výzkum a publikační činnost v oboru.</p>"
    seed = {**plan["jobs"][0], "_factHtml": html}
    previous = json.loads(jobs_path.read_text(encoding="utf-8"))
    payload = harvest_nine_hei_jobs.harvest_candidates([seed], lambda url: (200, html), previous, sleep_seconds=0)
    assert payload["jobs"][0]["catalogueScopeStatus"] == "unspecified"


def test_a_source_whose_table_decides_openness_keeps_its_posts(tmp_path, monkeypatch):
    """Dry run 2026-10-06: EURAXESS dates long past archived 16 RoboProx posts CIIRC still lists Open."""
    monkeypatch.setattr(worker, "load_registry", lambda: [{"id": "roboprox", "parser": "roboprox_positions"}])
    jobs_path = tmp_path / "jobs.json"
    job = {"id": "job-r", "sourceUrl": "https://euraxess.ec.europa.eu/jobs/1", "lifecycleStatus": "unknown",
           "visibility": "public", "discoverySourceId": "roboprox", "originalText": "PhD position"}
    jobs_path.write_text(json.dumps({"jobs": [job], "windows": []}), encoding="utf-8")
    worker.recheck_open_jobs(
        fetch_page=lambda url: (200, "<h1>PhD position</h1><p>Application deadline: 31 March 2026</p>"),
        now=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
        jobs_path=jobs_path,
        schedule_manager=ScheduleManager(tmp_path / "state.json"),
        use_lock=False,
        safety_dir=tmp_path / "safety",
    )
    stored = json.loads(jobs_path.read_text(encoding="utf-8"))["jobs"][0]
    assert (stored["lifecycleStatus"], stored["visibility"]) == ("unknown", "public")


def test_a_closure_phrase_in_a_condition_does_not_close_a_post():
    """2026-10-07: eight open posts were recorded closed by conditional sentences."""
    import harvest_nine_hei_jobs as h

    open_posts = (
        # CTU 6G Mobile PhD on EURAXESS 466323; its own page said "Call is open".
        "The applications will be continuously evaluated until the position is filled.",
        "We accept applications until November 6th, 2026, or until the position is filled.",
        # University of Ostrava boilerplate on four open posts.
        "The selection procedure may be cancelled or re-announced.",
        "The selection process may be canceled or reopened.",
        "Výběrové řízení probíhá, dokud nebude místo obsazeno.",
    )
    closed_posts = ("This position has been filled.", "Applications are closed.", "The call was cancelled.", "Místo je obsazeno.")
    assert [text for text in open_posts if h.page_is_closed(text)] == []
    assert [text for text in closed_posts if not h.page_is_closed(text)] == []

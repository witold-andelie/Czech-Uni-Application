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


def test_partial_shard_is_recorded_as_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeSchedule:
        def record_source_result(self, *_args, **_kwargs):
            return None

        def record_shard_success(self, *_args, **_kwargs):
            calls.append("success")

        def record_shard_failure(self, *_args, **_kwargs):
            calls.append("failure")

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
    assert calls == ["failure"]

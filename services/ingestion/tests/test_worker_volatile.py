from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import harvest_nine_hei_jobs  # noqa: E402
import worker  # noqa: E402
from schedule import ScheduleManager, to_iso  # noqa: E402


def _studyin_card(item_id: str, locale: str) -> str:
    title = "Computer Science" if locale == "en" else "Informatika"
    language = "English" if locale == "en" else "angličtina"
    degree = "Bachelor study programme" if locale == "en" else "bakalářský studijní program"
    return f"""
    <article>
      <h3><a href="/programme/{item_id}">{title}</a></h3>
      <input name="itemId" value="{item_id}" />
      <p class="font-semibold">Univerzita Karlova (Faculty)</p>
      <ul>
        <li><span role="tooltip">Study type</span>{degree}</li>
        <li><span role="tooltip">Study form:</span>full-time</li>
        <li><span role="tooltip">Study language:</span>{language}</li>
      </ul>
    </article>
    """


def _studyin_response(total: int, cards: list[str], locale: str) -> str:
    label = "Results found" if locale == "en" else "Nalezeno výsledků"
    return json.dumps(
        {
            "data": [
                {
                    "targetBlock": "#programSearchListContainer",
                    "content": f"<p>{label}: {total}</p>" + "".join(cards),
                }
            ]
        }
    )


def test_programme_availability_refresh_writes_candidate_and_advances_only_its_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "studyin.json"
    monkeypatch.setattr(worker, "RUNS", tmp_path / "runs")
    manager = ScheduleManager(tmp_path / "schedule.json")
    now = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
    manager.init_state(now)
    item_id = "11111111-1111-1111-1111-111111111111"

    def fetch(url: str) -> tuple[int, str]:
        query = parse_qs(urlparse(url).query)
        locale = query["language"][0]
        if query.get("openApplicationsOnly") == ["true"]:
            return 200, _studyin_response(0, [], locale)
        return 200, _studyin_response(1, [_studyin_card(item_id, locale)], locale)

    result = worker.refresh_programme_availability(
        fetch,
        now,
        output_path=output,
        schedule_manager=manager,
        use_lock=False,
    )
    state = manager.load_state(now)
    assert result["counts"]["programmes"] == 1
    assert json.loads(output.read_text(encoding="utf-8"))["catalogKind"] == "candidate_not_published"
    assert state["programmeAvailability"]["lastSuccessAt"] == to_iso(now)
    assert state["programmeAvailability"]["nextDueAt"] == to_iso(now + timedelta(hours=2))
    assert state["jobDiscovery"]["lastSuccessAt"] is None


def test_all_source_job_discovery_is_independent_of_daily_school_shard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = "https://www.muni.cz/en/about-us/careers"
    detail = "https://www.muni.cz/en/about-us/careers/vacancies/98765-new"
    registry = [
        {
            "id": "muni-test",
            "url": listing,
            "baseUrl": "https://www.muni.cz",
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_14000",
            "parser": "muni_vacancies",
            "followDetails": True,
        }
    ]
    pages = {
        listing: (200, '<a href="/en/about-us/careers/vacancies/98765-new">Research assistant in AI</a>'),
        detail: (
            200,
            "<h1>Research assistant in AI</h1><p>Master degree. Employment contract. "
            "Application deadline: 2026-09-30.</p>",
        ),
    }
    monkeypatch.setattr(harvest_nine_hei_jobs, "SLEEP", 0)
    monkeypatch.setattr(harvest_nine_hei_jobs, "RAW", tmp_path / "raw")
    manager = ScheduleManager(tmp_path / "schedule.json")
    now = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
    manager.init_state(now)

    result = worker.discover_all_jobs(
        lambda url: pages[url],
        now,
        jobs_path=tmp_path / "jobs.json",
        registry=registry,
        schedule_manager=manager,
        use_lock=False,
    )
    state = manager.load_state(now)
    assert result["status"] == "succeeded"
    assert result["discovery"]["discoveredCount"] == 1
    assert state["jobDiscovery"]["lastSuccessAt"] == to_iso(now)
    assert state["jobDiscovery"]["nextDueAt"] == to_iso(now + timedelta(hours=4))
    assert state["shards"]["0"]["lastSuccessAt"] is None


# ---------------------------------------------------------------------------
# A86: all-source success must be proven, not inferred from answered sources.
# ---------------------------------------------------------------------------


def _a86_registry() -> list[dict]:
    return [
        {
            "id": "source-a",
            "url": "https://a.test/jobs",
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_14000",
            "parser": "generic_listing_links",
            "followDetails": False,
        },
        {
            "id": "source-b",
            "url": "https://b.test/jobs",
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_27000",
            "parser": "generic_listing_links",
            "followDetails": False,
        },
    ]


def _a86_discovery(
    expected: list[str],
    complete: list[str],
    deferred: list[str],
    attempted: list[str],
):
    attempts = [
        {"sourceId": sid, "url": f"https://{sid}.test/jobs", "status": 200, "ok": True, "kind": "listing"}
        for sid in attempted
    ]
    return {
        "candidates": [],
        "attempts": attempts,
        "quarantined": [],
        "expectedSourceIds": expected,
        "completeSourceIds": complete,
        "deferredSourceIds": deferred,
        "runKind": "all_registered_sources",
        "discoveredCount": 0,
        "disappearedCount": 0,
    }


def _run_a86(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, discovery: dict, now):
    monkeypatch.setattr(worker, "harvest_jobs", lambda *args, **kwargs: {"discovery": discovery})
    monkeypatch.setattr(harvest_nine_hei_jobs, "SLEEP", 0)
    manager = ScheduleManager(tmp_path / "schedule.json")
    manager.init_state(now)
    result = worker.discover_all_jobs(
        lambda url: (200, "<html></html>"),
        now,
        jobs_path=tmp_path / "jobs.json",
        registry=_a86_registry(),
        schedule_manager=manager,
        use_lock=False,
    )
    state = manager.load_state(now)
    return result, state


def test_all_source_success_requires_every_expected_source_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 13, 6, 0, tzinfo=timezone.utc)
    # Source B never produced an attempt: silent skip, not a complete sweep.
    discovery = _a86_discovery(["source-a", "source-b"], ["source-a"], [], ["source-a"])
    result, state = _run_a86(tmp_path, monkeypatch, discovery, now)
    assert result["allSourceComplete"] is False
    assert result["unaccountedSourceIds"] == ["source-b"]
    assert state["jobDiscovery"].get("lastAllSourceSuccessAt") is None


def test_all_source_success_blocked_when_source_deferred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 13, 6, 0, tzinfo=timezone.utc)
    discovery = _a86_discovery(["source-a", "source-b"], ["source-a"], ["source-b"], ["source-a"])
    result, state = _run_a86(tmp_path, monkeypatch, discovery, now)
    assert result["allSourceComplete"] is False
    assert state["jobDiscovery"].get("lastAllSourceSuccessAt") is None


def test_all_source_success_blocked_when_complete_falls_short(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 13, 6, 0, tzinfo=timezone.utc)
    # Both sources answered, but B's run was not complete.
    discovery = _a86_discovery(["source-a", "source-b"], ["source-a"], [], ["source-a", "source-b"])
    result, state = _run_a86(tmp_path, monkeypatch, discovery, now)
    assert result["allSourceComplete"] is False
    assert state["jobDiscovery"].get("lastAllSourceSuccessAt") is None


def test_all_source_success_recorded_only_for_full_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 13, 6, 0, tzinfo=timezone.utc)
    discovery = _a86_discovery(
        ["source-a", "source-b"], ["source-a", "source-b"], [], ["source-a", "source-b"]
    )
    result, state = _run_a86(tmp_path, monkeypatch, discovery, now)
    assert result["allSourceComplete"] is True
    assert result["unaccountedSourceIds"] == []
    assert state["jobDiscovery"].get("lastAllSourceSuccessAt") == (
        now.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from schedule import (  # noqa: E402
    JOB_DISCOVERY_INTERVAL_HOURS,
    JOB_RECHECK_INTERVAL_HOURS,
    PROGRAMME_AVAILABILITY_INTERVAL_HOURS,
    SLA_HOURS,
    ScheduleManager,
    to_iso,
)


def test_init_state(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    state = mgr.load_state(now)

    assert state["version"] == "3.3"
    assert state["slaHours"] == 120
    assert len(state["shards"]) == 5
    for s in range(5):
        assert str(s) in state["shards"]
        assert state["shards"][str(s)]["status"] == "idle"
        assert state["shards"][str(s)]["lastSuccessAt"] is None
    assert state["jobRecheck"]["intervalHours"] == 1
    assert state["jobDiscovery"]["intervalHours"] == 4
    assert state["programmeAvailability"]["intervalHours"] == 2
    assert state["czuProgrammeAvailability"]["intervalHours"] == 2
    assert state["czuCzechProgrammeAvailability"]["intervalHours"] == 2
    assert state["czuDoctoralProgrammeAvailability"]["intervalHours"] == 2
    assert state_file.exists()


def test_sla_breach_detection_after_downtime(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    base_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    mgr.init_state(base_time)

    # Shard 0 succeeded at base_time
    mgr.record_shard_success(0, base_time)

    # Simulate 130 hours later (>120h SLA breach)
    current_time = base_time + timedelta(hours=130)
    breaches = mgr.check_sla_and_overdue(current_time)

    assert any(b["shardIndex"] == 0 for b in breaches)
    shard0_breach = next(b for b in breaches if b["shardIndex"] == 0)
    assert shard0_breach["overdueHours"] == 10.0

    state = mgr.load_state(current_time)
    assert state["shards"]["0"]["status"] == "overdue"
    assert len(state["slaBreaches"]) >= 1


def test_pending_tasks_priority_ordering(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    base_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    mgr.init_state(base_time)

    # Shard 1 succeeded 140h ago (breached SLA by 20h)
    mgr.record_shard_success(1, base_time)
    # Shard 2 succeeded 130h ago (breached SLA by 10h)
    mgr.record_shard_success(2, base_time + timedelta(hours=10))
    # Shard 3 succeeded 20h ago (within SLA)
    mgr.record_shard_success(3, base_time + timedelta(hours=120))

    now = base_time + timedelta(hours=140)
    tasks = mgr.get_pending_tasks(now)

    # Overdue tasks must come first, with shard 1 before shard 2 (since 1 is more overdue)
    overdue_shards = [t["shardIndex"] for t in tasks if t.get("priority") == "overdue_catchup"]
    assert 1 in overdue_shards
    assert 2 in overdue_shards
    assert overdue_shards.index(1) < overdue_shards.index(2)


def test_lease_acquisition_and_concurrency_protection(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    mgr.init_state(now)

    # First acquisition succeeds
    assert mgr.acquire_lease("shard_refresh", shard_index=0, lease_seconds=600, now=now) is True

    # Second acquisition for same shard while lease is active fails
    assert mgr.acquire_lease("shard_refresh", shard_index=0, lease_seconds=600, now=now + timedelta(seconds=100)) is False

    # Acquisition for another shard succeeds
    assert mgr.acquire_lease("shard_refresh", shard_index=1, lease_seconds=600, now=now) is True

    # After lease expires, acquisition succeeds again
    later = now + timedelta(seconds=700)
    assert mgr.acquire_lease("shard_refresh", shard_index=0, lease_seconds=600, now=later) is True


def test_failure_retry_backoff(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    mgr.init_state(now)

    # Fail shard 0
    mgr.record_shard_failure(0, error="Connection reset by peer", now=now)

    state = mgr.load_state(now)
    assert state["shards"]["0"]["status"] == "failed"
    assert state["shards"]["0"]["attempts"] == 1
    assert state["shards"]["0"]["retryAt"] == to_iso(now + timedelta(seconds=300))

    # Before retryAt, not in retry tasks
    tasks = mgr.get_pending_tasks(now + timedelta(seconds=100))
    assert not any(t.get("priority") == "retry" and t.get("shardIndex") == 0 for t in tasks)
    assert not any(t.get("shardIndex") == 0 for t in tasks)

    # After retryAt, is ready for retry
    tasks_after = mgr.get_pending_tasks(now + timedelta(seconds=301))
    assert any(t.get("priority") == "retry" and t.get("shardIndex") == 0 for t in tasks_after)


def test_failed_job_recheck_does_not_advance_last_success(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    first = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    mgr.record_job_recheck_success(4, 0, first)
    mgr.record_job_recheck_failure(
        "all HTTP 503",
        checked_count=4,
        closed_count=0,
        now=first + timedelta(hours=24),
    )
    state = mgr.load_state(first + timedelta(hours=24))
    assert state["jobRecheck"]["lastSuccessAt"] == to_iso(first)
    assert state["jobRecheck"]["lastAttemptAt"] == to_iso(first + timedelta(hours=24))
    assert state["jobRecheck"]["status"] == "failed"
    assert state["jobRecheck"]["retryAt"] == to_iso(first + timedelta(hours=24, seconds=300))


def test_expired_owner_cannot_release_reacquired_lease(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    first = ScheduleManager(state_file)
    second = ScheduleManager(state_file)
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    assert first.acquire_lease("shard_refresh", shard_index=2, lease_seconds=60, now=now)
    assert second.acquire_lease("shard_refresh", shard_index=2, lease_seconds=60, now=now + timedelta(seconds=61))
    first.release_lease("shard_refresh", shard_index=2, now=now + timedelta(seconds=62))
    state = second.load_state(now + timedelta(seconds=62))
    assert state["shards"]["2"]["leaseOwner"] == second.owner_id
    assert state["shards"]["2"]["leaseUntil"] == to_iso(now + timedelta(seconds=121))


def test_source_failures_are_tracked_independently_and_stay_in_sla(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    base = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    mgr.record_source_result("programme:a", succeeded=False, error="HTTP 503", now=base)
    mgr.record_source_result("programme:b", succeeded=True, now=base + timedelta(hours=1))
    breaches = mgr.check_sla_and_overdue(base + timedelta(hours=121))
    state = mgr.load_state(base + timedelta(hours=121))
    assert state["sources"]["programme:a"]["lastSuccessAt"] is None
    assert state["sources"]["programme:b"]["lastSuccessAt"] == to_iso(base + timedelta(hours=1))
    assert any(item.get("sourceId") == "programme:a" for item in breaches)


def test_next_wake_honours_five_minute_retry(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    mgr.init_state(now)
    mgr.record_shard_failure(1, "HTTP 503", now)
    assert mgr.next_wake_seconds(now) == 300


def test_volatile_sources_have_independent_short_cadences(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    now = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
    mgr.init_state(now)
    mgr.record_volatile_success("job_recheck", now=now)
    mgr.record_volatile_success("job_discovery", now=now)
    mgr.record_volatile_success("programme_availability", now=now)
    mgr.record_volatile_success("czu_programme_availability", now=now)
    mgr.record_volatile_success("czu_czech_programme_availability", now=now)
    mgr.record_volatile_success("czu_doctoral_programme_availability", now=now)

    after_one_hour = mgr.get_pending_tasks(now + timedelta(hours=JOB_RECHECK_INTERVAL_HOURS))
    assert any(item["type"] == "job_recheck" for item in after_one_hour)
    assert not any(item["type"] == "job_discovery" for item in after_one_hour)
    assert not any(item["type"] == "programme_availability" for item in after_one_hour)
    assert not any(item["type"] == "czu_programme_availability" for item in after_one_hour)
    assert not any(item["type"] == "czu_czech_programme_availability" for item in after_one_hour)
    assert not any(item["type"] == "czu_doctoral_programme_availability" for item in after_one_hour)

    after_two_hours = mgr.get_pending_tasks(
        now + timedelta(hours=PROGRAMME_AVAILABILITY_INTERVAL_HOURS)
    )
    assert any(item["type"] == "programme_availability" for item in after_two_hours)
    assert any(item["type"] == "czu_programme_availability" for item in after_two_hours)
    assert any(item["type"] == "czu_czech_programme_availability" for item in after_two_hours)
    assert any(item["type"] == "czu_doctoral_programme_availability" for item in after_two_hours)
    assert not any(item["type"] == "job_discovery" for item in after_two_hours)

    after_four_hours = mgr.get_pending_tasks(
        now + timedelta(hours=JOB_DISCOVERY_INTERVAL_HOURS)
    )
    assert any(item["type"] == "job_discovery" for item in after_four_hours)


def test_v2_state_migrates_old_daily_job_recheck_to_hourly(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    base = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    legacy = mgr._new_state(base)
    legacy["version"] = "2.0"
    legacy["jobRecheck"]["intervalHours"] = 24
    legacy["jobRecheck"]["lastSuccessAt"] = to_iso(base)
    legacy["jobRecheck"]["nextDueAt"] = to_iso(base + timedelta(hours=24))
    legacy.pop("jobDiscovery")
    legacy.pop("programmeAvailability")
    legacy.pop("czuProgrammeAvailability")
    legacy.pop("czuCzechProgrammeAvailability")
    legacy.pop("czuDoctoralProgrammeAvailability")
    state_file.write_text(json.dumps(legacy), encoding="utf-8")

    migrated = mgr.load_state(base + timedelta(hours=2))
    assert migrated["version"] == "3.3"
    assert migrated["jobRecheck"]["intervalHours"] == JOB_RECHECK_INTERVAL_HOURS
    assert migrated["jobRecheck"]["nextDueAt"] == to_iso(
        base + timedelta(hours=JOB_RECHECK_INTERVAL_HOURS)
    )
    task_types = {item["type"] for item in mgr.get_pending_tasks(base + timedelta(hours=2))}
    assert "job_recheck" in task_types
    assert "programme_availability" in task_types
    assert "czu_programme_availability" in task_types
    assert "czu_czech_programme_availability" in task_types
    assert "czu_doctoral_programme_availability" in task_types
    assert "job_discovery" in task_types


def test_volatile_task_lease_and_retry_are_isolated(tmp_path: Path) -> None:
    state_file = tmp_path / "schedule-state.json"
    mgr = ScheduleManager(state_file)
    now = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
    mgr.init_state(now)
    assert mgr.acquire_lease("programme_availability", now=now)
    assert not mgr.acquire_lease("programme_availability", now=now)
    assert mgr.acquire_lease("job_discovery", now=now)

    mgr.record_volatile_failure("programme_availability", "partial pagination", now=now)
    before_retry = mgr.get_pending_tasks(now + timedelta(seconds=299))
    assert not any(item["type"] == "programme_availability" for item in before_retry)
    at_retry = mgr.get_pending_tasks(now + timedelta(seconds=300))
    assert any(
        item["type"] == "programme_availability" and item["priority"] == "retry"
        for item in at_retry
    )

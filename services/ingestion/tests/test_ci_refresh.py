import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ci_refresh import run_tick, task_command, tick_exit_code
from schedule import ScheduleManager, to_iso


def test_normal_daily_shard_is_executed(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "shard_refresh", "shardIndex": 2, "priority": "daily_scheduled"}]
    def run(command, **kwargs):
        assert command[-3:] == ["--once", "--shard", "2"]
        manager.record_shard_success(2)
        return SimpleNamespace(returncode=0)
    report = run_tick(manager, run=run, output=tmp_path / "report.json")
    assert not report["failed"]
    assert len(report["tasks"]) == 1


def test_timeout_preserves_retry_and_continues_other_sources(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "job_recheck"}, {"type": "job_discovery"}]
    def run(command, **kwargs):
        if command[-1] == "--recheck-jobs":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        manager.record_volatile_success("job_discovery")
        return SimpleNamespace(returncode=0)
    report = run_tick(manager, run=run, output=tmp_path / "report.json")
    assert report["failed"]
    assert len(report["tasks"]) == 2
    assert manager.load_state()["jobRecheck"]["retryAt"]
    assert manager.load_state()["jobRecheck"]["lastSuccessAt"] is None
    assert not report["tasks"][1]["failed"]


def test_partial_failure_is_not_hidden_by_zero_exit_code(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "job_discovery"}]
    def run(*args, **kwargs):
        manager.record_volatile_failure("job_discovery", "one source failed")
        return SimpleNamespace(returncode=0)
    report = run_tick(manager, run=run, output=tmp_path / "report.json")
    assert report["failed"]


def test_exhausted_budget_does_not_advance_success(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "job_discovery"}]
    report = run_tick(manager, budget=0, run=lambda *a, **k: None, output=tmp_path / "report.json")
    assert report["deferred"]
    assert not report["tasks"]
    assert manager.load_state()["jobDiscovery"]["lastSuccessAt"] is None
    assert tick_exit_code(report) == 0


def test_partial_job_recheck_does_not_fail_the_github_tick(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "job_recheck"}]

    def run(*args, **kwargs):
        manager.record_job_recheck_partial(
            "1/125 job status checks failed",
            checked_count=125,
            closed_count=5,
        )
        return SimpleNamespace(returncode=0)

    report = run_tick(manager, run=run, output=tmp_path / "report.json")
    assert not report["failed"]
    assert tick_exit_code(report) == 0
    assert "1/125" in (report["tasks"][0]["error"] or "")
    assert manager.load_state()["jobRecheck"]["status"] == "completed"
    assert manager.load_state()["jobRecheck"]["lastSuccessAt"]


def test_started_task_failure_still_fails_the_tick(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "job_discovery"}]
    def run(*args, **kwargs):
        manager.record_volatile_failure("job_discovery", "one source failed")
        return SimpleNamespace(returncode=0)
    report = run_tick(manager, run=run, output=tmp_path / "report.json")
    assert report["failed"]
    assert tick_exit_code(report) == 1


def test_never_attempted_source_precedes_recent_long_retry(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.record_volatile_failure("job_discovery", "timeout")
    # Within its interval a failed task is queued as a retry (schedule.py).
    manager.get_pending_tasks = lambda: [{"type": "job_discovery", "priority": "retry"},
                                         {"type": "czu_doctoral_programme_availability"}]
    seen = []
    def run(command, **kwargs):
        seen.append(command[-1])
        kind = "job_discovery" if command[-1] == "--discover-jobs" else "czu_doctoral_programme_availability"
        manager.record_volatile_success(kind)
        return SimpleNamespace(returncode=0)
    run_tick(manager, run=run, output=tmp_path / "report.json")
    assert seen[0] == "--refresh-czu-doctoral-programmes"


def test_worker_is_started_unbuffered():
    command = task_command({"type": "job_recheck"})
    assert command[1] == "-u"
    assert command[-1] == "--recheck-jobs"


def test_run_tick_logs_before_waiting_for_worker(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "job_recheck"}]
    order = []

    def run(command, **kwargs):
        assert kwargs.get("env", {}).get("PYTHONUNBUFFERED") == "1"
        order.append("run")
        manager.record_volatile_success("job_recheck")
        return SimpleNamespace(returncode=0)

    def log(message):
        order.append(message)

    run_tick(manager, run=run, output=tmp_path / "report.json", log=log)
    start = next(item for item in order if item.startswith("ci_refresh: start job_recheck"))
    assert order.index(start) < order.index("run")
    assert any(item.startswith("ci_refresh: finish job_recheck") for item in order)


def test_task_gets_a_graceful_budget_below_its_hard_timeout(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "job_discovery"}]
    seen = {}

    def run(command, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        seen["budget"] = float(kwargs["env"]["WORKER_TASK_BUDGET_SECONDS"])
        manager.record_volatile_success("job_discovery")
        return SimpleNamespace(returncode=0)

    run_tick(manager, run=run, output=tmp_path / "report.json")
    assert 0 < seen["budget"] < seen["timeout"]


def test_an_operator_can_force_a_task_that_is_not_due(tmp_path, monkeypatch):
    monkeypatch.setenv("CI_REFRESH_FORCE_TASKS", "job_discovery")
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: []
    seen = []

    def run(command, **kwargs):
        seen.append(command[-1])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    run_tick(manager, run=run, output=tmp_path / "report.json")
    assert seen == ["--discover-jobs"]


def test_a_forced_task_runs_before_rechecks_and_shards(tmp_path, monkeypatch):
    monkeypatch.setenv("CI_REFRESH_FORCE_TASKS", "job_discovery")
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [
        {"type": "job_recheck"},
        {"type": "shard_refresh", "shardIndex": 0},
        {"type": "job_discovery"},
    ]
    seen = []

    def run(command, **kwargs):
        seen.append(command[-1])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    run_tick(manager, run=run, output=tmp_path / "report.json")
    assert seen[0] == "--discover-jobs"


def test_a_shard_with_some_failed_sources_is_done_and_not_retried(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.record_shard_partial(2, "9 source operations failed in shard 2")
    info = manager.load_state()["shards"]["2"]
    assert info["status"] == "completed" and info["retryAt"] is None
    assert info["lastError"] == "9 source operations failed in shard 2"
    assert not any(task.get("shardIndex") == 2 and task.get("priority") == "retry" for task in manager.get_pending_tasks())


def test_a_retry_runs_after_the_days_due_work(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [
        {"type": "shard_refresh", "shardIndex": 1, "priority": "retry"},
        {"type": "job_discovery"},
        {"type": "shard_refresh", "shardIndex": 3},
    ]
    seen = []

    def run(command, **kwargs):
        seen.append(command[-1])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    run_tick(manager, run=run, output=tmp_path / "report.json")
    assert seen[-1] == "1"


def test_a_shard_is_not_started_without_time_to_do_anything(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "shard_refresh", "shardIndex": 2}, {"type": "programme_availability"}]
    seen = []

    def run(command, **kwargs):
        seen.append(command[-1])
        return SimpleNamespace(returncode=0)

    report = run_tick(manager, budget=120, run=run, output=tmp_path / "report.json")
    assert [task["type"] for task in report["deferred"]] == ["shard_refresh"]
    assert seen == ["--refresh-programme-availability"]


def test_a_discovery_with_some_failed_sources_is_done_not_retried(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.record_volatile_partial("job_discovery", "3/60 registered job sources failed")
    info = manager.load_state()["jobDiscovery"]
    assert info["status"] == "completed" and info["retryAt"] is None
    assert info["lastError"] == "3/60 registered job sources failed"


def test_discovery_runs_right_after_the_recheck(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [
        {"type": "czu_programme_availability"},
        {"type": "shard_refresh", "shardIndex": 0, "priority": "daily_scheduled"},
        {"type": "job_discovery"},
        {"type": "job_recheck"},
    ]
    seen = []

    def run(command, **kwargs):
        seen.append((command[-1], kwargs["timeout"]))
        return SimpleNamespace(returncode=0)

    run_tick(manager, budget=6000, run=run, output=tmp_path / "report.json")
    assert [flag for flag, _ in seen] == ["--recheck-jobs", "--discover-jobs", "--refresh-czu-programmes", "0"]
    assert dict(seen)["--discover-jobs"] == 1800 and dict(seen)["0"] == 1200


def test_discovery_leaves_room_for_its_slowest_source(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "job_discovery"}]
    seen = {}

    def run(command, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        seen["budget"] = float(kwargs["env"]["WORKER_TASK_BUDGET_SECONDS"])
        return SimpleNamespace(returncode=0)

    run_tick(manager, budget=6000, run=run, output=tmp_path / "report.json")
    assert seen["timeout"] - seen["budget"] == 420


def test_the_tick_budget_comes_from_the_workflow(tmp_path, monkeypatch):
    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "programme_availability"}]
    monkeypatch.setenv("CI_REFRESH_BUDGET_SECONDS", "30")
    report = run_tick(manager, run=lambda *a, **k: SimpleNamespace(returncode=0), output=tmp_path / "report.json")
    assert [task["type"] for task in report["deferred"]] == ["programme_availability"]


def test_a_forced_extra_run_keeps_the_regular_daily_run(tmp_path):
    """2026-10-07: recheck and discovery forced the evening before were skipped by the morning tick."""
    from datetime import datetime, timedelta, timezone

    manager = ScheduleManager(tmp_path / "state.json")
    morning = datetime.now(timezone.utc) - timedelta(hours=9)
    manager.record_volatile_success("job_recheck", now=morning)  # regular run: due again morning + 24 h
    manager.get_pending_tasks = lambda: [{"type": "job_recheck", "priority": "forced"}]

    def run(command, **kwargs):
        manager.record_volatile_success("job_recheck")  # the worker's own record moves the due time on
        return SimpleNamespace(returncode=0)

    run_tick(manager, budget=6000, run=run, output=tmp_path / "report.json")
    info = manager.load_state()["jobRecheck"]
    assert info["nextDueAt"] == to_iso(morning + timedelta(hours=24))
    next_morning = morning + timedelta(hours=23, minutes=40)
    assert any(t["type"] == "job_recheck" for t in ScheduleManager(tmp_path / "state.json").get_pending_tasks(next_morning))


def test_a_forced_run_of_a_task_already_due_is_its_regular_run(tmp_path):
    from datetime import datetime, timedelta, timezone

    manager = ScheduleManager(tmp_path / "state.json")
    manager.record_volatile_success("job_discovery", now=datetime.now(timezone.utc) - timedelta(hours=30))
    manager.get_pending_tasks = lambda: [{"type": "job_discovery", "priority": "forced"}]

    def run(command, **kwargs):
        manager.record_volatile_success("job_discovery")
        return SimpleNamespace(returncode=0)

    run_tick(manager, budget=6000, run=run, output=tmp_path / "report.json")
    due = manager.load_state()["jobDiscovery"]["nextDueAt"]
    assert due > to_iso(datetime.now(timezone.utc) + timedelta(hours=23))

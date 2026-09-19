import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ci_refresh import run_tick, task_command, tick_exit_code
from schedule import ScheduleManager


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
    manager.get_pending_tasks = lambda: [{"type": "job_discovery"}, {"type": "czu_doctoral_programme_availability"}]
    seen = []
    def run(command, **kwargs):
        seen.append(command[-1])
        kind = "job_discovery" if command[-1] == "--discover-jobs" else "czu_doctoral_programme_availability"
        manager.record_volatile_success(kind)
        return SimpleNamespace(returncode=0)
    run_tick(manager, run=run, output=tmp_path / "report.json")
    assert seen[0] == "--refresh-czu-doctoral-programmes"

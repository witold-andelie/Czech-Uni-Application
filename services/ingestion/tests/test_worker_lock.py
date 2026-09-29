from __future__ import annotations

import json
import multiprocessing
import os
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import worker
from file_lock import lock_is_held, read_lock_metadata


def _process_lock_attempt(lock_path: str, acquired, release, results) -> None:
    try:
        with worker.RunLock(Path(lock_path)):
            results.put("acquired")
            acquired.set()
            release.wait(10)
    except SystemExit:
        results.put("blocked")


def test_pid_alive_current_process() -> None:
    # Current process must be alive and MUST NOT be terminated by the check
    current_pid = os.getpid()
    assert worker.pid_alive(current_pid) is True
    # Non-existent or invalid PID must return False
    assert worker.pid_alive(-1) is False
    assert worker.pid_alive(0) is False
    assert worker.pid_alive(4194304) is False  # Above typical max PID


def test_run_lock_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock_file = tmp_path / "test-run.lock"
    monkeypatch.setattr(worker, "LOCK", lock_file)
    monkeypatch.setattr(worker, "RUNS", tmp_path)

    # 1. Acquire lock
    with worker.RunLock():
        assert lock_file.exists()
        data = read_lock_metadata(lock_file)
        assert data["pid"] == os.getpid()
        assert lock_is_held(lock_file)

        # 2. Re-acquiring while active should fail with SystemExit
        with pytest.raises(SystemExit) as exc_info:
            with worker.RunLock():
                pass
        assert "refresh already running" in str(exc_info.value)

    # 3. Exiting releases the OS lock; the harmless sentinel may persist.
    assert lock_file.exists()
    assert not lock_is_held(lock_file)


def test_run_lock_stale_lock_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock_file = tmp_path / "test-run.lock"
    monkeypatch.setattr(worker, "LOCK", lock_file)
    monkeypatch.setattr(worker, "RUNS", tmp_path)

    # Write a stale lock with dead PID
    lock_file.write_text(json.dumps({"pid": 4194304, "startedAt": "2026-09-01T00:00:00Z"}), encoding="utf-8")

    # Should recover and acquire successfully
    with worker.RunLock():
        assert lock_file.exists()
        data = read_lock_metadata(lock_file)
        assert data["pid"] == os.getpid()

    assert not lock_is_held(lock_file)


def test_run_lock_does_not_delete_foreign_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock_file = tmp_path / "test-run.lock"
    monkeypatch.setattr(worker, "LOCK", lock_file)
    monkeypatch.setattr(worker, "RUNS", tmp_path)

    lock = worker.RunLock()
    # Simulate another PID having taken the lock
    lock_file.write_text(json.dumps({"pid": 99999, "startedAt": "2026-09-01T00:00:00Z"}), encoding="utf-8")

    # Exiting should not unlink foreign lock
    lock.__exit__(None, None, None)
    assert lock_file.exists()


def test_two_processes_cannot_enter_the_refresh_critical_section(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    results = context.Queue()
    lock_file = tmp_path / "process.lock"
    first = context.Process(target=_process_lock_attempt, args=(str(lock_file), acquired, release, results))
    second = context.Process(target=_process_lock_attempt, args=(str(lock_file), acquired, release, results))
    first.start()
    assert acquired.wait(10)
    second.start()
    second.join(10)
    release.set()
    first.join(10)
    assert not first.is_alive()
    assert not second.is_alive()
    assert sorted([results.get(timeout=2), results.get(timeout=2)]) == ["acquired", "blocked"]


def test_discovery_rotates_sources_and_defers_what_the_budget_does_not_reach(tmp_path, monkeypatch):
    """A bounded daily pass must not reach only the first registry sources forever."""
    import harvest_nine_hei_jobs

    sources = [{"id": "alpha"}, {"id": "beta"}, {"id": "gamma"}, {"id": "delta"}]
    monkeypatch.setattr(harvest_nine_hei_jobs, "load_registered_job_sources", lambda: sources)
    clock = {"now": 0.0}
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock["now"])
    visited = []
    original = worker.harvest_jobs

    def one_source(candidates, employer_ids=None, *, registry=None, **kwargs):
        if registry is not None and len(registry) == 1:
            visited.append(registry[0]["id"])
            clock["now"] += 100
            return {"discovery": {"completeSourceIds": [registry[0]["id"]]}}
        return original(candidates, employer_ids, registry=registry, **kwargs)

    monkeypatch.setattr(worker, "harvest_jobs", one_source)
    target = tmp_path / "jobs.json"
    target.write_text("{}", encoding="utf-8")
    result = original(
        [],
        fetch_page=lambda url: (200, ""),
        jobs_path=target,
        source_last_attempt={"alpha": "2026-09-29T08:30:00Z", "beta": "2026-09-28T08:30:00Z"},
        budget_seconds=150,
    )
    # Never-attempted sources first, then the oldest; stop between sources.
    assert visited == ["gamma", "delta"]
    assert result["discovery"]["deferredSourceIds"] == ["beta", "alpha"]

"""One bounded scheduler tick for GitHub Actions; no unreviewed publication."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from engine.runtime import require_http_fetcher, write_runtime_report
from schedule import ScheduleManager, VOLATILE_TASKS
from storage.postgres import load_database_env, require_database, store_from_env

ROOT = Path(__file__).resolve().parents[3]
FLAGS = {
    "job_recheck": "--recheck-jobs",
    "job_discovery": "--discover-jobs",
    "programme_availability": "--refresh-programme-availability",
    "czu_programme_availability": "--refresh-czu-programmes",
    "czu_czech_programme_availability": "--refresh-czu-czech-programmes",
    "czu_doctoral_programme_availability": "--refresh-czu-doctoral-programmes",
}


def _emit(message: str, log: Callable[[str], None] | None = None) -> None:
    if log is None:
        print(message, flush=True)
        return
    log(message)


def task_command(task: dict) -> list[str]:
    command = [sys.executable, "-u", str(ROOT / "services/ingestion/src/worker.py")]
    if task["type"] == "shard_refresh":
        shard = int(task["shardIndex"])
        if shard not in range(5):
            raise ValueError("Invalid shard")
        return command + ["--once", "--shard", str(shard)]
    return command + [FLAGS[task["type"]]]


def run_tick(manager=None, *, budget=2100, task_timeout=900,
             run=subprocess.run, clock=time.monotonic, output=None, log=None) -> dict:
    manager = manager or ScheduleManager()
    output = output or ROOT / "work/runs/ci-refresh-summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    tasks = manager.get_pending_tasks()
    # Status checks get first use of the bounded runner; the existing queue
    # determines the other tasks, including today's ordinary daily shard.
    state = manager.load_state()
    def task_order(task):
        info = (state["shards"].get(str(task["shardIndex"]), {}) if task["type"] == "shard_refresh"
                else state.get(VOLATILE_TASKS[task["type"]]["stateKey"], {}))
        return (task["type"] != "job_recheck", info.get("lastAttemptAt") or "")
    tasks.sort(key=task_order)
    _emit(
        "ci_refresh: "
        + json.dumps(
            {"pending": [{"type": item.get("type"), "shardIndex": item.get("shardIndex")} for item in tasks]},
            ensure_ascii=False,
        ),
        log,
    )
    deadline = clock() + budget
    report = {"tasks": [], "deferred": [], "failed": False}
    worker_env = os.environ.copy()
    worker_env["PYTHONUNBUFFERED"] = "1"
    worker_env.setdefault("PLAYWRIGHT_LAUNCH_TIMEOUT", "30000")
    for task in tasks:
        remaining = int(deadline - clock())
        if remaining < 30:
            report["deferred"].append(task)
            _emit(f"ci_refresh: defer {task.get('type')} remaining_s={remaining}", log)
            continue
        kind = task["type"]
        timeout = min(task_timeout, remaining)
        error = None
        _emit(f"ci_refresh: start {kind} timeout_s={timeout}", log)
        started = clock()
        try:
            result = run(
                task_command(task),
                cwd=ROOT,
                timeout=timeout,
                check=False,
                env=worker_env,
            )
            if result.returncode:
                error = f"Worker exited with status {result.returncode}"
        except (subprocess.TimeoutExpired, OSError) as exc:
            error = str(exc)
        if error:
            if kind == "shard_refresh":
                manager.record_shard_failure(task["shardIndex"], error)
            else:
                manager.record_volatile_failure(kind, error)
        state = manager.load_state()
        info = (state["shards"][str(task["shardIndex"])] if kind == "shard_refresh"
                else state[VOLATILE_TASKS[kind]["stateKey"]])
        failed = bool(error) or info.get("status") != "completed"
        report["failed"] |= failed
        report["tasks"].append({"task": task, "failed": failed, "error": error or info.get("lastError")})
        _emit(
            f"ci_refresh: finish {kind} elapsed_s={int(clock() - started)} failed={failed} error={error}",
            log,
        )
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def tick_exit_code(report: dict) -> int:
    """A bounded tick that defers leftover work is success. Started-task failure is not.

    A mixed job recheck (for example 124/125 official pages answered) records the
    miss and still completes the hourly sweep; that does not fail the GitHub job.
    """
    return 1 if report.get("failed") else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(ScheduleManager().get_pending_tasks(), indent=2), flush=True)
    else:
        print("ci_refresh: start", flush=True)
        load_database_env()
        require_database()
        store = store_from_env()
        if store is not None:
            print(json.dumps({"supabase": store.ping()}, indent=2), flush=True)
            store.close()
        else:
            print("ci_refresh: supabase store not configured", flush=True)
        runtime = write_runtime_report(ROOT / "work" / "runs" / "scrapling-runtime.json")
        print(json.dumps({"scrapling": runtime}, indent=2), flush=True)
        require_http_fetcher(runtime)
        result = run_tick()
        print(json.dumps(result, indent=2), flush=True)
        sys.exit(tick_exit_code(result))

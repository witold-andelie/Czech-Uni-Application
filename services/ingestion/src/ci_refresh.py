"""One bounded scheduler tick for GitHub Actions; no unreviewed publication."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from schedule import ScheduleManager, VOLATILE_TASKS

ROOT = Path(__file__).resolve().parents[3]
FLAGS = {
    "job_recheck": "--recheck-jobs",
    "job_discovery": "--discover-jobs",
    "programme_availability": "--refresh-programme-availability",
    "czu_programme_availability": "--refresh-czu-programmes",
    "czu_czech_programme_availability": "--refresh-czu-czech-programmes",
    "czu_doctoral_programme_availability": "--refresh-czu-doctoral-programmes",
}


def task_command(task: dict) -> list[str]:
    command = [sys.executable, str(ROOT / "services/ingestion/src/worker.py")]
    if task["type"] == "shard_refresh":
        shard = int(task["shardIndex"])
        if shard not in range(5):
            raise ValueError("Invalid shard")
        return command + ["--once", "--shard", str(shard)]
    return command + [FLAGS[task["type"]]]


def run_tick(manager=None, *, budget=2100, task_timeout=900,
             run=subprocess.run, clock=time.monotonic, output=None) -> dict:
    manager = manager or ScheduleManager()
    output = output or ROOT / "work/runs/ci-refresh-summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    tasks = manager.get_pending_tasks()
    # Status checks get first use of the bounded runner; the existing queue
    # determines the other tasks, including today's ordinary daily shard.
    tasks.sort(key=lambda task: task["type"] != "job_recheck")
    deadline = clock() + budget
    report = {"tasks": [], "deferred": [], "failed": False}
    for task in tasks:
        remaining = int(deadline - clock())
        if remaining < 30:
            report["deferred"].append(task)
            continue
        kind = task["type"]
        error = None
        try:
            result = run(task_command(task), cwd=ROOT, timeout=min(task_timeout, remaining), check=False)
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
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(ScheduleManager().get_pending_tasks(), indent=2))
    else:
        result = run_tick()
        print(json.dumps(result, indent=2))
        sys.exit(1 if result["failed"] or result["deferred"] else 0)

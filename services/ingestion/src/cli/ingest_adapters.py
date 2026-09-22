"""Harvest every HTML/job adapter source under a time budget.

Use this instead of the 35-minute full refresh when you only need identities
written to Supabase. Fixture mode is the default; pass --live for network.

Each source runs in its own subprocess so a slow or hanging source is killed at
its slice deadline. Earlier committed sources survive, the rest of the pass
continues, and the killed source stays due for the next wake.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.jobs import adapter_for, adapter_sources  # noqa: E402

CURSOR_PATH = ROOT / "work" / "runs" / "ingest-adapters.json"
WORKER = Path(__file__).resolve().parent / "adapter_source_worker.py"


def load_previous_report(path: Path = CURSOR_PATH) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def prefer_ids_from_env() -> list[str]:
    raw = os.environ.get("ADAPTER_PREFER_IDS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def prioritize_sources(
    sources: list[dict],
    previous: dict | None = None,
    prefer_ids: list[str] | None = None,
) -> list[dict]:
    by_id = {str(item.get("id")): item for item in sources if item.get("id")}
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for ident in list((previous or {}).get("deferred") or []) + list(prefer_ids or []):
        if ident in by_id and ident not in seen:
            ordered_ids.append(ident)
            seen.add(ident)
    for item in sources:
        ident = str(item.get("id") or "")
        if ident and ident not in seen:
            ordered_ids.append(ident)
            seen.add(ident)
    return [by_id[ident] for ident in ordered_ids]


def slice_timeout(remaining: float, *, source_timeout: int = 300, min_slice: int = 20) -> int:
    """A source gets the smaller of the remaining budget and its own cap.

    The minimum slice means a source already running near the deadline is still
    bounded, and the pass never waits unboundedly on one adapter.
    """
    return max(min_slice, min(int(remaining), source_timeout))


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def run_source_in_worker(
    worker_command: list[str],
    source: dict,
    *,
    plan_path: Path,
    out_path: Path,
    timeout: int,
    run_process,
    env: dict[str, str] | None = None,
    cwd: Any = None,
) -> dict[str, Any]:
    cmd = [
        *worker_command,
        "--source-id", str(source.get("id") or ""),
        "--previous", str(plan_path),
        "--out", str(out_path),
    ]
    try:
        result = run_process(cmd, cwd=cwd, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "budget-timeout"}
    except OSError as exc:
        return {"ok": False, "error": f"worker-spawn:{type(exc).__name__}"}
    if getattr(result, "returncode", 0) != 0:
        return {"ok": False, "error": f"worker-exit:{getattr(result, 'returncode', '?')}"}
    payload = _load_json(out_path, None)
    if not isinstance(payload, dict):
        return {"ok": False, "error": "worker-output-unreadable"}
    return {"ok": True, "payload": payload}


def run_adapter_pass(
    sources: list[dict],
    *,
    fetch_page=None,
    fetch_for=None,
    previous: dict,
    store=None,
    budget_seconds: int = 480,
    clock=time.monotonic,
    harvest=None,
    worker_command: list[str] | None = None,
    run_process=None,
    source_timeout: int = 300,
    env: dict[str, str] | None = None,
    cwd: Any = None,
    slice_dir: Path | None = None,
) -> dict:
    from engine.adapter_harvest import harvest_adapter_source

    harvest = harvest or harvest_adapter_source
    deadline = clock() + max(30, budget_seconds)
    started = []
    deferred = []
    snapshot = previous
    slices = slice_dir or (ROOT / "work" / "runs" / "adapter-slices")
    if worker_command:
        slices.mkdir(parents=True, exist_ok=True)
    for source in sources:
        remaining = deadline - clock()
        if remaining < 20:
            deferred.append(source.get("id"))
            continue
        page = fetch_for(source) if fetch_for is not None else fetch_page
        ident = str(source.get("id") or "")
        if worker_command is not None:
            plan_path = slices / f"{ident}-prev.json"
            out_path = slices / f"{ident}-out.json"
            _atomic_json(plan_path, snapshot)
            timeout = slice_timeout(remaining, source_timeout=source_timeout)
            print(
                f"ingest_adapters: start {ident} remaining_s={int(remaining)} timeout_s={timeout}",
                flush=True,
            )
            begun = clock()
            outcome = run_source_in_worker(
                worker_command,
                source,
                plan_path=plan_path,
                out_path=out_path,
                timeout=timeout,
                run_process=run_process or subprocess.run,
                env=env,
                cwd=cwd,
            )
            elapsed = int(clock() - begun)
            if outcome.get("ok") and outcome["payload"].get("complete"):
                snapshot = outcome["payload"].get("snapshot") or snapshot
            if outcome.get("ok"):
                payload = outcome["payload"]
                status = payload["run"].get("status", "succeeded")
                listed = payload.get("listed", 0)
                parsed = payload.get("parsed", 0)
                candidates = payload.get("candidates", 0)
                complete = bool(payload.get("complete"))
            else:
                status = outcome["error"]
                listed = parsed = candidates = 0
                complete = False
            started.append(
                {
                    "sourceId": ident,
                    "status": status,
                    "complete": complete,
                    "listed": listed,
                    "parsed": parsed,
                    "candidates": candidates,
                    "elapsed_s": elapsed,
                }
            )
            print(
                f"ingest_adapters: finish {ident} elapsed_s={elapsed} status={status}",
                flush=True,
            )
            continue
        print(f"ingest_adapters: start {ident} remaining_s={int(remaining)}", flush=True)
        begun = clock()
        result = harvest(source, fetch_page=page, previous=snapshot, store=store)
        snapshot = result.get("snapshot") or snapshot
        elapsed = int(clock() - begun)
        started.append(
            {
                "sourceId": source.get("id"),
                "status": result["run"]["status"],
                "complete": result.get("complete"),
                "listed": result["completeness"].listed_count,
                "parsed": result["completeness"].parsed_count,
                "candidates": len(result.get("candidates") or []),
                "elapsed_s": elapsed,
            }
        )
        print(
            f"ingest_adapters: finish {source.get('id')} elapsed_s={elapsed} "
            f"status={result['run']['status']}",
            flush=True,
        )
    return {
        "started": started,
        "deferred": deferred,
        "snapshot": snapshot,
        "failed": any(item.get("status") != "succeeded" for item in started),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget-seconds", type=int, default=480)
    parser.add_argument("--source-timeout", type=int, default=300)
    args = parser.parse_args(argv)
    sources = prioritize_sources(
        adapter_sources(),
        previous=load_previous_report(),
        prefer_ids=prefer_ids_from_env(),
    )
    if not args.live:
        print(
            json.dumps(
                {
                    "error": "live-flag-required-for-network",
                    "adapterSourceCount": len(sources),
                    "sourceIds": [item["id"] for item in sources],
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        return 2
    from engine.runtime import require_http_fetcher, write_runtime_report
    from engine.transport import live_fetcher
    from storage.postgres import persist_enabled, store_from_env
    from storage.retention import prune_ingest_history
    from worker import JOBS_OUT, atomic_write, load_json

    os.environ.setdefault("SCRAPLING_REQUIRED", "1")
    os.environ.setdefault("SUPABASE_WRITE", "1")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    runtime = write_runtime_report(ROOT / "work" / "runs" / "scrapling-runtime.json")
    require_http_fetcher(runtime)
    store = store_from_env() if persist_enabled() else None
    previous = load_json(JOBS_OUT)
    worker_env = os.environ.copy()
    worker_env.setdefault("PLAYWRIGHT_LAUNCH_TIMEOUT", "30000")
    try:
        report = run_adapter_pass(
            sources,
            fetch_for=live_fetcher,
            previous=previous,
            store=store,
            budget_seconds=args.budget_seconds,
            worker_command=[sys.executable, "-u", str(WORKER)],
            run_process=subprocess.run,
            source_timeout=args.source_timeout,
            env=worker_env,
            cwd=ROOT,
        )
        atomic_write(JOBS_OUT, report["snapshot"])
        if store is not None:
            report["retention"] = prune_ingest_history(store)
    finally:
        closer = getattr(store, "close", None)
        if callable(closer):
            closer()
    out = ROOT / "work" / "runs" / "ingest-adapters.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {key: value for key, value in report.items() if key != "snapshot"}
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 1 if report.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
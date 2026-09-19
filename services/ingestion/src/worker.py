"""Daily 1/5 refresh worker.

Each UTC day harvests one stable fifth of register HEIs (programmes, apply
portals) and the jobs whose employer is in that fifth. Five consecutive days
cover the full set (120 hours). Network failures are not stored as closed.
Does not write immutable snapshots. Verified closures may activate the
safety-status overlay under data/published/safety/.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
POLICY = ROOT / "config" / "refresh-policy.json"
REGISTRY = ROOT / "data" / "sources" / "registry.json"
RUNS = ROOT / "work" / "runs"
LOCK = RUNS / "refresh.lock"
STATE = RUNS / "refresh-state.json"
SHARD_ASSIGNMENTS = RUNS / "shard-assignments.json"
JOBS_OUT = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
PORTALS_OUT = ROOT / "data" / "sources" / "admissions" / "apply-portals.json"
STUDYIN_OUT = ROOT / "data" / "sources" / "admissions" / "studyin-programmes.json"
CZU_PROGRAMMES_OUT = ROOT / "data" / "sources" / "admissions" / "czu-english-programmes.json"
CZU_CZECH_PROGRAMMES_OUT = ROOT / "data" / "sources" / "admissions" / "czu-czech-programmes.json"
CZU_DOCTORAL_PROGRAMMES_OUT = ROOT / "data" / "sources" / "admissions" / "czu-doctoral-programmes.json"
SCHEDULE_STATE = RUNS / "schedule-state.json"

from schedule import ScheduleManager  # noqa: E402
from file_lock import FileMutex, LockUnavailable, lock_is_held, read_lock_metadata  # noqa: E402
from refresh_shards import (  # noqa: E402
    SHARD_COUNT,
    assign_shards_stable,
    merge_sharded_jobs,
    merge_sharded_portals,
    next_utc_midnight,
    shard_index_for_date,
    units_for_shard,
    utc_today,
)


def load_registry() -> list[dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def load_policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def network_failure_means_closed(status_code: int | None, timeout: bool) -> bool:
    if timeout:
        return False
    if status_code in {403, 404, 429, 500, 502, 503}:
        return False
    return False


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Windows virus scanners and indexers can briefly hold the destination
    # between the write and replace operations. Retry only that transient
    # sharing failure; the unique temporary file remains a valid checkpoint.
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1 * (attempt + 1))


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        except AttributeError:
            return False
        return True


class RunLock:
    def __init__(self, lock_path: Path | None = None) -> None:
        self.lock_path = lock_path or LOCK
        self._mutex: FileMutex | None = None

    def __enter__(self) -> "RunLock":
        mutex = FileMutex(self.lock_path, {"operation": "catalogue-candidate-write"})
        try:
            mutex.__enter__()
        except LockUnavailable as exc:
            owner = read_lock_metadata(self.lock_path)
            owner_text = f" pid={owner.get('pid')}" if owner.get("pid") else ""
            raise SystemExit(f"refresh already running{owner_text}") from exc
        self._mutex = mutex
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._mutex is not None:
            self._mutex.__exit__(exc_type, exc, tb)
            self._mutex = None


def baseline_schools() -> list[dict]:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    return list(payload.get("institutions") or [])


def load_shard_assignments(path: Path | None = None) -> dict[str, int]:
    payload = load_json(path or SHARD_ASSIGNMENTS)
    raw = payload.get("assignments") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return {}
    mapping: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, int):
            mapping[key] = value
    return mapping


def save_shard_assignments(mapping: dict[str, int], path: Path | None = None) -> None:
    atomic_write(
        path or SHARD_ASSIGNMENTS,
        {
            "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "assignments": mapping,
        },
    )


def plan_for_day(
    day,
    schools: list[dict] | None = None,
    shard: int | None = None,
    *,
    assignments_path: Path | None = None,
) -> dict:
    schools = schools if schools is not None else baseline_schools()
    ids = [item["id"] for item in schools]
    shard_idx = shard % SHARD_COUNT if shard is not None else shard_index_for_date(day)
    path = assignments_path or SHARD_ASSIGNMENTS
    previous = load_shard_assignments(path)
    mapping = assign_shards_stable(ids, previous)
    if mapping != previous:
        save_shard_assignments(mapping, path)
    selected_ids = set(units_for_shard(ids, shard_idx, previous=mapping))
    selected = [item for item in schools if item["id"] in selected_ids]
    from harvest_nine_hei_jobs import VERIFIED_CANDIDATES

    jobs = [item for item in VERIFIED_CANDIDATES if item["employerId"] in selected_ids]
    return {
        "date": day.isoformat(),
        "shard": shard_idx,
        "shardCount": SHARD_COUNT,
        "institutionIds": [item["id"] for item in selected],
        "schools": selected,
        "jobs": jobs,
        "jobIds": [item["id"] for item in jobs],
        "counts": {
            "institutions": len(selected),
            "jobs": len(jobs),
            "allInstitutions": len(schools),
        },
    }


def harvest_programmes(schools: list[dict], force: bool) -> list[dict]:
    from harvest_cscse24_programmes import SLEEP_SECONDS, harvest_one
    from parse_msmt_programmes import csv_for_code, parse_school_csv, write_school_programmes

    log = []
    for index, school in enumerate(schools):
        if index:
            time.sleep(SLEEP_SECONDS)
        result = harvest_one(school, force)
        if result["status"] not in {"ok", "skipped_existing"}:
            time.sleep(SLEEP_SECONDS)
            retry = harvest_one(school, True)
            retry["retriedFrom"] = result["status"]
            result = retry
        path = csv_for_code(school["msmtCode"])
        if result["status"] in {"ok", "skipped_existing"} and path is not None:
            records = parse_school_csv(path)
            if records:
                write_school_programmes(school["msmtCode"], school["id"], school["officialName"], records)
                result["parsedProgrammes"] = len(records)
            else:
                result["parsedProgrammes"] = 0
        log.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return log


def harvest_jobs(
    candidates: list[dict],
    employer_ids: set[str] | None = None,
    *,
    fetch_page=None,
    jobs_path: Path | None = None,
    registry: list[dict] | None = None,
) -> dict:
    from harvest_nine_hei_jobs import harvest_with_registered_discovery
    from engine.transport import live_fetcher

    target = jobs_path or JOBS_OUT
    injected_fetch = fetch_page
    if fetch_page is None:
        fetch_page = live_fetcher(registry[0] if registry else {})
    # Production discovery checkpoints each source. A killed slow source must
    # not discard candidates already fetched from unrelated universities.
    if registry is None and not candidates and employer_ids is None:
        from harvest_nine_hei_jobs import load_registered_job_sources
        sources = load_registered_job_sources()
        aggregate = {"runKind": "partial_checkpoint", "expectedSourceIds": [s["id"] for s in sources],
                     "completeSourceIds": [], "deferredSourceIds": [], "attempts": [],
                     "discoveredCount": 0, "hostCooldowns": {}}
        processed = set()
        skipped = []
        for source in sources:
            page = injected_fetch if injected_fetch is not None else live_fetcher(source)
            part = harvest_jobs([], fetch_page=page, jobs_path=target, registry=[source])
            discovery = part.get("discovery") or {}
            for key in ("completeSourceIds", "deferredSourceIds", "attempts"):
                aggregate[key].extend(discovery.get(key) or [])
            aggregate["discoveredCount"] += int(discovery.get("discoveredCount") or 0)
            aggregate["hostCooldowns"].update(discovery.get("hostCooldowns") or {})
            processed.update(part.get("processedCandidateIds") or [])
            skipped.extend(part.get("skipped") or [])
            checkpoint = load_json(target)
            checkpoint["discovery"] = aggregate
            atomic_write(target, checkpoint)
        aggregate["runKind"] = "all_registered_sources"
        checkpoint = load_json(target)
        checkpoint["discovery"] = aggregate
        atomic_write(target, checkpoint)
        return {"counts": checkpoint.get("counts"), "skipped": skipped,
                "discovery": aggregate, "processedCandidateIds": sorted(processed)}
    previous = load_json(target)
    shard_result = harvest_with_registered_discovery(
        candidates,
        fetch_page,
        previous,
        employer_ids=employer_ids,
        registry=registry,
    )
    processed_ids = set(shard_result.get("processedCandidateIds") or []) | {item["id"] for item in candidates}
    merged = merge_sharded_jobs(previous, shard_result, processed_ids)
    atomic_write(target, merged)
    discovery = shard_result.get("discovery") or {}
    from storage.persist import persist_job_harvest

    supabase = persist_job_harvest(
        expected_source_ids=list(discovery.get("expectedSourceIds") or []),
        complete_source_ids=list(discovery.get("completeSourceIds") or []),
        deferred_source_ids=list(discovery.get("deferredSourceIds") or []),
        attempts=list(discovery.get("attempts") or []),
        jobs=list(merged.get("jobs") or []),
    )
    discovery = {**discovery, "supabase": supabase}
    merged["discovery"] = discovery
    atomic_write(target, merged)
    return {
        "counts": merged.get("counts"),
        "skipped": shard_result.get("skipped") or [],
        "discovery": discovery,
        "processedCandidateIds": sorted(processed_ids),
        "supabase": supabase,
    }


def discover_all_jobs(
    fetch_page=None,
    now: datetime | None = None,
    *,
    jobs_path: Path | None = None,
    registry: list[dict] | None = None,
    schedule_manager: ScheduleManager | None = None,
    use_lock: bool = True,
) -> dict:
    """Refresh every registered official vacancy listing independently.

    Existing seeded jobs are checked by the hourly status task.  This task
    starts with no seed constants so its four-hour cadence measures genuine
    list discovery and does not depend on the five-day institution shards.
    """
    current = _aware_utc(now or datetime.now(timezone.utc))
    manager = schedule_manager or ScheduleManager()
    context = RunLock() if use_lock else nullcontext()
    metrics = {"discoveredJobsCount": 0, "checkedSourcesCount": 0}
    try:
        with context:
            from harvest_nine_hei_jobs import load_host_cooldowns

            state = manager.load_state(current)
            load_host_cooldowns((state.get("jobDiscovery") or {}).get("hostCooldowns") or {}, current)
            result = harvest_jobs(
                [],
                employer_ids=None,
                fetch_page=fetch_page,
                jobs_path=jobs_path,
                registry=registry,
            )
        discovery = result.get("discovery") or {}
        attempts = discovery.get("attempts") or []
        source_results: dict[str, list[dict]] = {}
        for attempt in attempts:
            source_id = str(attempt.get("sourceId") or "unknown")
            source_results.setdefault(source_id, []).append(attempt)
        metrics = {
            "discoveredJobsCount": int(discovery.get("discoveredCount") or 0),
            "checkedSourcesCount": len(source_results),
            "expectedSourceCount": len(discovery.get("expectedSourceIds") or []),
            "completeSourceCount": len(discovery.get("completeSourceIds") or []),
            "deferredSourceCount": len(discovery.get("deferredSourceIds") or []),
            "runKind": discovery.get("runKind") or "all_registered_sources",
            "hostCooldowns": discovery.get("hostCooldowns") or {},
        }
        failed_sources = []
        for source_id, source_attempts in source_results.items():
            succeeded = bool(source_attempts) and all(bool(item.get("ok")) for item in source_attempts)
            error = None if succeeded else "; ".join(
                str(item.get("reason") or f"http-{item.get('status')}")
                for item in source_attempts
                if not item.get("ok")
            )[:500]
            retry_at = next((item.get("retryAt") for item in source_attempts if item.get("retryAt")), None)
            manager.record_source_result(
                f"job-discovery:{source_id}",
                succeeded=succeeded,
                error=error,
                now=current,
                retry_at=retry_at,
            )
            if not succeeded:
                failed_sources.append(source_id)
        result["status"] = "succeeded" if not failed_sources else "partial"
        result["failedSources"] = failed_sources
        if failed_sources:
            manager.record_volatile_failure(
                "job_discovery",
                f"{len(failed_sources)}/{len(source_results)} registered job sources failed",
                metrics=metrics,
                now=current,
            )
        else:
            # A86: an all-source success timestamp requires proof, not just an
            # empty failure list over the sources that happened to answer.
            # Every expected source must be observed, accounted as complete,
            # with nothing deferred.
            expected_ids = list(discovery.get("expectedSourceIds") or [])
            complete_ids = set(discovery.get("completeSourceIds") or [])
            deferred_ids = set(discovery.get("deferredSourceIds") or [])
            attempted_ids = set(source_results)
            unaccounted_ids = [
                source_id for source_id in expected_ids if source_id not in attempted_ids
            ]
            result["unaccountedSourceIds"] = unaccounted_ids
            all_source_complete = (
                (discovery.get("runKind") or "all_registered_sources") == "all_registered_sources"
                and bool(expected_ids)
                and set(expected_ids) == complete_ids
                and not deferred_ids
                and not unaccounted_ids
            )
            result["allSourceComplete"] = all_source_complete
            if all_source_complete:
                metrics["lastAllSourceSuccessAt"] = current.strftime("%Y-%m-%dT%H:%M:%SZ")
            manager.record_volatile_success(
                "job_discovery", metrics=metrics, now=current
            )
        return result
    except Exception as exc:
        manager.record_source_result(
            "job-discovery:run",
            succeeded=False,
            error=str(exc),
            now=current,
        )
        manager.record_volatile_failure(
            "job_discovery", str(exc), metrics=metrics, now=current
        )
        raise


def refresh_programme_availability(
    fetch_page=None,
    now: datetime | None = None,
    *,
    output_path: Path | None = None,
    schedule_manager: ScheduleManager | None = None,
    use_lock: bool = True,
) -> dict:
    """Refresh the complete DZS programme candidate catalogue atomically."""
    from harvest_studyin_programmes import harvest_catalog

    current = _aware_utc(now or datetime.now(timezone.utc))
    manager = schedule_manager or ScheduleManager()
    target = output_path or STUDYIN_OUT
    context = RunLock() if use_lock else nullcontext()
    metrics = {
        "programmesCount": 0,
        "institutionsCount": 0,
        "openApplicationsCount": 0,
    }
    try:
        with context:
            kwargs = {"now": current}
            if fetch_page is not None:
                kwargs["fetch_page"] = fetch_page
            payload = harvest_catalog(**kwargs)
            atomic_write(target, payload)
            RUNS.mkdir(parents=True, exist_ok=True)
            atomic_write(
                RUNS / "studyin-programmes-latest.json",
                {
                    "generatedAt": payload["generatedAt"],
                    "counts": payload["counts"],
                    "coverage": payload["coverage"],
                    "output": str(target.relative_to(ROOT)).replace("\\", "/")
                    if target.is_relative_to(ROOT)
                    else str(target),
                },
            )
        counts = payload.get("counts") or {}
        metrics = {
            "programmesCount": int(counts.get("programmes") or 0),
            "institutionsCount": int(counts.get("institutions") or 0),
            "openApplicationsCount": int(counts.get("openApplications") or 0),
        }
        manager.record_source_result(
            "programme-availability:studyin",
            succeeded=True,
            now=current,
        )
        manager.record_volatile_success(
            "programme_availability", metrics=metrics, now=current
        )
        return {
            "status": "succeeded",
            "generatedAt": payload["generatedAt"],
            "counts": counts,
            "published": False,
            "output": str(target),
        }
    except Exception as exc:
        manager.record_source_result(
            "programme-availability:studyin",
            succeeded=False,
            error=str(exc),
            now=current,
        )
        manager.record_volatile_failure(
            "programme_availability", str(exc), metrics=metrics, now=current
        )
        raise


def refresh_czu_programme_availability(
    fetch_page=None,
    now: datetime | None = None,
    *,
    output_path: Path | None = None,
    schedule_manager: ScheduleManager | None = None,
    use_lock: bool = True,
    sleep=None,
    delay_seconds: float | None = None,
    raw_dir: Path | None = None,
) -> dict:
    """Refresh CZU's complete official English bachelor/master candidate source."""
    from harvest_czu_programmes import harvest_catalog

    current = _aware_utc(now or datetime.now(timezone.utc))
    manager = schedule_manager or ScheduleManager()
    target = output_path or CZU_PROGRAMMES_OUT
    context = RunLock() if use_lock else nullcontext()
    metrics = {
        "programmesCount": 0,
        "detailsWithCompleteWindowCount": 0,
        "openApplicationsCount": 0,
        "upcomingApplicationsCount": 0,
        "openPageReportedCount": 0,
        "availabilityCrosscheck": "unknown",
    }
    try:
        with context:
            kwargs = {"now": current}
            if fetch_page is not None:
                kwargs["fetch_page"] = fetch_page
            if sleep is not None:
                kwargs["sleep"] = sleep
            if delay_seconds is not None:
                kwargs["delay_seconds"] = delay_seconds
            if raw_dir is not None:
                kwargs["raw_dir"] = raw_dir
            payload = harvest_catalog(**kwargs)
            atomic_write(target, payload)
            RUNS.mkdir(parents=True, exist_ok=True)
            atomic_write(
                RUNS / "czu-programmes-latest.json",
                {
                    "generatedAt": payload["generatedAt"],
                    "counts": payload["counts"],
                    "coverage": payload["coverage"],
                    "output": str(target.relative_to(ROOT)).replace("\\", "/")
                    if target.is_relative_to(ROOT)
                    else str(target),
                },
            )
        counts = payload.get("counts") or {}
        coverage = payload.get("coverage") or {}
        metrics = {
            "programmesCount": int(counts.get("programmes") or 0),
            "detailsWithCompleteWindowCount": int(counts.get("detailsWithCompleteWindow") or 0),
            "openApplicationsCount": int(counts.get("openByDetailDates") or 0),
            "upcomingApplicationsCount": int(counts.get("upcomingByDetailDates") or 0),
            "openPageReportedCount": int(counts.get("openPageReported") or 0),
            "availabilityCrosscheck": coverage.get("availabilityCrosscheck") or "unknown",
        }
        manager.record_source_result(
            "programme-availability:czu-english",
            succeeded=True,
            now=current,
        )
        manager.record_volatile_success(
            "czu_programme_availability", metrics=metrics, now=current
        )
        return {
            "status": "succeeded",
            "generatedAt": payload["generatedAt"],
            "counts": counts,
            "coverage": coverage,
            "published": False,
            "output": str(target),
        }
    except Exception as exc:
        manager.record_source_result(
            "programme-availability:czu-english",
            succeeded=False,
            error=str(exc),
            now=current,
        )
        manager.record_volatile_failure(
            "czu_programme_availability", str(exc), metrics=metrics, now=current
        )
        raise


def refresh_czu_czech_programme_availability(
    fetch_page=None,
    now: datetime | None = None,
    *,
    output_path: Path | None = None,
    schedule_manager: ScheduleManager | None = None,
    use_lock: bool = True,
    sleep=None,
    delay_seconds: float | None = None,
    raw_dir: Path | None = None,
    english_payload: dict | None = None,
) -> dict:
    """Refresh CZU's Czech-facing bachelor/master sitemap and all details."""
    from harvest_czu_czech_programmes import harvest_catalog

    current = _aware_utc(now or datetime.now(timezone.utc))
    manager = schedule_manager or ScheduleManager()
    target = output_path or CZU_CZECH_PROGRAMMES_OUT
    context = RunLock() if use_lock else nullcontext()
    metrics = {
        "programmesCount": 0,
        "czechTaughtProgrammesCount": 0,
        "englishTaughtProgrammesCount": 0,
        "detailsWithCompleteWindowCount": 0,
        "openApplicationsCount": 0,
        "upcomingApplicationsCount": 0,
        "englishSourceCrosscheck": "unknown",
    }
    try:
        with context:
            kwargs = {"now": current}
            if fetch_page is not None:
                kwargs["fetch_page"] = fetch_page
            if sleep is not None:
                kwargs["sleep"] = sleep
            if delay_seconds is not None:
                kwargs["delay_seconds"] = delay_seconds
            if raw_dir is not None:
                kwargs["raw_dir"] = raw_dir
            kwargs["english_payload"] = (
                english_payload
                if english_payload is not None
                else load_json(CZU_PROGRAMMES_OUT)
            )
            payload = harvest_catalog(**kwargs)
            atomic_write(target, payload)
            RUNS.mkdir(parents=True, exist_ok=True)
            atomic_write(
                RUNS / "czu-czech-programmes-latest.json",
                {
                    "generatedAt": payload["generatedAt"],
                    "counts": payload["counts"],
                    "coverage": payload["coverage"],
                    "output": str(target.relative_to(ROOT)).replace("\\", "/")
                    if target.is_relative_to(ROOT)
                    else str(target),
                },
            )
        counts = payload.get("counts") or {}
        coverage = payload.get("coverage") or {}
        languages = counts.get("teachingLanguages") or {}
        crosscheck = coverage.get("englishSourceCrosscheck") or {}
        metrics = {
            "programmesCount": int(counts.get("programmes") or 0),
            "czechTaughtProgrammesCount": int(languages.get("cs") or 0),
            "englishTaughtProgrammesCount": int(languages.get("en") or 0),
            "detailsWithCompleteWindowCount": int(counts.get("detailsWithCompleteWindow") or 0),
            "openApplicationsCount": int(counts.get("openByDetailDates") or 0),
            "upcomingApplicationsCount": int(counts.get("upcomingByDetailDates") or 0),
            "englishSourceCrosscheck": crosscheck.get("status") or "unknown",
        }
        manager.record_source_result(
            "programme-availability:czu-czech-portal",
            succeeded=True,
            now=current,
        )
        manager.record_volatile_success(
            "czu_czech_programme_availability", metrics=metrics, now=current
        )
        return {
            "status": "succeeded",
            "generatedAt": payload["generatedAt"],
            "counts": counts,
            "coverage": coverage,
            "published": False,
            "output": str(target),
        }
    except Exception as exc:
        manager.record_source_result(
            "programme-availability:czu-czech-portal",
            succeeded=False,
            error=str(exc),
            now=current,
        )
        manager.record_volatile_failure(
            "czu_czech_programme_availability", str(exc), metrics=metrics, now=current
        )
        raise


def refresh_czu_doctoral_programme_availability(
    fetch_asset=None,
    now: datetime | None = None,
    *,
    output_path: Path | None = None,
    schedule_manager: ScheduleManager | None = None,
    use_lock: bool = True,
    sleep=None,
    delay_seconds: float | None = None,
    raw_dir: Path | None = None,
    inventory_payload: dict | None = None,
) -> dict:
    """Refresh CZU's six-faculty doctoral programme/window cross-check."""
    from harvest_czu_doctoral_programmes import harvest_catalog

    current = _aware_utc(now or datetime.now(timezone.utc))
    manager = schedule_manager or ScheduleManager()
    target = output_path or CZU_DOCTORAL_PROGRAMMES_OUT
    context = RunLock() if use_lock else nullcontext()
    metrics = {
        "programmesCount": 0,
        "facultiesCount": 0,
        "czechTaughtProgrammesCount": 0,
        "englishTaughtProgrammesCount": 0,
        "matchedProgrammesCount": 0,
        "openApplicationsCount": 0,
        "upcomingApplicationsCount": 0,
        "closedApplicationsCount": 0,
        "awaitingNextAcademicYearWindowCount": 0,
    }
    try:
        with context:
            kwargs = {"now": current}
            if fetch_asset is not None:
                kwargs["fetch_asset"] = fetch_asset
            if sleep is not None:
                kwargs["sleep"] = sleep
            if delay_seconds is not None:
                kwargs["delay_seconds"] = delay_seconds
            if raw_dir is not None:
                kwargs["raw_dir"] = raw_dir
            if inventory_payload is not None:
                kwargs["inventory_payload"] = inventory_payload
            payload = harvest_catalog(**kwargs)
            atomic_write(target, payload)
            RUNS.mkdir(parents=True, exist_ok=True)
            atomic_write(
                RUNS / "czu-doctoral-programmes-latest.json",
                {
                    "generatedAt": payload["generatedAt"],
                    "counts": payload["counts"],
                    "coverage": payload["coverage"],
                    "output": str(target.relative_to(ROOT)).replace("\\", "/")
                    if target.is_relative_to(ROOT)
                    else str(target),
                },
            )
        counts = payload.get("counts") or {}
        languages = counts.get("teachingLanguages") or {}
        metrics = {
            "programmesCount": int(counts.get("programmes") or 0),
            "facultiesCount": int(counts.get("faculties") or 0),
            "czechTaughtProgrammesCount": int(languages.get("cs") or 0),
            "englishTaughtProgrammesCount": int(languages.get("en") or 0),
            "matchedProgrammesCount": int(counts.get("matchedToFacultyAdmissionEvidence") or 0),
            "openApplicationsCount": int(counts.get("openByOfficialDates") or 0),
            "upcomingApplicationsCount": int(counts.get("upcomingByOfficialDates") or 0),
            "closedApplicationsCount": int(counts.get("closedByOfficialDates") or 0),
            "awaitingNextAcademicYearWindowCount": int(
                counts.get("awaitingNextAcademicYearWindow") or 0
            ),
        }
        manager.record_source_result(
            "programme-availability:czu-doctoral-faculties",
            succeeded=True,
            now=current,
        )
        manager.record_volatile_success(
            "czu_doctoral_programme_availability", metrics=metrics, now=current
        )
        return {
            "status": "succeeded",
            "generatedAt": payload["generatedAt"],
            "counts": counts,
            "coverage": payload.get("coverage") or {},
            "published": False,
            "output": str(target),
        }
    except Exception as exc:
        manager.record_source_result(
            "programme-availability:czu-doctoral-faculties",
            succeeded=False,
            error=str(exc),
            now=current,
        )
        manager.record_volatile_failure(
            "czu_doctoral_programme_availability",
            str(exc),
            metrics=metrics,
            now=current,
        )
        raise


def harvest_portals(schools: list[dict], all_ids: list[str]) -> dict:
    from harvest_apply_portals import harvest_rows

    previous = load_json(PORTALS_OUT)
    rows = harvest_rows(schools)
    merged = merge_sharded_portals(previous, rows, all_ids)
    merged["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    merged["dataClass"] = previous.get("dataClass") or "official_admissions_extract"
    merged["catalogKind"] = previous.get("catalogKind") or "tracer_not_published"
    merged["note"] = previous.get("note") or (
        "Verified official application / admissions URLs. A working portal is not an open window."
    )
    atomic_write(PORTALS_OUT, merged)
    return {"counts": merged.get("counts") or {}, "attempts": rows}


def rebuild_inventory() -> dict:
    from build_nine_hei_inventory import build_from_register, write_compact

    payload = build_from_register()
    source_path = write_compact(payload)
    return {
        "programmes": payload["counts"]["programmes"],
        "schools": payload["counts"]["schools"],
        "source": str(source_path),
    }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _window_deadline_passed(window: dict, now: datetime) -> bool:
    from harvest_nine_hei_jobs import parse_date

    closes_value = window.get("closesAt")
    if not isinstance(closes_value, str) or not closes_value.strip():
        return False
    precision = window.get("datePrecision")
    timezone_name = window.get("timezone") or "Europe/Prague"
    try:
        source_zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        source_zone = timezone.utc

    if precision == "datetime" or "T" in closes_value:
        try:
            deadline = datetime.fromisoformat(closes_value.replace("Z", "+00:00"))
        except ValueError:
            return False
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=source_zone)
        return _aware_utc(now) > deadline.astimezone(timezone.utc)

    deadline_date = parse_date(closes_value)
    if deadline_date is None:
        return False
    return _aware_utc(now).astimezone(source_zone).date() > deadline_date


def _recheck_open_jobs_unlocked(
    fetch_page,
    now: datetime,
    jobs_path: Path,
    schedule_manager: ScheduleManager,
    post_json=None,
    safety_dir: Path | None = None,
) -> dict:
    from harvest_nine_hei_jobs import (
        LMC_GRAPHQL_ENDPOINT,
        SLEEP,
        _lmc_detail_payload,
        _lmc_job_ad,
        page_is_closed,
        parse_lmc_widget_config,
        request_json,
        visible_text,
    )
    from urllib.parse import parse_qs, urlsplit

    from engine.transport import live_fetcher

    live_request = fetch_page is None
    fetch_fn = fetch_page or live_fetcher()
    post_fn = post_json or request_json
    response_cache: dict[str, tuple[int, str]] = {}
    post_response_cache: dict[str, tuple[int, str]] = {}
    lmc_config_cache: dict[str, dict | None] = {}
    source_by_id = {
        str(source.get("id")): source
        for source in load_registry()
        if isinstance(source, dict) and source.get("id")
    }

    def cached_get(url: str) -> tuple[int, str]:
        if url not in response_cache:
            if response_cache and live_request and SLEEP:
                time.sleep(SLEEP)
            response_cache[url] = fetch_fn(url)
        return response_cache[url]

    def cached_post(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, str]:
        key = json.dumps([url, payload, headers], ensure_ascii=False, sort_keys=True)
        if key not in post_response_cache:
            if post_response_cache and post_json is None and SLEEP:
                time.sleep(SLEEP)
            post_response_cache[key] = post_fn(url, payload, headers)
        return post_response_cache[key]
    previous = load_json(jobs_path)
    jobs = previous.get("jobs") or []
    raw_windows = previous.get("windows") or []
    windows_by_owner: dict[str, list[dict]] = {}
    updated_windows: list[dict] = []
    for item in raw_windows:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        owner_id = copied.get("ownerId")
        if isinstance(owner_id, str) and owner_id:
            windows_by_owner.setdefault(owner_id, []).append(copied)
        updated_windows.append(copied)

    checked_count = 0
    http_success_count = 0
    failure_count = 0
    closed_count = 0
    now_text = _aware_utc(now).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated_jobs = []

    for job in jobs:
        if not isinstance(job, dict) or not job.get("id"):
            continue
        if (
            job.get("visibility") == "archived"
            or job.get("wholeOpportunityClosed")
            or job.get("lifecycleStatus") in {"closed", "expired", "unavailable"}
        ):
            updated_jobs.append(job)
            continue

        checked_count += 1
        job_copy = dict(job)
        job_windows = windows_by_owner.get(job["id"], [])
        expired_any = False
        for window in job_windows:
            if window.get("status") != "closed" and _window_deadline_passed(window, now):
                window["status"] = "closed"
                window["closedReason"] = "deadline_expired"
                window["closedAt"] = now_text
                expired_any = True

        all_windows_closed = bool(job_windows) and all(window.get("status") == "closed" for window in job_windows)
        if expired_any:
            job_copy["lastAttemptAt"] = now_text
            job_copy["lastAttemptReason"] = "deadline_window_expired"
        if all_windows_closed:
            job_copy["lifecycleStatus"] = "expired"
            job_copy["visibility"] = "archived"
            job_copy["wholeOpportunityClosed"] = False
        elif job_windows and job_copy.get("lifecycleStatus") == "expired" and not job_copy.get("wholeOpportunityClosed"):
            job_copy["lifecycleStatus"] = "unknown"
            job_copy["visibility"] = "public" if job_copy.get("publicationStatus") == "approved" else "review_pending"

        url = job.get("sourceUrl")
        if not isinstance(url, str) or not url:
            failure_count += 1
            job_copy["lastAttemptAt"] = now_text
            job_copy["lastAttemptReason"] = "recheck_missing_source_url"
            updated_jobs.append(job_copy)
            if all_windows_closed:
                closed_count += 1
            continue

        lmc_missing = False
        try:
            source = source_by_id.get(str(job.get("discoverySourceId") or ""))
            if source and source.get("parser") == "lmc_graphql":
                source_id = str(source["id"])
                if source_id not in lmc_config_cache:
                    shell_status, shell_html = cached_get(str(source["url"]))
                    lmc_config_cache[source_id] = (
                        parse_lmc_widget_config(shell_html) if shell_status == 200 else None
                    )
                config = lmc_config_cache[source_id]
                item_id = str(job.get("sourceItemId") or "").strip()
                if not item_id:
                    item_id = str(parse_qs(urlsplit(url).query).get("id", [""])[0])
                if config is None or not item_id:
                    status, html = 0, ""
                else:
                    endpoint = str(source.get("apiUrl") or LMC_GRAPHQL_ENDPOINT)
                    status, body = cached_post(
                        endpoint,
                        _lmc_detail_payload(config, item_id),
                        {"X-Api-Key": config["apiKey"]},
                    )
                    job_ad = _lmc_job_ad(body) if status == 200 else None
                    if job_ad is not None and str(job_ad.get("id") or "") == item_id:
                        content = job_ad.get("content") if isinstance(job_ad.get("content"), dict) else {}
                        html = (
                            f"<h1>{job_ad.get('title') or ''}</h1>"
                            + str(content.get("htmlContent") or "")
                        )
                    else:
                        html = ""
                        try:
                            decoded = json.loads(body)
                            widget = decoded.get("data", {}).get("widget", {})
                            lmc_missing = (
                                status == 200
                                and not decoded.get("errors")
                                and isinstance(widget, dict)
                                and "jobAd" in widget
                                and widget.get("jobAd") is None
                            )
                        except (json.JSONDecodeError, AttributeError):
                            lmc_missing = False
            else:
                status, html = cached_get(url)
        except Exception as exc:
            failure_count += 1
            job_copy["lastAttemptAt"] = now_text
            job_copy["lastAttemptReason"] = f"recheck_error_{type(exc).__name__}: {exc}"[:240]
            updated_jobs.append(job_copy)
            if all_windows_closed:
                closed_count += 1
            continue

        job_copy["lastAttemptAt"] = now_text
        if lmc_missing:
            http_success_count += 1
            job_copy["lastStatusCheckedAt"] = now_text
            job_copy["lastAttemptReason"] = "official_ats_detail_unavailable"
            job_copy["lifecycleStatus"] = "unavailable"
            job_copy["visibility"] = "archived"
            job_copy["wholeOpportunityClosed"] = False
            job_copy["unavailableAt"] = now_text
            for window in job_windows:
                window["status"] = "closed"
                window["closedReason"] = "official_application_unavailable"
                window["closedAt"] = now_text
            closed_count += 1
            updated_jobs.append(job_copy)
            continue
        if status != 200 or not html.strip():
            failure_count += 1
            job_copy["lastAttemptReason"] = f"recheck_http_{status}"
            updated_jobs.append(job_copy)
            if all_windows_closed:
                closed_count += 1
            continue

        http_success_count += 1
        job_copy["lastStatusCheckedAt"] = now_text
        job_copy["lastAttemptReason"] = "recheck_ok"
        text = visible_text(html)
        title_en = job.get("title", {}).get("en") if isinstance(job.get("title"), dict) else str(job.get("title") or "")
        if page_is_closed(text, title_en):
            job_copy["lifecycleStatus"] = "closed"
            job_copy["wholeOpportunityClosed"] = True
            job_copy["visibility"] = "archived"
            job_copy["closedAt"] = now_text
            job_copy["closureReason"] = "page_announced_closure"
            for window in job_windows:
                window["status"] = "closed"
                window["closedReason"] = "whole_opportunity_closed"
                window["closedAt"] = now_text
            all_windows_closed = True
        if all_windows_closed:
            closed_count += 1
        updated_jobs.append(job_copy)

    merged = dict(previous)
    merged["jobs"] = updated_jobs
    merged["windows"] = updated_windows
    merged["lastRecheckedAt"] = now_text
    merged["lastRecheckResult"] = {
        "checked": checked_count,
        "httpSucceeded": http_success_count,
        "failed": failure_count,
        "closed": closed_count,
    }
    atomic_write(jobs_path, merged)
    from safety_status import maybe_publish_from_recheck

    maybe_publish_from_recheck(
        previous,
        merged,
        now_text,
        jobs_path=jobs_path,
        production_jobs_path=JOBS_OUT,
        safety_dir=safety_dir,
    )

    if failure_count:
        schedule_manager.record_job_recheck_failure(
            f"{failure_count}/{checked_count} job status checks failed",
            checked_count=checked_count,
            closed_count=closed_count,
            now=now,
        )
    else:
        schedule_manager.record_job_recheck_success(checked_count, closed_count, now)
    return {
        "checked": checked_count,
        "httpSucceeded": http_success_count,
        "failed": failure_count,
        "closed": closed_count,
        "status": "succeeded" if failure_count == 0 else ("failed" if http_success_count == 0 else "partial"),
    }


def recheck_open_jobs(
    fetch_page=None,
    now: datetime | None = None,
    *,
    jobs_path: Path | None = None,
    schedule_manager: ScheduleManager | None = None,
    use_lock: bool = True,
    post_json=None,
    safety_dir: Path | None = None,
) -> dict:
    current = _aware_utc(now or datetime.now(timezone.utc))
    manager = schedule_manager or ScheduleManager()
    context = RunLock() if use_lock else nullcontext()
    with context:
        return _recheck_open_jobs_unlocked(
            fetch_page,
            current,
            jobs_path or JOBS_OUT,
            manager,
            post_json=post_json,
            safety_dir=safety_dir,
        )


def run_once(
    day=None,
    force: bool = True,
    dry_run: bool = False,
    skip_portals: bool = False,
    shard: int | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    day = day or utc_today(now)
    plan = plan_for_day(day, shard=shard)
    report = {
        "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": plan["date"],
        "shard": plan["shard"],
        "shardCount": plan["shardCount"],
        "dryRun": dry_run,
        "institutionIds": plan["institutionIds"],
        "jobIds": plan["jobIds"],
        "counts": plan["counts"],
        "published": False,
    }
    if dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    sched_mgr = ScheduleManager()
    with RunLock():
        try:
            report["programmes"] = harvest_programmes(plan["schools"], force)
            report["jobs"] = harvest_jobs(plan["jobs"], set(plan["institutionIds"]))
            if not skip_portals:
                report["portals"] = harvest_portals(plan["schools"], [item["id"] for item in baseline_schools()])
            report["inventory"] = rebuild_inventory()
            programme_success = lambda item: (
                item.get("status") in {"ok", "skipped_existing"}
                and isinstance(item.get("parsedProgrammes"), int)
                and item["parsedProgrammes"] > 0
            )
            report["ok"] = sum(programme_success(item) for item in report["programmes"])
            report["failed"] = sum(not programme_success(item) for item in report["programmes"])
            job_failures = [
                item for item in report.get("jobs", {}).get("skipped", [])
                if item.get("reason") not in {"past-deadline"}
            ]
            discovery_failures = [
                item for item in report.get("jobs", {}).get("discovery", {}).get("attempts", [])
                if not item.get("ok")
            ]
            job_failures.extend(discovery_failures)
            portal_failures = [
                item for item in report.get("portals", {}).get("attempts", [])
                if item.get("kind") == "missing" or item.get("lastAttemptReason") == "probe_failed_kept_last_good"
            ]
            report["jobFailures"] = job_failures
            report["portalFailures"] = [item.get("institutionId") for item in portal_failures]
            total_failures = report["failed"] + len(job_failures) + len(portal_failures)
            report["status"] = "succeeded" if total_failures == 0 else "partial"

            school_id_by_code = {school.get("msmtCode"): school.get("id") for school in plan["schools"]}
            for item in report["programmes"]:
                source_id = f"programme:{school_id_by_code.get(item.get('msmtCode')) or item.get('msmtCode') or 'unknown'}"
                succeeded = programme_success(item)
                sched_mgr.record_source_result(
                    source_id,
                    succeeded=succeeded,
                    error=None if succeeded else str(item.get("status") or "zero parsed programmes"),
                    now=now,
                )
            skipped_by_job = {item.get("id"): item.get("reason") for item in report.get("jobs", {}).get("skipped", [])}
            for candidate in plan["jobs"]:
                reason = skipped_by_job.get(candidate["id"])
                succeeded = reason is None or reason == "past-deadline"
                sched_mgr.record_source_result(
                    f"job:{candidate['id']}",
                    succeeded=succeeded,
                    error=None if succeeded else str(reason),
                    now=now,
                )
            for item in report.get("jobs", {}).get("discovery", {}).get("attempts", []):
                sched_mgr.record_source_result(
                    f"job-discovery:{item.get('sourceId') or 'unknown'}:{item.get('kind') or 'unknown'}",
                    succeeded=bool(item.get("ok")),
                    error=None if item.get("ok") else str(item.get("reason") or f"http-{item.get('status')}"),
                    now=now,
                )
            for item in report.get("portals", {}).get("attempts", []):
                succeeded = item not in portal_failures
                sched_mgr.record_source_result(
                    f"portal:{item.get('institutionId') or 'unknown'}",
                    succeeded=succeeded,
                    error=None if succeeded else str(item.get("lastAttemptReason") or item.get("kind")),
                    now=now,
                )
            sched_mgr.record_source_result("inventory:official-register", succeeded=True, now=now)
            RUNS.mkdir(parents=True, exist_ok=True)
            atomic_write(STATE, report)
            (RUNS / f"refresh-{plan['date']}-shard{plan['shard']}.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if total_failures == 0:
                sched_mgr.record_shard_success(plan["shard"], now)
            else:
                sched_mgr.record_shard_failure(
                    plan["shard"],
                    f"{total_failures} source operations failed in shard {plan['shard']}",
                    now,
                )
        except Exception as exc:
            sched_mgr.record_shard_failure(plan["shard"], str(exc), now)
            raise
    print(json.dumps({"shard": plan["shard"], "ok": report.get("ok"), "failed": report.get("failed"), "inventory": report.get("inventory")}, ensure_ascii=False))
    return report


def run_catch_up(force: bool = True, skip_portals: bool = False, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    sched_mgr = ScheduleManager()
    tasks = sched_mgr.get_pending_tasks(now)
    results = []
    for task in tasks:
        if task["type"] == "shard_refresh" and task["priority"] in {"overdue_catchup", "retry"}:
            s = task["shardIndex"]
            if sched_mgr.acquire_lease("shard_refresh", shard_index=s, now=now):
                print(f"[Catch-up] Running shard {s} (priority={task['priority']}, reason={task['reason']})", flush=True)
                try:
                    res = run_once(force=force, skip_portals=skip_portals, shard=s, now=now)
                    results.append(res)
                finally:
                    sched_mgr.release_lease("shard_refresh", shard_index=s, now=now)
        elif task["type"] == "job_recheck":
            if sched_mgr.acquire_lease(task["type"], now=now):
                print("[Catch-up] Running hourly lightweight job recheck", flush=True)
                try:
                    res = recheck_open_jobs(now=now, schedule_manager=sched_mgr)
                    results.append(res)
                finally:
                    sched_mgr.release_lease(task["type"], now=now)
        elif task["type"] == "job_discovery":
            if sched_mgr.acquire_lease(task["type"], now=now):
                print("[Catch-up] Running four-hour official job discovery", flush=True)
                try:
                    results.append(discover_all_jobs(now=now, schedule_manager=sched_mgr))
                finally:
                    sched_mgr.release_lease(task["type"], now=now)
        elif task["type"] == "programme_availability":
            if sched_mgr.acquire_lease(task["type"], now=now):
                print("[Catch-up] Running two-hour official programme-directory refresh", flush=True)
                try:
                    results.append(
                        refresh_programme_availability(now=now, schedule_manager=sched_mgr)
                    )
                finally:
                    sched_mgr.release_lease(task["type"], now=now)
        elif task["type"] == "czu_programme_availability":
            if sched_mgr.acquire_lease(task["type"], now=now):
                print("[Catch-up] Running two-hour CZU programme refresh", flush=True)
                try:
                    results.append(
                        refresh_czu_programme_availability(now=now, schedule_manager=sched_mgr)
                    )
                finally:
                    sched_mgr.release_lease(task["type"], now=now)
        elif task["type"] == "czu_czech_programme_availability":
            if sched_mgr.acquire_lease(task["type"], now=now):
                print("[Catch-up] Running two-hour CZU Czech catalogue refresh", flush=True)
                try:
                    results.append(
                        refresh_czu_czech_programme_availability(
                            now=now, schedule_manager=sched_mgr
                        )
                    )
                finally:
                    sched_mgr.release_lease(task["type"], now=now)
        elif task["type"] == "czu_doctoral_programme_availability":
            if sched_mgr.acquire_lease(task["type"], now=now):
                print("[Catch-up] Running two-hour CZU doctoral faculty cross-check", flush=True)
                try:
                    results.append(
                        refresh_czu_doctoral_programme_availability(
                            now=now, schedule_manager=sched_mgr
                        )
                    )
                finally:
                    sched_mgr.release_lease(task["type"], now=now)
    return results


def loop_daily(force: bool = True, skip_portals: bool = False) -> None:
    sched_mgr = ScheduleManager()
    while True:
        now = datetime.now(timezone.utc)
        pending = sched_mgr.get_pending_tasks(now)
        for task in pending:
            if task["type"] == "shard_refresh":
                s = task["shardIndex"]
                if sched_mgr.acquire_lease("shard_refresh", shard_index=s, now=now):
                    print(f"Executing task: shard {s} ({task['priority']})", flush=True)
                    try:
                        run_once(force=force, skip_portals=skip_portals, shard=s, now=now)
                    except Exception as e:
                        print(f"Task failed for shard {s}: {e}", flush=True)
                    finally:
                        sched_mgr.release_lease("shard_refresh", shard_index=s, now=datetime.now(timezone.utc))
            elif task["type"] == "job_recheck":
                if sched_mgr.acquire_lease("job_recheck", now=now):
                    print("Executing task: hourly job recheck", flush=True)
                    try:
                        recheck_open_jobs(now=now, schedule_manager=sched_mgr)
                    except Exception as e:
                        print(f"Job recheck failed: {e}", flush=True)
                    finally:
                        sched_mgr.release_lease("job_recheck", now=datetime.now(timezone.utc))
            elif task["type"] == "job_discovery":
                if sched_mgr.acquire_lease("job_discovery", now=now):
                    print("Executing task: four-hour job discovery", flush=True)
                    try:
                        discover_all_jobs(now=now, schedule_manager=sched_mgr)
                    except Exception as e:
                        print(f"Job discovery failed: {e}", flush=True)
                    finally:
                        sched_mgr.release_lease("job_discovery", now=datetime.now(timezone.utc))
            elif task["type"] == "programme_availability":
                if sched_mgr.acquire_lease("programme_availability", now=now):
                    print("Executing task: two-hour programme availability refresh", flush=True)
                    try:
                        refresh_programme_availability(now=now, schedule_manager=sched_mgr)
                    except Exception as e:
                        print(f"Programme availability refresh failed: {e}", flush=True)
                    finally:
                        sched_mgr.release_lease("programme_availability", now=datetime.now(timezone.utc))
            elif task["type"] == "czu_programme_availability":
                if sched_mgr.acquire_lease("czu_programme_availability", now=now):
                    print("Executing task: two-hour CZU programme refresh", flush=True)
                    try:
                        refresh_czu_programme_availability(now=now, schedule_manager=sched_mgr)
                    except Exception as e:
                        print(f"CZU programme refresh failed: {e}", flush=True)
                    finally:
                        sched_mgr.release_lease("czu_programme_availability", now=datetime.now(timezone.utc))
            elif task["type"] == "czu_czech_programme_availability":
                if sched_mgr.acquire_lease("czu_czech_programme_availability", now=now):
                    print("Executing task: two-hour CZU Czech catalogue refresh", flush=True)
                    try:
                        refresh_czu_czech_programme_availability(
                            now=now, schedule_manager=sched_mgr
                        )
                    except Exception as e:
                        print(f"CZU Czech catalogue refresh failed: {e}", flush=True)
                    finally:
                        sched_mgr.release_lease(
                            "czu_czech_programme_availability",
                            now=datetime.now(timezone.utc),
                        )
            elif task["type"] == "czu_doctoral_programme_availability":
                if sched_mgr.acquire_lease("czu_doctoral_programme_availability", now=now):
                    print("Executing task: two-hour CZU doctoral faculty cross-check", flush=True)
                    try:
                        refresh_czu_doctoral_programme_availability(
                            now=now, schedule_manager=sched_mgr
                        )
                    except Exception as e:
                        print(f"CZU doctoral faculty cross-check failed: {e}", flush=True)
                    finally:
                        sched_mgr.release_lease(
                            "czu_doctoral_programme_availability",
                            now=datetime.now(timezone.utc),
                        )

        current = datetime.now(timezone.utc)
        nxt = next_utc_midnight(current)
        wait = sched_mgr.next_wake_seconds(current)
        print(f"Waiting {wait}s until next due task (next midnight: {nxt.isoformat()})", flush=True)
        time.sleep(wait)


def main() -> None:
    args = sys.argv[1:]
    if "--harvest-baseline" in args:
        from harvest_baseline import main as harvest

        harvest()
        return
    policy = load_policy()
    sched_mgr = ScheduleManager()

    if "--status" in args:
        sched_state = sched_mgr.load_state()
        breaches = sched_mgr.check_sla_and_overdue()
        pending = sched_mgr.get_pending_tasks()
        print(
            json.dumps(
                {
                    "policy": policy.get("status"),
                    "state": load_json(STATE),
                    "schedule": sched_state,
                    "slaBreaches": breaches,
                    "pendingTasks": pending,
                    "lock": lock_is_held(LOCK),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    dry = "--dry-run" in args
    force = "--skip-existing" not in args
    skip_portals = "--skip-portals" in args
    shard_arg = None
    if "--shard" in args:
        shard_arg = int(args[args.index("--shard") + 1])

    if "--recheck-jobs" in args or "--discover-jobs" in args:
        from engine.runtime import require_http_fetcher, write_runtime_report

        runtime = write_runtime_report(RUNS / "scrapling-runtime.json")
        print(json.dumps({"scrapling": runtime}, ensure_ascii=False))
        require_http_fetcher(runtime)

    if "--recheck-jobs" in args:
        res = recheck_open_jobs()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if "--discover-jobs" in args:
        res = discover_all_jobs()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if "--refresh-programme-availability" in args:
        res = refresh_programme_availability()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if "--refresh-czu-programmes" in args:
        res = refresh_czu_programme_availability()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if "--refresh-czu-czech-programmes" in args:
        res = refresh_czu_czech_programme_availability()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if "--refresh-czu-doctoral-programmes" in args:
        res = refresh_czu_doctoral_programme_availability()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if "--catch-up" in args:
        res = run_catch_up(force=force, skip_portals=skip_portals)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    day = utc_today()
    if shard_arg is not None:
        from datetime import timedelta
        from refresh_shards import DEFAULT_ANCHOR

        day = DEFAULT_ANCHOR
        while shard_index_for_date(day) != shard_arg % SHARD_COUNT:
            day = day + timedelta(days=1)

    if "--loop" in args:
        loop_daily(force=force, skip_portals=skip_portals)
        return

    if "--once" in args or "--daily-shard" in args or dry or shard_arg is not None:
        run_once(day=day, force=force, dry_run=dry, skip_portals=skip_portals, shard=shard_arg)
        return

    print("ingestion worker daily 1/5 refresh")
    print(f"policy_status={policy.get('status')} sources={len(load_registry())}")
    print(
        "run with --once for today's stable fifth; --recheck-jobs for the hourly status sweep; "
        "--discover-jobs for all registered listings; --refresh-programme-availability for the "
        "official DZS candidate catalogue; --refresh-czu-programmes for CZU's English catalogue; "
        "--refresh-czu-czech-programmes for CZU's Czech-facing bachelor/master catalogue; "
        "--refresh-czu-doctoral-programmes for CZU's six-faculty doctoral cross-check; "
        "--catch-up for due tasks; --loop for the scheduler"
    )
    print("network_failure_means_closed", network_failure_means_closed(429, False))


if __name__ == "__main__":
    main()

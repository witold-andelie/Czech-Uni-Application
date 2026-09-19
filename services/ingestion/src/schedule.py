"""Atomic schedule queue, leases, retry timing, and refresh SLA tracking."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from file_lock import FileMutex, LockUnavailable
from refresh_shards import SHARD_COUNT, next_utc_midnight, shard_index_for_date, utc_today

logger = logging.getLogger("schedule")

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCHEDULE_STATE_PATH = ROOT / "work" / "runs" / "schedule-state.json"
SLA_HOURS = 120
JOB_RECHECK_INTERVAL_HOURS = 1
JOB_DISCOVERY_INTERVAL_HOURS = 4
PROGRAMME_AVAILABILITY_INTERVAL_HOURS = 2
CZU_PROGRAMME_AVAILABILITY_INTERVAL_HOURS = 2
CZU_CZECH_PROGRAMME_AVAILABILITY_INTERVAL_HOURS = 2
CZU_DOCTORAL_PROGRAMME_AVAILABILITY_INTERVAL_HOURS = 2
RETRY_BACKOFFS = [300, 1800, 7200]
STATE_LOCK_TIMEOUT_SECONDS = 5.0

VOLATILE_TASKS = {
    "job_recheck": {
        "stateKey": "jobRecheck",
        "intervalHours": JOB_RECHECK_INTERVAL_HOURS,
        "priority": "hourly_job_status",
        "reason": "Recheck every known public and candidate job against its official page",
    },
    "job_discovery": {
        "stateKey": "jobDiscovery",
        "intervalHours": JOB_DISCOVERY_INTERVAL_HOURS,
        "priority": "four_hour_job_discovery",
        "reason": "Discover new vacancies from every registered official job listing",
    },
    "programme_availability": {
        "stateKey": "programmeAvailability",
        "intervalHours": PROGRAMME_AVAILABILITY_INTERVAL_HOURS,
        "priority": "two_hour_programme_availability",
        "reason": "Refresh the complete official DZS programme directory and availability signal",
    },
    "czu_programme_availability": {
        "stateKey": "czuProgrammeAvailability",
        "intervalHours": CZU_PROGRAMME_AVAILABILITY_INTERVAL_HOURS,
        "priority": "two_hour_czu_programme_availability",
        "reason": "Refresh CZU's official English programme catalogue, detail windows, and open signal",
    },
    "czu_czech_programme_availability": {
        "stateKey": "czuCzechProgrammeAvailability",
        "intervalHours": CZU_CZECH_PROGRAMME_AVAILABILITY_INTERVAL_HOURS,
        "priority": "two_hour_czu_czech_programme_availability",
        "reason": "Refresh CZU's official Czech-facing bachelor/master sitemap and every detail window",
    },
    "czu_doctoral_programme_availability": {
        "stateKey": "czuDoctoralProgrammeAvailability",
        "intervalHours": CZU_DOCTORAL_PROGRAMME_AVAILABILITY_INTERVAL_HOURS,
        "priority": "two_hour_czu_doctoral_programme_availability",
        "reason": (
            "Cross-check CZU's MŠMT doctoral baseline against all six faculties' "
            "official programme and admissions evidence"
        ),
    },
}


def parse_iso(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ScheduleManager:
    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = state_path or DEFAULT_SCHEDULE_STATE_PATH
        self.lock_path = self.state_path.with_name(f".{self.state_path.name}.lock")
        self.owner_id = f"{os.getpid()}-{uuid.uuid4().hex}"
        self._held_leases: dict[str, str] = {}

    def _new_state(self, now: datetime) -> dict[str, Any]:
        iso_now = to_iso(now)

        def task_state(interval_hours: int, **metrics: Any) -> dict[str, Any]:
            return {
                "intervalHours": interval_hours,
                "lastAttemptAt": None,
                "lastSuccessAt": None,
                "nextDueAt": iso_now,
                "retryAt": None,
                "leaseUntil": None,
                "leaseOwner": None,
                "leaseToken": None,
                "status": "idle",
                "attempts": 0,
                "lastError": None,
                **metrics,
            }

        shards = {
            str(index): {
                "shardIndex": index,
                "lastAttemptAt": None,
                "lastSuccessAt": None,
                "nextDueAt": iso_now,
                "retryAt": None,
                "leaseUntil": None,
                "leaseOwner": None,
                "leaseToken": None,
                "status": "idle",
                "attempts": 0,
                "lastError": None,
            }
            for index in range(SHARD_COUNT)
        }
        return {
            "version": "3.3",
            "createdAt": iso_now,
            "updatedAt": iso_now,
            "slaHours": SLA_HOURS,
            "shards": shards,
            "jobRecheck": task_state(
                JOB_RECHECK_INTERVAL_HOURS,
                checkedJobsCount=0,
                closedJobsCount=0,
            ),
            "jobDiscovery": task_state(
                JOB_DISCOVERY_INTERVAL_HOURS,
                discoveredJobsCount=0,
                checkedSourcesCount=0,
            ),
            "programmeAvailability": task_state(
                PROGRAMME_AVAILABILITY_INTERVAL_HOURS,
                programmesCount=0,
                institutionsCount=0,
                openApplicationsCount=0,
            ),
            "czuProgrammeAvailability": task_state(
                CZU_PROGRAMME_AVAILABILITY_INTERVAL_HOURS,
                programmesCount=0,
                detailsWithCompleteWindowCount=0,
                openApplicationsCount=0,
                upcomingApplicationsCount=0,
                openPageReportedCount=0,
                availabilityCrosscheck="unknown",
            ),
            "czuCzechProgrammeAvailability": task_state(
                CZU_CZECH_PROGRAMME_AVAILABILITY_INTERVAL_HOURS,
                programmesCount=0,
                czechTaughtProgrammesCount=0,
                englishTaughtProgrammesCount=0,
                detailsWithCompleteWindowCount=0,
                openApplicationsCount=0,
                upcomingApplicationsCount=0,
                englishSourceCrosscheck="unknown",
            ),
            "czuDoctoralProgrammeAvailability": task_state(
                CZU_DOCTORAL_PROGRAMME_AVAILABILITY_INTERVAL_HOURS,
                programmesCount=0,
                facultiesCount=0,
                czechTaughtProgrammesCount=0,
                englishTaughtProgrammesCount=0,
                matchedProgrammesCount=0,
                openApplicationsCount=0,
                upcomingApplicationsCount=0,
                closedApplicationsCount=0,
                awaitingNextAcademicYearWindowCount=0,
            ),
            "sources": {},
            "slaBreaches": [],
        }

    def _validate_state(self, state: Any) -> bool:
        return (
            isinstance(state, dict)
            and isinstance(state.get("shards"), dict)
            and all(str(index) in state["shards"] for index in range(SHARD_COUNT))
            and isinstance(state.get("jobRecheck"), dict)
        )

    def _normalize_state(self, state: dict[str, Any], now: datetime) -> dict[str, Any]:
        template = self._new_state(now)
        state.setdefault("createdAt", state.get("updatedAt") or to_iso(now))
        state["version"] = "3.3"
        state.setdefault("slaHours", SLA_HOURS)
        state.setdefault("sources", {})
        state.setdefault("slaBreaches", [])
        for index in range(SHARD_COUNT):
            target = state["shards"][str(index)]
            for key, value in template["shards"][str(index)].items():
                target.setdefault(key, value)
        for spec in VOLATILE_TASKS.values():
            state_key = spec["stateKey"]
            target = state.setdefault(state_key, {})
            for key, value in template[state_key].items():
                target.setdefault(key, value)
            # A v2 state may still carry the old 24-hour job interval.  The
            # current policy is authoritative and migration must make an
            # already-due volatile task visible immediately.
            target["intervalHours"] = spec["intervalHours"]
            last_success = parse_iso(target.get("lastSuccessAt"))
            if last_success is not None:
                target["nextDueAt"] = to_iso(
                    last_success + timedelta(hours=spec["intervalHours"])
                )
        return state

    @contextmanager
    def _state_mutex(self) -> Iterator[None]:
        deadline = time.monotonic() + STATE_LOCK_TIMEOUT_SECONDS
        while True:
            mutex = FileMutex(self.lock_path, {"operation": "schedule-state"})
            try:
                mutex.__enter__()
                break
            except LockUnavailable:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for schedule-state lock: {self.lock_path}")
                time.sleep(0.01)
        try:
            yield
        finally:
            mutex.__exit__(None, None, None)

    def _read_unlocked(self, now: datetime) -> dict[str, Any]:
        if self.state_path.is_file():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                if self._validate_state(state):
                    return self._normalize_state(state, now)
            except Exception as exc:
                logger.warning("Failed to read schedule state from %s: %s", self.state_path, exc)
        return self._new_state(now)

    def _write_unlocked(self, state: dict[str, Any], now: datetime) -> None:
        state["updatedAt"] = to_iso(now)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(f".{self.state_path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            for attempt in range(8):
                try:
                    os.replace(temporary, self.state_path)
                    break
                except PermissionError:
                    if attempt == 7:
                        raise
                    # Windows virus scanners and indexed folders can retain a
                    # just-closed read handle briefly.  Keep the atomic rename,
                    # but tolerate that transient sharing violation.
                    time.sleep(0.01 * (2**attempt))
        finally:
            temporary.unlink(missing_ok=True)

    @contextmanager
    def _transaction(self, now: datetime) -> Iterator[dict[str, Any]]:
        with self._state_mutex():
            state = self._read_unlocked(now)
            yield state
            self._write_unlocked(state, now)

    def load_state(self, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        with self._state_mutex():
            state = self._read_unlocked(current)
            if not self.state_path.is_file():
                self._write_unlocked(state, current)
            return state

    def init_state(self, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        with self._state_mutex():
            state = self._new_state(current)
            self._write_unlocked(state, current)
            return state

    def save_state(self, state: dict[str, Any], now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        with self._state_mutex():
            self._write_unlocked(self._normalize_state(state, current), current)

    @staticmethod
    def _append_breach(state: dict[str, Any], breach: dict[str, Any], identity: tuple[Any, ...]) -> bool:
        existing = state.setdefault("slaBreaches", [])
        for item in existing:
            item_identity = tuple(item.get(key) for key in ("type", "shardIndex", "sourceId", "lastSuccessAt"))
            if item_identity == identity:
                return False
        existing.append(breach)
        return True

    def check_sla_and_overdue(self, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        new_breaches: list[dict[str, Any]] = []
        with self._transaction(current) as state:
            created_at = parse_iso(state.get("createdAt")) or current
            for index in range(SHARD_COUNT):
                info = state["shards"][str(index)]
                last_success = parse_iso(info.get("lastSuccessAt"))
                anchor = last_success or created_at
                elapsed_hours = (current - anchor).total_seconds() / 3600.0
                if elapsed_hours <= SLA_HOURS:
                    continue
                overdue_by = round(elapsed_hours - SLA_HOURS, 2)
                if info.get("status") not in {"running", "failed"}:
                    info["status"] = "overdue"
                breach = {
                    "type": "shard_overdue",
                    "shardIndex": index,
                    "lastSuccessAt": info.get("lastSuccessAt"),
                    "overdueHours": overdue_by,
                    "detectedAt": to_iso(current),
                    "message": f"Shard {index} exceeded the {SLA_HOURS}h success SLA by {overdue_by}h",
                }
                identity = ("shard_overdue", index, None, info.get("lastSuccessAt"))
                if self._append_breach(state, breach, identity):
                    new_breaches.append(breach)

            for task_type, spec in VOLATILE_TASKS.items():
                info = state[spec["stateKey"]]
                last_success = parse_iso(info.get("lastSuccessAt"))
                anchor = last_success or created_at
                elapsed_hours = (current - anchor).total_seconds() / 3600.0
                interval_hours = spec["intervalHours"]
                if elapsed_hours <= interval_hours:
                    continue
                if info.get("status") not in {"running", "failed"}:
                    info["status"] = "overdue"
                overdue_by = round(elapsed_hours - interval_hours, 2)
                breach = {
                    "type": "volatile_task_overdue",
                    "sourceId": task_type,
                    "lastSuccessAt": info.get("lastSuccessAt"),
                    "overdueHours": overdue_by,
                    "detectedAt": to_iso(current),
                    "message": (
                        f"{task_type} exceeded its {interval_hours}h success SLA "
                        f"by {overdue_by}h"
                    ),
                }
                identity = (
                    "volatile_task_overdue",
                    None,
                    task_type,
                    info.get("lastSuccessAt"),
                )
                if self._append_breach(state, breach, identity):
                    new_breaches.append(breach)

            for source_id, info in state.get("sources", {}).items():
                last_success = parse_iso(info.get("lastSuccessAt"))
                first_attempt = parse_iso(info.get("firstAttemptAt"))
                anchor = last_success or first_attempt
                if anchor is None:
                    continue
                elapsed_hours = (current - anchor).total_seconds() / 3600.0
                if elapsed_hours <= SLA_HOURS:
                    continue
                info["slaStatus"] = "overdue"
                overdue_by = round(elapsed_hours - SLA_HOURS, 2)
                breach = {
                    "type": "source_overdue",
                    "sourceId": source_id,
                    "lastSuccessAt": info.get("lastSuccessAt"),
                    "overdueHours": overdue_by,
                    "detectedAt": to_iso(current),
                    "message": f"Source {source_id} exceeded the {SLA_HOURS}h success SLA by {overdue_by}h",
                }
                identity = ("source_overdue", None, source_id, info.get("lastSuccessAt"))
                if self._append_breach(state, breach, identity):
                    new_breaches.append(breach)
        return new_breaches

    def get_pending_tasks(self, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        self.check_sla_and_overdue(current)
        state = self.load_state(current)
        tasks: list[dict[str, Any]] = []

        overdue: list[tuple[float, int]] = []
        for index in range(SHARD_COUNT):
            info = state["shards"][str(index)]
            lease_until = parse_iso(info.get("leaseUntil"))
            if lease_until and lease_until > current:
                continue
            if info.get("status") == "overdue":
                last_success = parse_iso(info.get("lastSuccessAt"))
                elapsed = (current - last_success).total_seconds() if last_success else float("inf")
                overdue.append((elapsed, index))
        overdue.sort(reverse=True)
        for _elapsed, index in overdue:
            tasks.append({"type": "shard_refresh", "shardIndex": index, "priority": "overdue_catchup", "reason": "SLA >120h breach catch-up"})

        for index in range(SHARD_COUNT):
            if any(task.get("type") == "shard_refresh" and task.get("shardIndex") == index for task in tasks):
                continue
            info = state["shards"][str(index)]
            lease_until = parse_iso(info.get("leaseUntil"))
            if lease_until and lease_until > current:
                continue
            retry_at = parse_iso(info.get("retryAt"))
            if retry_at and retry_at <= current:
                tasks.append({"type": "shard_refresh", "shardIndex": index, "priority": "retry", "reason": f"Retry after failure: {info.get('lastError')}"})

        today_shard = shard_index_for_date(utc_today(current))
        today_info = state["shards"][str(today_shard)]
        lease_until = parse_iso(today_info.get("leaseUntil"))
        retry_at = parse_iso(today_info.get("retryAt"))
        already_queued = any(task.get("type") == "shard_refresh" and task.get("shardIndex") == today_shard for task in tasks)
        retry_backoff_active = retry_at is not None and retry_at > current
        if not already_queued and not retry_backoff_active and not (lease_until and lease_until > current):
            last_success = parse_iso(today_info.get("lastSuccessAt"))
            today_start = datetime(current.year, current.month, current.day, tzinfo=timezone.utc)
            if last_success is None or last_success < today_start:
                tasks.append({"type": "shard_refresh", "shardIndex": today_shard, "priority": "daily_scheduled", "reason": f"Regular daily 1/5 rotation shard {today_shard}"})

        for task_type, spec in VOLATILE_TASKS.items():
            info = state[spec["stateKey"]]
            lease_until = parse_iso(info.get("leaseUntil"))
            if lease_until and lease_until > current:
                continue
            retry_at = parse_iso(info.get("retryAt"))
            if retry_at and retry_at > current:
                continue
            if retry_at and retry_at <= current:
                tasks.append(
                    {
                        "type": task_type,
                        "priority": "retry",
                        "reason": f"Retry after failure: {info.get('lastError')}",
                    }
                )
                continue
            next_due = parse_iso(info.get("nextDueAt"))
            if next_due is None or next_due <= current:
                tasks.append(
                    {
                        "type": task_type,
                        "priority": spec["priority"],
                        "reason": spec["reason"],
                    }
                )
        return tasks

    @staticmethod
    def _lease_key(task_type: str, shard_index: int | None) -> str:
        return f"{task_type}:{shard_index if shard_index is not None else '-'}"

    @staticmethod
    def _task_info(
        state: dict[str, Any], task_type: str, shard_index: int | None
    ) -> dict[str, Any] | None:
        if task_type == "shard_refresh" and shard_index is not None:
            return state["shards"].get(str(shard_index))
        spec = VOLATILE_TASKS.get(task_type)
        return state.get(spec["stateKey"]) if spec else None

    def acquire_lease(self, task_type: str, shard_index: int | None = None, lease_seconds: int = 1800, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        key = self._lease_key(task_type, shard_index)
        with self._transaction(current) as state:
            info = self._task_info(state, task_type, shard_index)
            if info is None:
                return False
            lease_until = parse_iso(info.get("leaseUntil"))
            if lease_until and lease_until > current:
                return False
            token = uuid.uuid4().hex
            info["leaseUntil"] = to_iso(current + timedelta(seconds=lease_seconds))
            info["leaseOwner"] = self.owner_id
            info["leaseToken"] = token
            info["status"] = "running"
            self._held_leases[key] = token
            return True

    def renew_lease(self, task_type: str, shard_index: int | None = None, lease_seconds: int = 1800, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        key = self._lease_key(task_type, shard_index)
        token = self._held_leases.get(key)
        if token is None:
            return False
        with self._transaction(current) as state:
            info = self._task_info(state, task_type, shard_index)
            if info is None or info.get("leaseOwner") != self.owner_id or info.get("leaseToken") != token:
                return False
            info["leaseUntil"] = to_iso(current + timedelta(seconds=lease_seconds))
            return True

    def release_lease(self, task_type: str, shard_index: int | None = None, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        key = self._lease_key(task_type, shard_index)
        token = self._held_leases.pop(key, None)
        if token is None:
            return
        with self._transaction(current) as state:
            info = self._task_info(state, task_type, shard_index)
            if info is None or info.get("leaseOwner") != self.owner_id or info.get("leaseToken") != token:
                return
            info["leaseUntil"] = None
            info["leaseOwner"] = None
            info["leaseToken"] = None
            if info.get("status") == "running":
                info["status"] = "idle"

    @staticmethod
    def _clear_lease(info: dict[str, Any]) -> None:
        info["leaseUntil"] = None
        info["leaseOwner"] = None
        info["leaseToken"] = None

    def record_shard_success(self, shard_index: int, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        with self._transaction(current) as state:
            info = state["shards"][str(shard_index)]
            info["lastAttemptAt"] = to_iso(current)
            info["lastSuccessAt"] = to_iso(current)
            info["nextDueAt"] = to_iso(current + timedelta(hours=SLA_HOURS))
            info["retryAt"] = None
            info["status"] = "completed"
            info["attempts"] = 0
            info["lastError"] = None
            self._clear_lease(info)

    def record_shard_failure(self, shard_index: int, error: str, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        with self._transaction(current) as state:
            info = state["shards"][str(shard_index)]
            attempts = int(info.get("attempts") or 0) + 1
            info["lastAttemptAt"] = to_iso(current)
            info["attempts"] = attempts
            info["lastError"] = str(error)
            info["status"] = "failed"
            info["retryAt"] = to_iso(current + timedelta(seconds=RETRY_BACKOFFS[min(attempts - 1, len(RETRY_BACKOFFS) - 1)]))
            self._clear_lease(info)

    def record_job_recheck_success(self, checked_count: int, closed_count: int, now: datetime | None = None) -> None:
        self.record_volatile_success(
            "job_recheck",
            metrics={"checkedJobsCount": checked_count, "closedJobsCount": closed_count},
            now=now,
        )

    def record_job_recheck_failure(self, error: str, *, checked_count: int, closed_count: int, now: datetime | None = None) -> None:
        self.record_volatile_failure(
            "job_recheck",
            error,
            metrics={"checkedJobsCount": checked_count, "closedJobsCount": closed_count},
            now=now,
        )

    def record_job_recheck_partial(
        self,
        error: str,
        *,
        checked_count: int,
        closed_count: int,
        now: datetime | None = None,
    ) -> None:
        """A mixed recheck still completed the hourly sweep. Keep the miss for logs."""
        spec = VOLATILE_TASKS["job_recheck"]
        current = now or datetime.now(timezone.utc)
        with self._transaction(current) as state:
            info = state[spec["stateKey"]]
            info["lastAttemptAt"] = to_iso(current)
            info["lastSuccessAt"] = to_iso(current)
            info["nextDueAt"] = to_iso(current + timedelta(hours=spec["intervalHours"]))
            info["retryAt"] = None
            info["status"] = "completed"
            info["attempts"] = 0
            info["lastError"] = str(error)
            info["checkedJobsCount"] = checked_count
            info["closedJobsCount"] = closed_count
            self._clear_lease(info)

    def record_volatile_success(
        self,
        task_type: str,
        *,
        metrics: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        spec = VOLATILE_TASKS.get(task_type)
        if spec is None:
            raise ValueError(f"Unknown volatile task: {task_type}")
        current = now or datetime.now(timezone.utc)
        with self._transaction(current) as state:
            info = state[spec["stateKey"]]
            info["lastAttemptAt"] = to_iso(current)
            info["lastSuccessAt"] = to_iso(current)
            info["nextDueAt"] = to_iso(
                current + timedelta(hours=spec["intervalHours"])
            )
            info["retryAt"] = None
            info["status"] = "completed"
            info["attempts"] = 0
            info["lastError"] = None
            if metrics:
                info.update(metrics)
            self._clear_lease(info)

    def record_volatile_failure(
        self,
        task_type: str,
        error: str,
        *,
        metrics: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        spec = VOLATILE_TASKS.get(task_type)
        if spec is None:
            raise ValueError(f"Unknown volatile task: {task_type}")
        current = now or datetime.now(timezone.utc)
        with self._transaction(current) as state:
            info = state[spec["stateKey"]]
            attempts = int(info.get("attempts") or 0) + 1
            info["lastAttemptAt"] = to_iso(current)
            info["attempts"] = attempts
            info["lastError"] = str(error)
            info["status"] = "failed"
            info["retryAt"] = to_iso(
                current
                + timedelta(
                    seconds=RETRY_BACKOFFS[
                        min(attempts - 1, len(RETRY_BACKOFFS) - 1)
                    ]
                )
            )
            if metrics:
                info.update(metrics)
            self._clear_lease(info)

    def record_source_result(
        self,
        source_id: str,
        *,
        succeeded: bool,
        error: str | None = None,
        now: datetime | None = None,
        retry_at: datetime | str | None = None,
    ) -> None:
        current = now or datetime.now(timezone.utc)
        with self._transaction(current) as state:
            info = state.setdefault("sources", {}).setdefault(
                source_id,
                {"firstAttemptAt": to_iso(current), "lastAttemptAt": None, "lastSuccessAt": None, "attempts": 0, "lastError": None, "slaStatus": "current"},
            )
            info["lastAttemptAt"] = to_iso(current)
            if succeeded:
                info["lastSuccessAt"] = to_iso(current)
                info["attempts"] = 0
                info["lastError"] = None
                info["slaStatus"] = "current"
                info["retryAt"] = None
            else:
                info["attempts"] = int(info.get("attempts") or 0) + 1
                info["lastError"] = str(error or "unknown failure")
                if retry_at is not None:
                    info["retryAt"] = retry_at if isinstance(retry_at, str) else to_iso(retry_at)

    def next_wake_seconds(self, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        state = self.load_state(current)
        candidates = [next_utc_midnight(current)]
        volatile_infos = [
            state[spec["stateKey"]] for spec in VOLATILE_TASKS.values()
        ]
        for info in [*state["shards"].values(), *volatile_infos]:
            for field in ("retryAt", "nextDueAt"):
                value = parse_iso(info.get(field))
                if value and value > current:
                    candidates.append(value)
        wait = min((candidate - current).total_seconds() for candidate in candidates)
        return max(60, min(3600, int(wait)))

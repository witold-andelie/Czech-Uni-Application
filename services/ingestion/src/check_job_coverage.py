"""Regression floor for the harvested job candidate file (A101).

Identities and approved records must not silently shrink. Verified close,
expiry, or an operator disposition can lower the floor only in a deliberate
commit that records the reason.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JOBS = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
DEFAULT_FLOOR = ROOT / "data" / "sources" / "coverage" / "job-coverage-floor.json"


def _counts(payload: dict) -> tuple[int, int]:
    jobs = [item for item in payload.get("jobs") or [] if isinstance(item, dict) and item.get("id")]
    approved = sum(1 for item in jobs if item.get("publicationStatus") == "approved")
    return len(jobs), approved


def check(jobs_path: Path = DEFAULT_JOBS, floor_path: Path = DEFAULT_FLOOR) -> tuple[bool, list[str]]:
    if not floor_path.is_file():
        return True, [f"no job floor committed at {floor_path}; nothing to compare against"]
    floor = json.loads(floor_path.read_text(encoding="utf-8"))
    if not jobs_path.is_file():
        return False, ["JOB_COVERAGE_REGRESSION: the candidate job file is missing"]
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    identities, approved = _counts(payload)
    errors: list[str] = []
    floor_identities = int(floor.get("identityTotal") or 0)
    floor_approved = int(floor.get("approvedTotal") or 0)
    if identities < floor_identities:
        errors.append(
            "JOB_COVERAGE_REGRESSION: "
            f"candidate identities {identities}, the committed floor is {floor_identities}"
        )
    if approved < floor_approved:
        errors.append(
            "JOB_COVERAGE_REGRESSION: "
            f"approved records {approved}, the committed floor is {floor_approved}"
        )
    if errors:
        return False, errors
    return True, [
        f"job candidate file: {identities} identities, {approved} approved "
        f"(floor {floor_identities}/{floor_approved})"
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Check harvested jobs against the A101 floor")
    parser.add_argument("--jobs", type=Path, default=DEFAULT_JOBS)
    parser.add_argument("--floor", type=Path, default=DEFAULT_FLOOR)
    args = parser.parse_args()
    ok, messages = check(args.jobs, args.floor)
    for message in messages:
        print(message, flush=True)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Regression floor for the harvested job candidate file (A101).

Identities and approved records must not silently shrink. Verified close,
expiry, or an operator disposition can lower the floor only in a deliberate
commit that records the reason.

Owner decision 2026-10-01: an approved record that went back to review
because its official source or derived facts changed (A53) still counts toward the approved
floor. It keeps its identity and waits in the re-review queue; only the
public snapshot drops it until it is reviewed again. It counts only with the
reason proven: stale translation, a completed review on record, and a source
or fact hash different from the reviewed one. A record demoted while both
still match has no reason and still fails the floor.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JOBS = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
DEFAULT_FLOOR = ROOT / "data" / "sources" / "coverage" / "job-coverage-floor.json"
DEFAULT_REVIEWS = ROOT / "data" / "sources" / "reviews" / "job-translations.json"


def _returned_for_source_change(job: dict, reviews: dict, windows: list | None = None) -> bool:
    """A reviewed record sent back to review because its source or facts changed (A53).

    The reason must be on record: a stale translation, a completed review,
    and a source hash or fact hash that no longer matches the review. Stale
    with both hashes still matching has no reason, so it does not count.
    """
    if job.get("publicationStatus") != "review_pending" or job.get("translationStatus") != "stale":
        return False
    entry = reviews.get(str(job.get("id")))
    if not isinstance(entry, dict) or (entry.get("reviewer") or {}).get("role") != "operator_source_review":
        return False
    current, reviewed = job.get("sourceHash"), entry.get("sourceHash")
    if current and reviewed and current != reviewed:
        return True
    from publication_rules import review_job_fact_hash

    owned = [item for item in windows or [] if isinstance(item, dict) and item.get("ownerId") == job.get("id")]
    return bool(entry.get("factHash")) and review_job_fact_hash(job, owned, entry) != entry.get("factHash")


def _load_reviews(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviews = payload.get("reviews") if isinstance(payload, dict) else None
    return reviews if isinstance(reviews, dict) else {}


def _counts(payload: dict, reviews: dict | None = None) -> tuple[int, int, int]:
    jobs = [item for item in payload.get("jobs") or [] if isinstance(item, dict) and item.get("id")]
    approved = sum(1 for item in jobs if item.get("publicationStatus") == "approved")
    windows = [item for item in payload.get("windows") or [] if isinstance(item, dict)]
    returned = sum(1 for item in jobs if _returned_for_source_change(item, reviews or {}, windows))
    return len(jobs), approved, returned


def check(
    jobs_path: Path = DEFAULT_JOBS,
    floor_path: Path = DEFAULT_FLOOR,
    reviews_path: Path | None = DEFAULT_REVIEWS,
) -> tuple[bool, list[str]]:
    if not floor_path.is_file():
        return True, [f"no job floor committed at {floor_path}; nothing to compare against"]
    floor = json.loads(floor_path.read_text(encoding="utf-8"))
    if not jobs_path.is_file():
        return False, ["JOB_COVERAGE_REGRESSION: the candidate job file is missing"]
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    identities, approved, returned = _counts(payload, _load_reviews(reviews_path))
    errors: list[str] = []
    floor_identities = int(floor.get("identityTotal") or 0)
    floor_approved = int(floor.get("approvedTotal") or 0)
    if identities < floor_identities:
        errors.append(
            "JOB_COVERAGE_REGRESSION: "
            f"candidate identities {identities}, the committed floor is {floor_identities}"
        )
    if approved + returned < floor_approved:
        errors.append(
            "JOB_COVERAGE_REGRESSION: "
            f"approved records {approved} (+{returned} back in review after an official "
            f"source or fact change), the committed floor is {floor_approved}"
        )
    if errors:
        return False, errors
    return True, [
        f"job candidate file: {identities} identities, {approved} approved"
        + (f" + {returned} back in review after an official source or fact change" if returned else "")
        + f" (floor {floor_identities}/{floor_approved})"
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

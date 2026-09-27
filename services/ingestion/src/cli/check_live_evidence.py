"""Publish gate: every job entering a snapshot needs recent live evidence.

Reads the evidence written by services/ingestion/src/cli/verify_live_titles.py
(tracked at data/sources/coverage/live-title-verification.json) and the job file
that is about to be snapshotted. It is offline: it never fetches anything, so CI
can run it without touching university sites.

Rules (docs/REFRESH_POLICY.md, docs/CRAWLING_RULES.md):
- A job is confirmed only when a recent row records status "matched" or
  "operator_verified" for its candidateId.
- A job whose announced application window has already closed is not required
  to have live evidence: it is expected to be archived or withheld.
- An http_404/http_403/http_500/timeout/source_change_noted row is never read as
  a closed vacancy; it simply does not confirm the job.

Owner decision 2026-09-26 (docs/REFRESH_POLICY.md, docs/ACCEPTANCE.md A96): one
such record no longer holds the whole publication. The publisher withholds it by
id and reason in ``publicationSelection.withheld`` and publishes the rest, so this
gate reports those records and exits 0. It still fails the run when no job in the
candidate file carries live proof, or when every job that would enter the
snapshot lacks it - withholding them all would publish an empty research
library, and that is a verifier failure rather than a source change. ``--strict``
restores the earlier hold-on-any-single-record behaviour for an operator who
wants the report to be a hard stop.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from live_evidence import (  # noqa: E402
    DEFAULT_MAX_AGE_DAYS,
    EVIDENCE,
    load_evidence,
    missing_live_evidence,
    publication_gate,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish gate for live-verified evidence")
    parser.add_argument("--jobs", type=Path, required=True, help="candidate job file about to be snapshotted")
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail the run on any single unconfirmed record instead of reporting it as withheld",
    )
    args = parser.parse_args()

    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    evidence = load_evidence(args.evidence)
    if args.strict:
        errors = [
            f"LIVE_EVIDENCE_MISSING: {job_id} has no live verification within {args.max_age_days} days ({reason})"
            for job_id, reason in missing_live_evidence(
                jobs, evidence, max_age_days=args.max_age_days, now=datetime.now(timezone.utc)
            )
        ]
        withheld = []
    else:
        errors, withheld = publication_gate(
            jobs, evidence, max_age_days=args.max_age_days, now=datetime.now(timezone.utc)
        )
    if errors:
        print(f"publication held: {len(errors)} live-evidence error(s)")
        for error in errors:
            print(f"  {error}")
        print("Action: re-run verify_live_titles.py so every job entering the snapshot is verified.")
        raise SystemExit(1)
    if withheld:
        print(
            f"live evidence ok for the publication; {len(withheld)} record(s) will be withheld "
            "by id and reason (publicationSelection.withheld), never reported as closed:"
        )
        for job_id, reason in withheld:
            print(f"  held {job_id}: {reason}")
        print(
            "Action: re-run verify_live_titles.py to confirm them, or disposition each item "
            "(archive / re-source) in the ledger; the remaining records publish as they stand."
        )
        raise SystemExit(0)
    print(f"live evidence ok for every job entering {args.jobs}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()

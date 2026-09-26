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
  a closed vacancy; it simply does not confirm the job, so publication is held
  until an operator dispositions it.

The publication pipeline (services/ingestion/src/publish.py) applies the same
rules inside publishing itself, so no caller can bypass this gate.
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
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish gate for live-verified evidence")
    parser.add_argument("--jobs", type=Path, required=True, help="candidate job file about to be snapshotted")
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    args = parser.parse_args()

    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    missing = missing_live_evidence(
        jobs,
        load_evidence(args.evidence),
        max_age_days=args.max_age_days,
        now=datetime.now(timezone.utc),
    )
    if missing:
        print(f"publication held: {len(missing)} job(s) lack live evidence within {args.max_age_days} days")
        for job_id, reason in missing:
            print(f"  {job_id}: {reason}")
        print("Action: re-run verify_live_titles.py, or disposition the item (archive / re-source) in the ledger.")
        raise SystemExit(1)
    print(f"live evidence ok for every job entering {args.jobs}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()

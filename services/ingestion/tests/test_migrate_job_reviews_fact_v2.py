from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cli.migrate_job_reviews_fact_v2 import migrate  # noqa: E402
from publication_rules import job_fact_hash  # noqa: E402


def test_rebinds_only_from_the_exact_reviewed_record() -> None:
    window = {"id": "win-a", "ownerId": "job-a", "closesAt": "2026-10-30", "status": "open"}
    reviewed = {"id": "job-a", "paidStatus": "confirmed", "track": "postdoc"}
    later = {**reviewed, "paidStatus": "unconfirmed"}
    reviews = {"reviews": {
        "job-a": {"normalizationVersion": "fact-v1", "factHash": job_fact_hash(reviewed, [window], "fact-v1")},
        "job-b": {"normalizationVersion": "fact-v1", "factHash": "sha256:" + "0" * 64},
    }}
    # The candidate file holds a later reading; an older snapshot holds the reviewed one.
    baselines = [
        ("the candidate file", {"jobs": [later], "windows": [window]}),
        ("snapshot v1", {"jobs": [reviewed, {"id": "job-b"}], "windows": [window]}),
    ]
    result = migrate(reviews, baselines)

    assert result == {"rebound": ["job-a"], "unmatched": ["job-b"]}
    entry = reviews["reviews"]["job-a"]
    assert entry["normalizationVersion"] == "fact-v2"
    assert entry["factHash"] == job_fact_hash(reviewed, [{**window, "status": "closed"}], "fact-v2")
    assert "snapshot v1" in entry["reviewNote"]
    assert reviews["reviews"]["job-b"]["normalizationVersion"] == "fact-v1"

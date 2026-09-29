from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from build_incremental_job_review_queue import build_queue, markdown_packets  # noqa: E402


def test_only_changed_or_withheld_jobs_enter_operator_packets() -> None:
    jobs = {"generatedAt": "2026-09-29T10:00:00Z", "jobs": [
        {"id": "approved", "applicationUrl": "https://uni.cz/job/1", "sourceHash": "old",
         "translationStatus": "verified", "translationReview": {"factHash": "facts"}},
        {"id": "changed", "applicationUrl": "https://uni.cz/job/2", "sourceHash": "new",
         "translationStatus": "stale", "translationReview": {"factHash": "new-facts"}},
        {"id": "withheld", "applicationUrl": "https://uni.cz/job/3", "sourceHash": "old",
         "translationStatus": "verified", "translationReview": {"factHash": "facts"}},
    ]}
    ledger = {"candidateGenerationId": "generation", "rows": [
        {"candidateId": "approved", "employerId": "school", "decision": "approved_public", "blockers": []},
        {"candidateId": "changed", "employerId": "school", "decision": "blocked", "blockers": ["evidence_changed_since_review"]},
        {"candidateId": "withheld", "employerId": "school", "decision": "blocked", "blockers": []},
    ]}
    reviewed = {"sourceHash": "old", "factHash": "facts",
                "locales": {locale: {"status": "reviewed"} for locale in ("zh-CN", "en", "cs")}}
    queue = build_queue(jobs, ledger, {"reviews": {name: reviewed for name in ("approved", "changed", "withheld")}})
    assert queue["summary"]["unchangedApprovedCarriedForward"] == 1
    assert [p["candidateId"] for p in queue["packets"]] == ["changed", "withheld"]
    assert [p["action"] for p in queue["packets"]] == ["source_and_fact_re_review", "live_evidence_recheck"]
    assert queue["summary"]["diagnostics"] == 0
    assert "https://uni.cz/job/2" in markdown_packets(queue)


def test_missing_job_and_invalid_target_are_diagnostics_not_approvals() -> None:
    queue = build_queue(
        {"jobs": [{"id": "bad", "applicationUrl": "http://uni.cz/job/1", "translationStatus": "draft"}]},
        {"rows": [{"candidateId": "missing", "decision": "blocked"},
                  {"candidateId": "bad", "decision": "blocked"}]},
        {"reviews": {}},
    )
    assert queue["summary"]["pendingPackets"] == 0
    assert {d["reason"] for d in queue["diagnostics"]} == {"ledger_job_missing", "invalid_official_target"}

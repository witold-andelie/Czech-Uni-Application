"""A82/A83: deterministic tests for the source assessment and disposition ledger."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from build_disposition_ledger import build_ledger  # noqa: E402
from build_job_source_assessment import build_assessment  # noqa: E402


def _baseline(ids: list[tuple[str, str]]) -> dict:
    return {
        "institutions": [
            {"id": iid, "officialName": name, "ownership": "public"} for iid, name in ids
        ]
    }


def test_assessment_labels_all_54_states_honestly() -> None:
    baseline = _baseline(
        [
            ("msmt-vs_14000", "Masarykova univerzita"),
            ("msmt-vs_23000", "Západočeská univerzita v Plzni"),
            ("msmt-vs_13000", "Univerzita Jana Evangelisty Purkyně"),
        ]
    )
    registry = [
        {"id": "muni-careers", "sourceType": "official_job_listing", "employerId": "msmt-vs_14000", "url": "https://muni.test", "scope": "central"},
        {"id": "ujep-careers", "sourceType": "official_job_listing", "employerId": "msmt-vs_13000", "url": "https://ujep.test", "scope": "central"},
    ]
    schedule = {
        "sources": {
            "job-discovery:muni-careers": {"lastSuccessAt": "2026-09-11T20:25:25Z"},
            "job-discovery:ujep-careers": {"lastSuccessAt": None},
        }
    }
    payload = build_assessment(
        baseline,
        registry,
        schedule,
        {"jobs": []},
        {
            "activeVersion": "v2026-09-12.6",
            "snapshotDir": "snapshots/v2026-09-12.6",
            "candidateGenerationId": "cg-assess-1",
            "sourceRunSetDigest": "sha256:" + "0" * 64,
        },
        {},
        generated_at="2026-09-13T06:00:00Z",
    )
    assert len(payload["rows"]) == 3
    by_id = {row["institutionId"]: row for row in payload["rows"]}
    assert by_id["msmt-vs_14000"]["assessmentStatus"] == "registered_executed"
    assert by_id["msmt-vs_14000"]["latestSourceSuccessAt"] == "2026-09-11T20:25:25Z"
    assert by_id["msmt-vs_13000"]["assessmentStatus"] == "registered_never_executed"
    assert by_id["msmt-vs_23000"]["assessmentStatus"] == "not_assessed"
    assert payload["summary"] == {
        "registered_executed": 1,
        "registered_never_executed": 1,
        "assessed_no_central_source": 0,
        "not_assessed": 1,
    }
    assert payload["publicationVersion"] == "v2026-09-12.6"
    assert payload["candidateGenerationId"] == "cg-assess-1"
    assert payload["sourceRunSetDigest"] == "sha256:" + "0" * 64
    # The claim boundary explicitly denies whole-institution coverage.
    assert "No row claims whole-institution coverage" in payload["claimBoundary"]


def test_assessment_records_official_site_check_without_claiming_no_vacancies() -> None:
    payload = build_assessment(
        _baseline([("msmt-vs_x", "Small University")]),
        [],
        {"sources": {}},
        {"jobs": []},
        {"activeVersion": "v1"},
        {
            "rows": [
                {
                    "institutionId": "msmt-vs_x",
                    "checkedAt": "2026-09-17T12:00:00Z",
                    "nextCheckAt": "2026-09-22T12:00:00Z",
                    "method": "official_domain_search",
                    "evidenceUrls": ["https://small.example/"],
                    "result": "official_site_checked_no_central_listing",
                    "note": "No central public vacancy listing was found.",
                }
            ]
        },
        generated_at="2026-09-17T12:00:00Z",
    )
    row = payload["rows"][0]
    assert row["assessmentStatus"] == "assessed_no_central_source"
    assert row["assessmentEvidence"]["evidenceUrls"] == ["https://small.example/"]
    assert row["nextCheckAt"] == "2026-09-22T12:00:00Z"
    assert "not that the institution has no vacancies" in payload["claimBoundary"]


def test_disposition_ledger_one_decision_per_candidate() -> None:
    candidates = {
        "jobs": [
            {
                "id": "job-public",
                "employerId": "msmt-vs_14000",
                "originalText": "Research Specialist",
                "paidStatus": "confirmed",
                "minimumDegree": "master",
                "doctoralEnrollment": "unspecified",
                "catalogueScopeStatus": "included",
                "translationStatus": "verified",
                "visibility": "review_pending",
                "lifecycleStatus": "unknown",
            },
            {
                "id": "job-unpaid",
                "employerId": "msmt-vs_21000",
                "originalText": "PhD student",
                "paidStatus": "unconfirmed",
                "minimumDegree": "unknown",
                "doctoralEnrollment": "required",
                "catalogueScopeStatus": "included",
                "translationStatus": "unreviewed",
                "visibility": "review_pending",
                "lifecycleStatus": "unknown",
            },
            {
                "id": "job-scopeless",
                "employerId": "msmt-vs_41000",
                "originalText": "Assistant",
                "paidStatus": "confirmed",
                "minimumDegree": "master",
                "doctoralEnrollment": "not_required",
                "catalogueScopeStatus": None,
                "translationStatus": "unreviewed",
                "visibility": "review_pending",
                "lifecycleStatus": "unknown",
            },
        ],
        "windows": [
            {"ownerId": "job-unpaid", "closesAt": "2026-09-20"},
            {"ownerId": "job-public", "closesAt": "2027-01-08"},
        ],
    }
    payload = build_ledger(
        candidates,
        {"job-public"},
        {
            "activeVersion": "v2026-09-12.6",
            "snapshotDir": "snapshots/v2026-09-12.6",
            "candidateGenerationId": "cg-ledger-2",
            "sourceRunSetDigest": "sha256:" + "0" * 64,
        },
        generated_at="2026-09-13T06:00:00Z",
    )
    rows = {row["candidateId"]: row for row in payload["rows"]}
    assert rows["job-public"]["decision"] == "approved_public"
    assert rows["job-public"]["blockers"] == []
    assert rows["job-unpaid"]["decision"] == "blocked"
    assert "unconfirmed_pay_evidence" in rows["job-unpaid"]["blockers"]
    assert rows["job-scopeless"]["blockers"].count("unspecified_scope") == 1
    # Near deadlines sort first.
    assert payload["rows"][0]["candidateId"] == "job-unpaid"
    assert payload["summary"]["approved_public"] == 1
    assert payload["summary"]["blocked"] == 2
    assert payload["bySchool"]["msmt-vs_21000"]["blocked"] == 1
    assert payload["candidateGenerationId"] == "cg-ledger-2"
    assert payload["sourceRunSetDigest"] == "sha256:" + "0" * 64


def test_draft_translation_status_blocks_as_missing_review_not_evidence_change() -> None:
    candidates = {
        "jobs": [
            {
                "id": "job-draft",
                "employerId": "msmt-vs_14000",
                "originalText": "Výzkumný specialista",
                "paidStatus": "confirmed",
                "minimumDegree": "master",
                "doctoralEnrollment": "unspecified",
                "catalogueScopeStatus": "included",
                "translationStatus": "draft",
                "visibility": "review_pending",
                "lifecycleStatus": "unknown",
            },
        ],
        "windows": [],
    }
    payload = build_ledger(
        candidates,
        set(),
        {"activeVersion": "v2026-09-22.1"},
        generated_at="2026-09-22T09:00:00Z",
    )
    row = payload["rows"][0]
    assert row["decision"] == "blocked"
    assert "trilingual_review_missing" in row["blockers"]
    assert "evidence_changed_since_review" not in row["blockers"]
    assert payload["summary"]["blocked"] == 1

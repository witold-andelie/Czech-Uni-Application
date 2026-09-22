"""A82: versioned 54-row national job-source assessment.

This artifact separates honest states: a registered source that has executed,
a registered source that never ran, an official site assessment that found no
central public listing, and an institution not assessed at all. Connection-only
counts stay separate from executed coverage. It does not claim any institution
is fully covered or that a school has no vacancies.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
REGISTRY = ROOT / "data" / "sources" / "registry.json"
SCHEDULE = ROOT / "work" / "runs" / "schedule-state.json"
CANDIDATES = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
POINTER = ROOT / "data" / "published" / "current.json"
SOURCE_CHECKS = ROOT / "data" / "sources" / "job-source-checks.json"
OUT = ROOT / "data" / "sources" / "coverage" / "job-source-assessment.json"

JOB_SOURCE_TYPES = {"official_job_listing", "official_job_listing_candidate"}
ASSESSMENT_SCHEMA_VERSION = 2


def read_json(path: Path, default=None):
    if not path.exists() and default is not None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def build_assessment(
    baseline: dict,
    registry: list[dict],
    schedule: dict,
    candidates: dict,
    pointer: dict,
    source_checks: dict | None = None,
    generated_at: str | None = None,
) -> dict:
    institutions = baseline.get("institutions") or []
    job_sources = [
        row
        for row in registry
        if isinstance(row, dict) and row.get("sourceType") in JOB_SOURCE_TYPES
    ]
    sources_by_institution: dict[str, list[dict]] = {}
    for row in job_sources:
        employer = str(row.get("employerId") or "")
        sources_by_institution.setdefault(employer, []).append(row)

    state_sources = schedule.get("sources") or {}
    current_by_employer: dict[str, int] = {}
    public_by_employer: dict[str, int] = {}
    for job in candidates.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        employer = str(job.get("employerId") or "")
        if job.get("visibility") != "archived" and job.get("lifecycleStatus") not in {
            "closed",
            "expired",
            "unavailable",
        }:
            current_by_employer[employer] = current_by_employer.get(employer, 0) + 1
        if job.get("visibility") == "public":
            public_by_employer[employer] = public_by_employer.get(employer, 0) + 1

    checks_payload = source_checks or {}
    checks_by_institution = {
        str(row.get("institutionId") or ""): row
        for row in checks_payload.get("rows", [])
        if isinstance(row, dict) and row.get("institutionId")
    }
    rows = []
    for institution in institutions:
        institution_id = str(institution.get("id") or "")
        registered = []
        successes = []
        for source in sources_by_institution.get(institution_id, []):
            source_id = str(source.get("id") or "")
            state = state_sources.get(f"job-discovery:{source_id}") or {}
            last_success = state.get("lastSuccessAt")
            registered.append(
                {
                    "sourceId": source_id,
                    "url": source.get("url"),
                    "scope": source.get("scope"),
                    "parser": source.get("parser"),
                    "lastSuccessAt": last_success,
                    # A87/A86: a scheduler timestamp is execution evidence for
                    # this source's own URL; it is never whole-institution
                    # coverage.
                    "executionEvidence": "scheduler_success_timestamp" if last_success else "none",
                }
            )
            if last_success:
                successes.append(last_success)

        check = checks_by_institution.get(institution_id)
        if registered and successes:
            status = "registered_executed"
        elif registered:
            status = "registered_never_executed"
        elif check and check.get("result") == "official_site_checked_no_central_listing":
            # This is deliberately weaker than "no vacancies". It records a
            # completed official-domain channel check and schedules another.
            status = "assessed_no_central_source"
        else:
            # A82: honest label. It does not mean "no vacancies"; it means the
            # careers-channel assessment has not been performed yet.
            status = "not_assessed"
        rows.append(
            {
                "institutionId": institution_id,
                "officialName": institution.get("officialName"),
                "ownership": institution.get("ownership"),
                "assessmentStatus": status,
                "registeredSources": registered,
                "registeredSourceCount": len(registered),
                "sourcesWithSuccessCount": len(successes),
                "latestSourceSuccessAt": max(successes) if successes else None,
                "currentCandidates": current_by_employer.get(institution_id, 0),
                "publicJobs": public_by_employer.get(institution_id, 0),
                "assessmentEvidence": (
                    {
                        "checkedAt": check.get("checkedAt") or checks_payload.get("checkedAt"),
                        "method": check.get("method"),
                        "evidenceUrls": check.get("evidenceUrls") or [],
                        "result": check.get("result"),
                    }
                    if check
                    else None
                ),
                "nextCheckAt": (
                    check.get("nextCheckAt") or checks_payload.get("nextCheckAt")
                    if check
                    else None
                ),
                "notes": check.get("note") if check else None,
            }
        )

    counts = {
        "registered_executed": 0,
        "registered_never_executed": 0,
        "assessed_no_central_source": 0,
        "not_assessed": 0,
    }
    for row in rows:
        counts[row["assessmentStatus"]] += 1
    version = pointer.get("activeVersion") if isinstance(pointer, dict) else None
    return {
        "assessmentSchemaVersion": ASSESSMENT_SCHEMA_VERSION,
        "generatedAt": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "publicationVersion": version,
        "candidateGenerationId": pointer.get("candidateGenerationId") if isinstance(pointer, dict) else None,
        "sourceRunSetDigest": pointer.get("sourceRunSetDigest") if isinstance(pointer, dict) else None,
        "baselineInstitutions": len(institutions),
        "summary": counts,
        "claimBoundary": (
            "assessmentStatus labels honest pipeline state only: "
            "registered_executed means at least one registered source has a "
            "scheduler success timestamp; registered_never_executed means a "
            "source is registered but no successful run is recorded; "
            "assessed_no_central_source means an official-domain check found no "
            "central public vacancy listing at that time, not that the institution "
            "has no vacancies; "
            "not_assessed means no registered source exists and the "
            "careers-channel assessment has not happened. No row claims "
            "whole-institution vacancy coverage. No row claims whole-institution coverage; fully assessed scopes remain "
            "0 until documented per-institution scope assessments exist."
        ),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the 54-row job-source assessment")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--generated-at", type=str, default=None)
    args = parser.parse_args()
    pointer = read_json(POINTER, {})
    payload = build_assessment(
        read_json(BASELINE),
        read_json(REGISTRY, []),
        read_json(SCHEDULE, {}),
        read_json(CANDIDATES, {}),
        pointer if isinstance(pointer, dict) else {},
        read_json(SOURCE_CHECKS, {}),
        generated_at=args.generated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.output)
    print(
        json.dumps(
            {
                "rows": len(payload["rows"]),
                "summary": payload["summary"],
                "publicationVersion": payload["publicationVersion"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

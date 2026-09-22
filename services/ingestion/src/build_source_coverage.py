"""Build an auditable coverage report from the current official-source artifacts.

Coverage is deliberately split by claim.  A complete harvest of one directory
does not prove a complete admissions catalogue, and a successful job-source run
does not prove that every Czech HEI has a registered career source.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from source_types import JOB_LISTING_SOURCE_TYPES

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
REGISTRY = ROOT / "data" / "sources" / "registry.json"
STUDYIN = ROOT / "data" / "sources" / "admissions" / "studyin-programmes.json"
CZU_PROGRAMMES = ROOT / "data" / "sources" / "admissions" / "czu-english-programmes.json"
CZU_CZECH_PROGRAMMES = (
    ROOT / "data" / "sources" / "admissions" / "czu-czech-programmes.json"
)
CZU_DOCTORAL_PROGRAMMES = (
    ROOT / "data" / "sources" / "admissions" / "czu-doctoral-programmes.json"
)
CANDIDATE_JOBS = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
PUBLISHED_DIR = ROOT / "data" / "published"
CURRENT_META = PUBLISHED_DIR / "current.json"
SCHEDULE = ROOT / "work" / "runs" / "schedule-state.json"
OUT = ROOT / "data" / "sources" / "coverage" / "source-coverage.json"
JOB_SOURCE_ASSESSMENT = (
    ROOT / "data" / "sources" / "coverage" / "job-source-assessment.json"
)

CLOSED_LIFECYCLES = {"closed", "expired", "unavailable"}
COVERAGE_SCHEMA_VERSION = 2
PREDICATE_VERSION = "coverage-predicates-v2"


def read_json(path: Path, default: object | None = None) -> object:
    if not path.exists() and default is not None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def active_snapshot_snapshot_root(publication_pointer: dict | None) -> Path:
    pointer = publication_pointer or read_json(CURRENT_META)
    version = pointer.get("activeVersion") if isinstance(pointer, dict) else None
    relative = pointer.get("snapshotDir") if isinstance(pointer, dict) else None
    if isinstance(version, str) and relative == f"snapshots/{version}":
        return (PUBLISHED_DIR / relative).resolve()
    return (PUBLISHED_DIR / "current").resolve()


def active_snapshot() -> tuple[Path, dict]:
    pointer = read_json(CURRENT_META)
    if not isinstance(pointer, dict):
        raise ValueError("data/published/current.json must be an object")
    version = pointer.get("activeVersion")
    relative = pointer.get("snapshotDir")
    if not isinstance(version, str) or relative != f"snapshots/{version}":
        raise ValueError("data/published/current.json has an inconsistent active snapshot")
    root = (PUBLISHED_DIR / relative).resolve()
    if PUBLISHED_DIR.resolve() not in root.parents or not root.is_dir():
        raise ValueError("active publication snapshot is missing or outside data/published")
    return root, pointer


def records(payload: dict, key: str) -> list[dict]:
    value = payload.get(key, [])
    return list(value.values()) if isinstance(value, dict) else list(value)


def is_current_job(job: dict) -> bool:
    """Non-archived and not an explicit closed/expired/unavailable lifecycle.

    This is *not* the supported-scope predicate. Missing catalogueScopeStatus
    stays unspecified rather than being treated as included.
    """
    return (
        job.get("visibility") != "archived"
        and job.get("lifecycleStatus") not in CLOSED_LIFECYCLES
    )


def is_supported_candidate(job: dict) -> bool:
    return is_current_job(job) and job.get("catalogueScopeStatus") == "included"


def approved_reviewed_offerings(snapshot_root: Path) -> list[dict]:
    """Reviewed offerings formally published in the active immutable snapshot.

    These are the only programme publications that can be attributed back to a
    candidate source, via each offering's candidateIds.
    """
    payload = read_json(snapshot_root / "admissions" / "reviewed-offerings.json", {})
    if not isinstance(payload, dict):
        return []
    return [
        row
        for row in records(payload, "offerings")
        if isinstance(row, dict) and row.get("publicationStatus") == "approved"
    ]


def reviewed_offerings_from_candidates(reviewed: list[dict], candidate_ids: set[str]) -> list[str]:
    """Offerings whose candidateIds include at least one candidate of a source.

    One reviewed offering is counted once globally; per-source attribution can
    overlap when an offering cites candidates from more than one source.
    """
    attributed = []
    for row in reviewed:
        ids = row.get("candidateIds")
        if isinstance(ids, list) and any(item in candidate_ids for item in ids):
            attributed.append(str(row.get("id") or ""))
    return sorted(item for item in attributed if item)


def matches_paid_master_facts(job: dict) -> bool:
    return (
        job.get("paidStatus") == "confirmed"
        and job.get("minimumDegree") in {"bachelor", "master"}
        and job.get("doctorateRequired") is False
        and not job.get("isPostdoc")
    )


def matches_paid_master_scope(job: dict) -> bool:
    return is_current_job(job) and matches_paid_master_facts(job)


def percent(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100) if denominator else 0.0, 1)


def build_coverage(
    baseline: dict,
    registry: list[dict],
    studyin: dict,
    candidate_jobs_payload: dict,
    published_jobs_payload: dict,
    published_inventory: dict,
    schedule: dict,
    czu_programmes: dict | None = None,
    czu_czech_programmes: dict | None = None,
    czu_doctoral_programmes: dict | None = None,
    *,
    generated_at: str | None = None,
    publication_pointer: dict | None = None,
    job_source_assessment: dict | None = None,
) -> dict:
    institutions = baseline.get("institutions", [])
    institution_by_id = {row["id"]: row for row in institutions}
    denominator = len(institutions)

    job_sources = [
        source
        for source in registry
        if source.get("official") is True
        and source.get("sourceType") in JOB_LISTING_SOURCE_TYPES
        and source.get("enabled", True) is not False
        and isinstance(source.get("parser"), str)
    ]
    mapped_sources = [source for source in job_sources if source.get("employerId") in institution_by_id]
    non_hei_sources = [source for source in job_sources if source not in mapped_sources]
    scope_counts: dict[str, int] = {}
    for source in job_sources:
        scope = str(source.get("coverageScope") or "unspecified")
        scope_counts[scope] = scope_counts.get(scope, 0) + 1
    sources_by_employer: dict[str, list[dict]] = {}
    for source in mapped_sources:
        sources_by_employer.setdefault(source["employerId"], []).append(source)

    candidate_jobs = records(candidate_jobs_payload, "jobs")
    published_jobs = records(published_jobs_payload, "jobs")
    current_candidates = [job for job in candidate_jobs if is_current_job(job)]
    supported_candidates = [job for job in candidate_jobs if is_supported_candidate(job)]
    unspecified_scope_candidates = [
        job for job in current_candidates if job.get("catalogueScopeStatus") not in {"included", "excluded"}
    ]
    review_pending = [
        job for job in supported_candidates if job.get("publicationStatus") == "review_pending" or job.get("visibility") == "review_pending"
    ]
    approved_candidates = [job for job in supported_candidates if job.get("publicationStatus") == "approved"]
    public_candidates = [job for job in published_jobs if job.get("visibility") == "public"]
    current_open = [
        job
        for job in supported_candidates
        if job.get("lifecycleStatus") in {"open", "unknown", None}
    ]
    paid_master_candidates = [job for job in current_candidates if matches_paid_master_facts(job)]
    supported_paid_master_candidates = [job for job in supported_candidates if matches_paid_master_facts(job)]
    paid_master_published = [
        job
        for job in published_jobs
        if matches_paid_master_scope(job) and job.get("visibility") == "public"
    ]

    schedule_sources = schedule.get("sources", {})
    institution_rows = []
    for institution in sorted(institutions, key=lambda row: row["id"]):
        institution_id = institution["id"]
        sources = sources_by_employer.get(institution_id, [])
        institution_rows.append(
            {
                "institutionId": institution_id,
                "officialName": institution.get("officialName"),
                "ownership": institution.get("ownership"),
                "registeredOfficialJobSource": bool(sources),
                "sources": [
                    {
                        "sourceId": source["id"],
                        "url": source["url"],
                        "coverageScope": source.get("coverageScope", "unspecified"),
                        "sourceCoverageClaim": source.get("sourceCoverageClaim", "not_asserted"),
                        "lastSuccessAt": schedule_sources.get(
                            f"job-discovery:{source['id']}", {}
                        ).get("lastSuccessAt"),
                    }
                    for source in sources
                ],
                "currentCandidateJobs": sum(
                    job.get("employerId") == institution_id for job in current_candidates
                ),
                "currentPaidMasterScopeCandidates": sum(
                    job.get("employerId") == institution_id for job in paid_master_candidates
                ),
                "publishedPaidMasterScopeJobs": sum(
                    job.get("employerId") == institution_id for job in paid_master_published
                ),
            }
        )

    mapped_institution_ids = set(sources_by_employer)
    aggregator_institution_ids = {
        source["employerId"]
        for source in mapped_sources
        if source.get("coverageScope") == "institution_aggregator"
    }
    faculty_institution_ids = {
        source["employerId"]
        for source in mapped_sources
        if source.get("coverageScope") == "faculty"
    }
    asserted_complete_institution_ids = {
        source["employerId"]
        for source in mapped_sources
        if source.get("sourceCoverageClaim") == "complete"
    }
    assessment = job_source_assessment or {}
    assessment_rows = [
        row
        for row in assessment.get("rows", [])
        if isinstance(row, dict) and row.get("institutionId") in institution_by_id
    ]
    assessment_status_counts = {
        "registered_executed": 0,
        "registered_never_executed": 0,
        "assessed_no_central_source": 0,
        "not_assessed": 0,
    }
    for row in assessment_rows:
        status = row.get("assessmentStatus")
        if status in assessment_status_counts:
            assessment_status_counts[status] += 1
    assessed_baseline_institutions = sum(
        count
        for status, count in assessment_status_counts.items()
        if status != "not_assessed"
    )
    studyin_counts = studyin.get("counts", {})
    studyin_coverage = studyin.get("coverage", {})
    inventory_counts = published_inventory.get("counts", {})
    job_discovery = schedule.get("jobDiscovery", {})
    programme_availability = schedule.get("programmeAvailability", {})
    czu_programme_availability = schedule.get("czuProgrammeAvailability", {})
    czu_czech_programme_availability = schedule.get(
        "czuCzechProgrammeAvailability", {}
    )
    czu_doctoral_programme_availability = schedule.get(
        "czuDoctoralProgrammeAvailability", {}
    )
    czu_programmes = czu_programmes or {}
    czu_counts = czu_programmes.get("counts", {})
    czu_coverage = czu_programmes.get("coverage", {})
    czu_czech_programmes = czu_czech_programmes or {}
    czu_czech_counts = czu_czech_programmes.get("counts", {})
    czu_czech_coverage = czu_czech_programmes.get("coverage", {})
    czu_doctoral_programmes = czu_doctoral_programmes or {}
    czu_doctoral_counts = czu_doctoral_programmes.get("counts", {})
    czu_doctoral_coverage = czu_doctoral_programmes.get("coverage", {})
    # A77: publication attribution is a join, not a constant. Reviewed
    # offerings cite candidateIds; an offering is attributed to a candidate
    # source when at least one cited candidate belongs to that source. One
    # offering counts once globally; per-source attribution may overlap and the
    # report says so.
    reviewed_offerings = approved_reviewed_offerings(
        active_snapshot_snapshot_root(publication_pointer)
    )
    reviewed_published_globally = len(reviewed_offerings)
    attribution_note = (
        "formallyPublishedFromThisCandidateSource joins approved reviewed "
        "offerings' candidateIds to this source's candidate ids. The global "
        "reviewed count counts each offering once; per-source attribution can "
        "overlap when an offering cites candidates from several sources."
    )
    czu_english_candidate_ids = {
        str(row.get("id") or "")
        for row in records(czu_programmes, "programmes")
        if isinstance(row, dict) and row.get("id")
    }
    czu_czech_candidate_ids = {
        str(row.get("id") or "")
        for row in records(czu_czech_programmes, "programmes")
        if isinstance(row, dict) and row.get("id")
    }
    czu_doctoral_candidate_ids = {
        str(row.get("id") or "")
        for row in records(czu_doctoral_programmes, "programmes")
        if isinstance(row, dict) and row.get("id")
    }
    czu_english_published = reviewed_offerings_from_candidates(
        reviewed_offerings, czu_english_candidate_ids
    )
    czu_czech_published = reviewed_offerings_from_candidates(
        reviewed_offerings, czu_czech_candidate_ids
    )
    czu_doctoral_published = reviewed_offerings_from_candidates(
        reviewed_offerings, czu_doctoral_candidate_ids
    )
    job_recheck = schedule.get("jobRecheck", {})
    discovery = candidate_jobs_payload.get("discovery") if isinstance(candidate_jobs_payload.get("discovery"), dict) else {}
    complete_source_ids = set(discovery.get("completeSourceIds") or [])
    expected_source_ids = list(discovery.get("expectedSourceIds") or [])
    # A77: bind each source to its own recorded attempt state.
    per_source_attempts: dict[str, dict] = {}
    for attempt in discovery.get("attempts") or []:
        if not isinstance(attempt, dict):
            continue
        source_id = str(attempt.get("sourceId") or "")
        if not source_id:
            continue
        entry = per_source_attempts.setdefault(
            source_id,
            {"sourceId": source_id, "attempts": 0, "failedAttempts": 0},
        )
        entry["attempts"] += 1
        if attempt.get("ok") is not True:
            entry["failedAttempts"] += 1
        if not entry.get("lastAttemptAt") and attempt.get("attemptedAt"):
            entry["lastAttemptAt"] = attempt.get("attemptedAt")
    per_source_run_status = []
    registry_by_id = {str(row.get("id") or ""): row for row in registry if isinstance(row, dict)}
    for source_id in expected_source_ids:
        entry = per_source_attempts.get(source_id, {})
        registry_row = registry_by_id.get(source_id, {})
        per_source_run_status.append(
            {
                "sourceId": source_id,
                "parserVersion": registry_row.get("parser"),
                "attempted": bool(entry),
                "attempts": entry.get("attempts", 0),
                "failedAttempts": entry.get("failedAttempts", 0),
                "lastAttemptAt": entry.get("lastAttemptAt"),
                "runComplete": source_id in complete_source_ids,
                "overdue": bool(entry) is False or source_id not in complete_source_ids,
            }
        )
    run_kind = discovery.get("runKind") or "unknown_legacy"
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    publication_version = (publication_pointer or {}).get("activeVersion")
    report_is_historical = False
    last_all_source_success = job_discovery.get("lastAllSourceSuccessAt")
    if run_kind == "all_registered_sources" and not last_all_source_success:
        last_all_source_success = job_discovery.get("lastSuccessAt")

    return {
        "generatedAt": generated_at,
        "dataClass": "operational_coverage_audit",
        "catalogKind": "coverage_evidence_not_opportunity_publication",
        "schemaVersion": COVERAGE_SCHEMA_VERSION,
        "predicateVersion": PREDICATE_VERSION,
        "predicates": {
            "currentJob": "visibility != archived AND lifecycleStatus not in {closed, expired, unavailable}",
            "supportedCandidate": "currentJob AND catalogueScopeStatus == included",
            "unspecifiedScope": "currentJob AND catalogueScopeStatus not in {included, excluded}",
            "paidMaster": "currentJob AND paid confirmed AND bachelor/master threshold AND doctorateRequired is false AND not postdoc",
            "supportedPaidMaster": "supportedCandidate AND the paidMaster facts",
        },
        "publication": {
            "activeVersion": publication_version,
            "publishedAt": (publication_pointer or {}).get("publishedAt"),
            "candidateGenerationId": (publication_pointer or {}).get("candidateGenerationId"),
            "sourceRunSetDigest": (publication_pointer or {}).get("sourceRunSetDigest"),
            "reportBoundToActiveVersion": True,
            "historical": report_is_historical,
        },
        "baseline": {
            "sourceId": "msmt-register",
            "sourceUrl": baseline.get("sourceUrl"),
            "sourceGeneratedAt": baseline.get("generatedAt"),
            "institutions": denominator,
        },
        "programmes": {
            "directorySourceId": "studyin",
            "sourceGeneratedAt": studyin.get("generatedAt"),
            "lastScheduledSuccessAt": programme_availability.get("lastSuccessAt"),
            "refreshIntervalHours": programme_availability.get("intervalHours", 2),
            "directoryRecords": studyin_counts.get("programmes", 0),
            "mappedInstitutions": studyin_counts.get("institutions", 0),
            "baselineInstitutionCoveragePercent": percent(
                int(studyin_counts.get("institutions", 0)), denominator
            ),
            "unmappedRecords": studyin_counts.get("unmappedProgrammes", 0),
            "directoryHarvestComplete": studyin_coverage.get("complete") is True,
            "englishCzechUuidSetsMatch": studyin_coverage.get("localeUuidSetsMatch") is True,
            "directoryReportsApplicationsOpen": studyin_counts.get("openApplications", 0),
            "displayedRegisterInventoryRecords": inventory_counts.get("programmes", 0),
            "displayedRegisterInventoryInstitutions": inventory_counts.get("schools", 0),
            "completeAdmissionsCatalogueClaim": False,
            "priorityInstitutionSources": {
                "czuEnglishBachelorMaster": {
                    "sourceId": "czu-study-english-programmes",
                    "institutionId": "msmt-vs_41000",
                    "sourceGeneratedAt": czu_programmes.get("generatedAt"),
                    "lastScheduledSuccessAt": czu_programme_availability.get("lastSuccessAt"),
                    "refreshIntervalHours": czu_programme_availability.get("intervalHours", 2),
                    "declaredScope": "English bachelor and master programmes on study.czu.cz",
                    "sourceCatalogueRecords": czu_counts.get("programmes", 0),
                    "detailsWithCompleteWindow": czu_counts.get("detailsWithCompleteWindow", 0),
                    "openByDetailDates": czu_counts.get("openByDetailDates", 0),
                    "upcomingByDetailDates": czu_counts.get("upcomingByDetailDates", 0),
                    "closedByDetailDates": czu_counts.get("closedByDetailDates", 0),
                    "openPageReported": czu_counts.get("openPageReported", 0),
                    "declaredScopeHarvestComplete": czu_coverage.get("complete") is True,
                    "availabilityCrosscheck": czu_coverage.get("availabilityCrosscheck"),
                    "formallyPublishedFromThisCandidateSource": len(czu_english_published),
                    "formallyPublishedOfferingIds": czu_english_published,
                    "reviewedOfferingsPublishedGlobally": reviewed_published_globally,
                    "publicationAttributionBasis": attribution_note,
                    "claimBoundary": (
                        "This is a complete read only for CZU's declared English bachelor/master "
                        "source scope. It excludes Czech-taught and doctoral programmes and remains "
                        "outside formal publication until zh-CN/en/cs source-bound review passes."
                    ),
                },
                "czuCzechAndEnglishBachelorMaster": {
                    "sourceId": "czu-studuj-bachelor-master-programmes",
                    "institutionId": "msmt-vs_41000",
                    "sourceGeneratedAt": czu_czech_programmes.get("generatedAt"),
                    "lastScheduledSuccessAt": czu_czech_programme_availability.get(
                        "lastSuccessAt"
                    ),
                    "refreshIntervalHours": czu_czech_programme_availability.get(
                        "intervalHours", 2
                    ),
                    "declaredScope": (
                        "Czech- and English-taught bachelor and master programmes on studuj.czu.cz"
                    ),
                    "sourceCatalogueRecords": czu_czech_counts.get("programmes", 0),
                    "teachingLanguageCounts": czu_czech_counts.get(
                        "teachingLanguages", {}
                    ),
                    "degreeCounts": czu_czech_counts.get("degrees", {}),
                    "detailsWithCompleteWindow": czu_czech_counts.get(
                        "detailsWithCompleteWindow", 0
                    ),
                    "openByDetailDates": czu_czech_counts.get(
                        "openByDetailDates", 0
                    ),
                    "upcomingByDetailDates": czu_czech_counts.get(
                        "upcomingByDetailDates", 0
                    ),
                    "closedByDetailDates": czu_czech_counts.get(
                        "closedByDetailDates", 0
                    ),
                    "unknownByDetailDates": czu_czech_counts.get(
                        "unknownByDetailDates", 0
                    ),
                    "homepageReportedTotal": czu_czech_coverage.get(
                        "homepageReportedTotal", 0
                    ),
                    "sitemapDetailTotal": czu_czech_coverage.get(
                        "sitemapDetailTotal", 0
                    ),
                    "declaredScopeHarvestComplete": czu_czech_coverage.get("complete")
                    is True,
                    "englishSourceCrosscheck": czu_czech_coverage.get(
                        "englishSourceCrosscheck", {}
                    ).get("status"),
                    "formallyPublishedFromThisCandidateSource": len(czu_czech_published),
                    "formallyPublishedOfferingIds": czu_czech_published,
                    "reviewedOfferingsPublishedGlobally": reviewed_published_globally,
                    "publicationAttributionBasis": attribution_note,
                    "claimBoundary": (
                        "This is a complete read only for the bachelor/master catalogue exposed by "
                        "studuj.czu.cz. It excludes doctoral programmes and remains outside formal "
                        "publication until zh-CN/en/cs source-bound review passes."
                    ),
                },
                "czuDoctoral": {
                    "sourceId": "czu-doctoral-faculty-admissions",
                    "institutionId": "msmt-vs_41000",
                    "sourceGeneratedAt": czu_doctoral_programmes.get("generatedAt"),
                    "lastScheduledSuccessAt": czu_doctoral_programme_availability.get(
                        "lastSuccessAt"
                    ),
                    "refreshIntervalHours": czu_doctoral_programme_availability.get(
                        "intervalHours", 2
                    ),
                    "declaredScope": czu_doctoral_coverage.get("declaredScope"),
                    "academicYear": czu_doctoral_programmes.get("academicYear"),
                    "registerBaselineOfferings": czu_doctoral_coverage.get(
                        "baselineOfferings", 0
                    ),
                    "matchedFacultyEvidenceOfferings": czu_doctoral_counts.get(
                        "matchedToFacultyAdmissionEvidence", 0
                    ),
                    "facultiesWithProgrammeAndWindowEvidence": czu_doctoral_coverage.get(
                        "facultiesWithProgrammeAndWindowEvidence", 0
                    ),
                    "teachingLanguageCounts": czu_doctoral_counts.get(
                        "teachingLanguages", {}
                    ),
                    "withAnyOfficialWindow": czu_doctoral_counts.get(
                        "withAnyOfficialWindow", 0
                    ),
                    "withAtLeastOneCompleteWindow": czu_doctoral_counts.get(
                        "withAtLeastOneCompleteWindow", 0
                    ),
                    "openByOfficialDates": czu_doctoral_counts.get(
                        "openByOfficialDates", 0
                    ),
                    "upcomingByOfficialDates": czu_doctoral_counts.get(
                        "upcomingByOfficialDates", 0
                    ),
                    "closedByOfficialDates": czu_doctoral_counts.get(
                        "closedByOfficialDates", 0
                    ),
                    "unknownByOfficialDates": czu_doctoral_counts.get(
                        "unknownByOfficialDates", 0
                    ),
                    "awaitingNextAcademicYearWindow": czu_doctoral_counts.get(
                        "awaitingNextAcademicYearWindow", 0
                    ),
                    "declaredScopeHarvestComplete": czu_doctoral_coverage.get("complete")
                    is True,
                    "allApplicationWindowsClosedAtFetch": czu_doctoral_coverage.get(
                        "allApplicationWindowsClosedAtFetch"
                    ),
                    "formallyPublishedFromThisCandidateSource": len(czu_doctoral_published),
                    "formallyPublishedOfferingIds": czu_doctoral_published,
                    "reviewedOfferingsPublishedGlobally": reviewed_published_globally,
                    "publicationAttributionBasis": attribution_note,
                    "claimBoundary": czu_doctoral_coverage.get("claimBoundary")
                    or (
                        "This candidate cross-check is limited to CZU doctoral offerings in the "
                        "current MŠMT baseline and configured faculty evidence. It remains outside "
                        "formal publication until zh-CN/en/cs source-bound review passes."
                    ),
                },
            },
            "claimBoundary": (
                "The DZS source snapshot is complete for its reported directory result, but it is not "
                "the legal register or the authority for each university application window. Candidate "
                "records remain outside formal publication until source and zh-CN/en/cs review passes."
            ),
        },
        "jobs": {
            "registeredOfficialListingSources": len(job_sources),
            "lastRunCompleteSources": len(complete_source_ids.intersection({s["id"] for s in job_sources})),
            "lastDiscoverySuccessAt": job_discovery.get("lastSuccessAt"),
            "discoveryIntervalHours": job_discovery.get("intervalHours", 4),
            "lastStatusRecheckSuccessAt": job_recheck.get("lastSuccessAt"),
            "statusRecheckIntervalHours": job_recheck.get("intervalHours", 1),
            "mappedBaselineInstitutions": len(mapped_institution_ids),
            "baselineInstitutionCoveragePercent": percent(len(mapped_institution_ids), denominator),
            "baselineInstitutionsWithoutRegisteredSource": denominator - len(mapped_institution_ids),
            "assessedBaselineInstitutions": assessed_baseline_institutions,
            "notAssessedBaselineInstitutions": max(
                denominator - assessed_baseline_institutions, 0
            ),
            "assessmentStatusCounts": assessment_status_counts,
            "institutionAggregatorConnections": len(aggregator_institution_ids),
            "facultyOnlyConnections": len(faculty_institution_ids - aggregator_institution_ids),
            "assertedCompleteInstitutionSources": len(asserted_complete_institution_ids),
            "coverageScopeCounts": scope_counts,
            "independentNonHeiOfficialSources": len(non_hei_sources),
            "inventoryRows": int(inventory_counts.get("programmes") or 0),
            "discoveredCandidates": len(candidate_jobs),
            "currentCandidates": len(current_candidates),
            "supportedCandidates": len(supported_candidates),
            "unspecifiedScopeCandidates": len(unspecified_scope_candidates),
            "reviewPending": len(review_pending),
            "approved": len(approved_candidates),
            "public": len(public_candidates),
            "currentOpenOrUnknown": len(current_open),
            "currentPaidMasterScopeCandidates": len(paid_master_candidates),
            "supportedPaidMasterScopeCandidates": len(supported_paid_master_candidates),
            "publishedRecords": len(published_jobs),
            "publishedPaidMasterScopeJobs": len(paid_master_published),
            "sourceConnectedSchools": len(mapped_institution_ids),
            "fullyAssessedSchoolScope": len(asserted_complete_institution_ids),
            "missingInstitutions": [
                {
                    "institutionId": row["institutionId"],
                    "officialName": row["officialName"],
                    "ownership": row["ownership"],
                }
                for row in institution_rows
                if not row["registeredOfficialJobSource"]
            ],
            "lastDiscoveryRun": {
                "runKind": run_kind,
                "expectedSourceIds": expected_source_ids,
                "completeSourceIds": sorted(complete_source_ids),
                "deferredSourceIds": list(discovery.get("deferredSourceIds") or []),
                "lastScheduledSuccessAt": job_discovery.get("lastSuccessAt"),
                "lastAllSourceSuccessAt": last_all_source_success,
                "singleSourceRefreshCannotCountAsAllSourceSuccess": run_kind != "all_registered_sources",
                # A77: per-source state comes from recorded attempts only. A
                # global run timestamp is never copied onto sources without an
                # actual successful attempt of their own.
                "perSourceRunStatus": per_source_run_status,
            },
            "completeSchoolJobCoverageClaim": False,
            "claimBoundary": (
                "A successful run covers only registered official listings. A central aggregator "
                "connection is not an institution-wide completeness claim, and a faculty source is "
                "only partial. An official-domain check that found no central listing records an "
                "assessed discovery channel, not zero vacancies. Assessed-institution and "
                "source-connected counts are separate; unregistered institutions and units may "
                "still have vacancies."
            ),
            "nonHeiSources": [
                {"sourceId": source["id"], "url": source["url"]} for source in non_hei_sources
            ],
            "institutions": institution_rows,
        },
    }


def write_current_coverage(*, output: Path = OUT, generated_at: str | None = None) -> dict:
    snapshot, pointer = active_snapshot()
    payload = build_coverage(
        read_json(BASELINE),
        read_json(REGISTRY),
        read_json(STUDYIN),
        read_json(CANDIDATE_JOBS),
        read_json(snapshot / "browse" / "nine-hei-jobs.json"),
        read_json(snapshot / "browse" / "nine-hei-inventory.json"),
        read_json(SCHEDULE, {}),
        read_json(CZU_PROGRAMMES, {}),
        read_json(CZU_CZECH_PROGRAMMES, {}),
        read_json(CZU_DOCTORAL_PROGRAMMES, {}),
        generated_at=generated_at,
        publication_pointer=pointer,
        job_source_assessment=read_json(JOB_SOURCE_ASSESSMENT, {}),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the current source coverage audit")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    payload = write_current_coverage(output=args.output, generated_at=args.generated_at)
    print(
        json.dumps(
            {
                "generatedAt": payload["generatedAt"],
                "publicationVersion": payload["publication"]["activeVersion"],
                "programmeDirectoryRecords": payload["programmes"]["directoryRecords"],
                "registeredJobSources": payload["jobs"]["registeredOfficialListingSources"],
                "jobSourceInstitutions": payload["jobs"]["mappedBaselineInstitutions"],
                "jobInstitutionCoveragePercent": payload["jobs"]["baselineInstitutionCoveragePercent"],
                "currentCandidates": payload["jobs"]["currentCandidates"],
                "supportedCandidates": payload["jobs"]["supportedCandidates"],
                "currentPaidMasterScopeCandidates": payload["jobs"]["currentPaidMasterScopeCandidates"],
                "publishedPaidMasterScopeJobs": payload["jobs"]["publishedPaidMasterScopeJobs"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

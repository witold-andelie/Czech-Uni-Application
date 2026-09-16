from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from build_source_coverage import build_coverage  # noqa: E402


def test_coverage_keeps_directory_completeness_separate_from_admissions_and_job_claims() -> None:
    baseline = {
        "generatedAt": "2026-09-01T00:00:00Z",
        "sourceUrl": "https://example.test/register",
        "institutions": [
            {"id": "hei-1", "officialName": "One", "ownership": "public"},
            {"id": "hei-2", "officialName": "Two", "ownership": "private"},
        ],
    }
    registry = [
        {
            "id": "jobs-one",
            "url": "https://one.test/jobs",
            "official": True,
            "sourceType": "official_job_listing",
            "parser": "test",
            "employerId": "hei-1",
            "coverageScope": "faculty",
            "sourceCoverageClaim": "not_asserted",
        },
        {
            "id": "research-network",
            "url": "https://network.test/jobs",
            "official": True,
            "sourceType": "official_job_listing",
            "parser": "test",
            "employerId": None,
            "coverageScope": "research_network",
            "sourceCoverageClaim": "not_asserted",
        },
    ]
    candidate_job = {
        "id": "job-1",
        "employerId": "hei-1",
        "visibility": "review_pending",
        "catalogueScopeStatus": "included",
        "publicationStatus": "review_pending",
        "lifecycleStatus": "open",
        "paidStatus": "confirmed",
        "minimumDegree": "master",
        "doctorateRequired": False,
        "isPostdoc": False,
    }
    published_job = {**candidate_job, "visibility": "public"}
    report = build_coverage(
        baseline,
        registry,
        {
            "generatedAt": "2026-09-10T00:00:00Z",
            "counts": {"programmes": 10, "institutions": 2, "unmappedProgrammes": 0},
            "coverage": {"complete": True, "localeUuidSetsMatch": True},
        },
        {"jobs": [candidate_job], "discovery": {"completeSourceIds": ["jobs-one", "research-network"]}},
        {"jobs": [published_job]},
        {"counts": {"programmes": 8, "schools": 1}},
        {
            "jobDiscovery": {"lastSuccessAt": "2026-09-10T01:00:00Z"},
            "czuProgrammeAvailability": {
                "lastSuccessAt": "2026-09-10T01:30:00Z",
                "intervalHours": 2,
            },
            "czuCzechProgrammeAvailability": {
                "lastSuccessAt": "2026-09-10T01:45:00Z",
                "intervalHours": 2,
            },
            "czuDoctoralProgrammeAvailability": {
                "lastSuccessAt": "2026-09-10T01:50:00Z",
                "intervalHours": 2,
            },
            "sources": {"job-discovery:jobs-one": {"lastSuccessAt": "2026-09-10T01:00:00Z"}},
        },
        {
            "generatedAt": "2026-09-10T01:30:00Z",
            "counts": {
                "programmes": 36,
                "detailsWithCompleteWindow": 36,
                "openByDetailDates": 0,
                "upcomingByDetailDates": 35,
                "closedByDetailDates": 1,
                "openPageReported": 0,
            },
            "coverage": {
                "complete": True,
                "availabilityCrosscheck": "agrees",
            },
        },
        {
            "generatedAt": "2026-09-10T01:45:00Z",
            "counts": {
                "programmes": 129,
                "degrees": {"bachelor": 68, "master": 61},
                "teachingLanguages": {"cs": 93, "en": 36},
                "detailsWithCompleteWindow": 128,
                "openByDetailDates": 4,
                "upcomingByDetailDates": 90,
                "closedByDetailDates": 34,
                "unknownByDetailDates": 1,
            },
            "coverage": {
                "homepageReportedTotal": 129,
                "sitemapDetailTotal": 129,
                "complete": True,
                "englishSourceCrosscheck": {"status": "agrees"},
            },
        },
        {
            "generatedAt": "2026-09-10T01:50:00Z",
            "academicYear": "2026/2027",
            "counts": {
                "programmes": 60,
                "faculties": 6,
                "teachingLanguages": {"cs": 30, "en": 30},
                "matchedToFacultyAdmissionEvidence": 60,
                "withAnyOfficialWindow": 60,
                "withAtLeastOneCompleteWindow": 34,
                "openByOfficialDates": 0,
                "upcomingByOfficialDates": 0,
                "closedByOfficialDates": 60,
                "unknownByOfficialDates": 0,
                "awaitingNextAcademicYearWindow": 60,
            },
            "coverage": {
                "complete": True,
                "declaredScope": "MŠMT baseline plus six faculties",
                "baselineOfferings": 60,
                "facultiesWithProgrammeAndWindowEvidence": 6,
                "allApplicationWindowsClosedAtFetch": True,
                "claimBoundary": "2026/2027 evidence only; candidate review required.",
            },
        },
        generated_at="2026-09-10T02:00:00Z",
        job_source_assessment={
            "rows": [
                {"institutionId": "hei-1", "assessmentStatus": "registered_executed"},
                {
                    "institutionId": "hei-2",
                    "assessmentStatus": "assessed_no_central_source",
                },
            ]
        },
    )

    assert report["programmes"]["directoryHarvestComplete"] is True
    assert report["programmes"]["baselineInstitutionCoveragePercent"] == 100.0
    assert report["programmes"]["completeAdmissionsCatalogueClaim"] is False
    czu = report["programmes"]["priorityInstitutionSources"]["czuEnglishBachelorMaster"]
    assert czu["sourceCatalogueRecords"] == 36
    assert czu["detailsWithCompleteWindow"] == 36
    assert czu["declaredScopeHarvestComplete"] is True
    assert czu["formallyPublishedFromThisCandidateSource"] == 0
    assert "excludes Czech-taught and doctoral programmes" in czu["claimBoundary"]
    czu_czech = report["programmes"]["priorityInstitutionSources"][
        "czuCzechAndEnglishBachelorMaster"
    ]
    assert czu_czech["sourceCatalogueRecords"] == 129
    assert czu_czech["teachingLanguageCounts"] == {"cs": 93, "en": 36}
    assert czu_czech["detailsWithCompleteWindow"] == 128
    assert czu_czech["homepageReportedTotal"] == 129
    assert czu_czech["sitemapDetailTotal"] == 129
    assert czu_czech["declaredScopeHarvestComplete"] is True
    assert czu_czech["englishSourceCrosscheck"] == "agrees"
    assert czu_czech["formallyPublishedFromThisCandidateSource"] == 0
    assert "excludes doctoral programmes" in czu_czech["claimBoundary"]
    czu_doctoral = report["programmes"]["priorityInstitutionSources"]["czuDoctoral"]
    assert czu_doctoral["academicYear"] == "2026/2027"
    assert czu_doctoral["registerBaselineOfferings"] == 60
    assert czu_doctoral["matchedFacultyEvidenceOfferings"] == 60
    assert czu_doctoral["facultiesWithProgrammeAndWindowEvidence"] == 6
    assert czu_doctoral["teachingLanguageCounts"] == {"cs": 30, "en": 30}
    assert czu_doctoral["openByOfficialDates"] == 0
    assert czu_doctoral["closedByOfficialDates"] == 60
    assert czu_doctoral["declaredScopeHarvestComplete"] is True
    assert czu_doctoral["formallyPublishedFromThisCandidateSource"] == 0
    assert report["jobs"]["registeredOfficialListingSources"] == 2
    assert report["jobs"]["mappedBaselineInstitutions"] == 1
    assert report["jobs"]["baselineInstitutionCoveragePercent"] == 50.0
    assert report["jobs"]["baselineInstitutionsWithoutRegisteredSource"] == 1
    assert report["jobs"]["assessedBaselineInstitutions"] == 2
    assert report["jobs"]["notAssessedBaselineInstitutions"] == 0
    assert report["jobs"]["assessmentStatusCounts"] == {
        "registered_executed": 1,
        "registered_never_executed": 0,
        "assessed_no_central_source": 1,
        "not_assessed": 0,
    }
    assert "not zero vacancies" in report["jobs"]["claimBoundary"]
    assert report["jobs"]["institutionAggregatorConnections"] == 0
    assert report["jobs"]["facultyOnlyConnections"] == 1
    assert report["jobs"]["assertedCompleteInstitutionSources"] == 0
    assert report["jobs"]["coverageScopeCounts"] == {"faculty": 1, "research_network": 1}
    assert report["jobs"]["independentNonHeiOfficialSources"] == 1
    assert report["jobs"]["currentPaidMasterScopeCandidates"] == 1
    assert report["jobs"]["completeSchoolJobCoverageClaim"] is False
    assert report["jobs"]["supportedCandidates"] == 1
    assert report["jobs"]["unspecifiedScopeCandidates"] == 0
    assert report["schemaVersion"] == 2


def test_current_and_supported_predicates_are_not_interchangeable() -> None:
    baseline = {
        "generatedAt": "2026-09-01T00:00:00Z",
        "sourceUrl": "https://example.test/register",
        "institutions": [
            {"id": "hei-1", "officialName": "One", "ownership": "public"},
            {"id": "hei-2", "officialName": "Two", "ownership": "private"},
        ],
    }
    registry = [
        {
            "id": "jobs-one",
            "url": "https://one.test/jobs",
            "official": True,
            "sourceType": "official_job_listing",
            "parser": "test",
            "employerId": "hei-1",
            "coverageScope": "institution_aggregator",
            "sourceCoverageClaim": "not_asserted",
        }
    ]
    included = {
        "id": "job-included",
        "employerId": "hei-1",
        "visibility": "review_pending",
        "catalogueScopeStatus": "included",
        "publicationStatus": "review_pending",
        "lifecycleStatus": "open",
        "paidStatus": "confirmed",
        "minimumDegree": "master",
        "doctorateRequired": False,
        "isPostdoc": False,
    }
    unspecified = {
        **included,
        "id": "job-unspecified-scope",
        "catalogueScopeStatus": None,
    }
    report = build_coverage(
        baseline,
        registry,
        {"generatedAt": "2026-09-10T00:00:00Z", "counts": {}, "coverage": {}},
        {
            "jobs": [included, unspecified],
            "discovery": {
                "runKind": "selected_sources",
                "expectedSourceIds": ["jobs-one"],
                "completeSourceIds": ["jobs-one"],
            },
        },
        {"jobs": []},
        {"counts": {"programmes": 8, "schools": 1}},
        {
            "jobDiscovery": {
                "lastSuccessAt": "2026-09-12T12:00:00Z",
                "lastAllSourceSuccessAt": "2026-09-11T19:24:00Z",
            }
        },
        generated_at="2026-09-12T13:00:00Z",
        publication_pointer={"activeVersion": "v2026-09-12.4", "publishedAt": "2026-09-12T14:32:50Z"},
    )
    assert report["jobs"]["currentCandidates"] == 2
    assert report["jobs"]["supportedCandidates"] == 1
    assert report["jobs"]["unspecifiedScopeCandidates"] == 1
    assert report["jobs"]["missingInstitutions"][0]["institutionId"] == "hei-2"
    assert report["jobs"]["lastDiscoveryRun"]["runKind"] == "selected_sources"
    assert report["jobs"]["lastDiscoveryRun"]["singleSourceRefreshCannotCountAsAllSourceSuccess"] is True
    assert report["jobs"]["lastDiscoveryRun"]["lastAllSourceSuccessAt"] == "2026-09-11T19:24:00Z"
    assert report["jobs"]["lastDiscoveryRun"]["lastScheduledSuccessAt"] == "2026-09-12T12:00:00Z"
    again = build_coverage(
        baseline,
        registry,
        {"generatedAt": "2026-09-10T00:00:00Z", "counts": {}, "coverage": {}},
        {
            "jobs": [included, unspecified],
            "discovery": {
                "runKind": "selected_sources",
                "expectedSourceIds": ["jobs-one"],
                "completeSourceIds": ["jobs-one"],
            },
        },
        {"jobs": []},
        {"counts": {"programmes": 8, "schools": 1}},
        {
            "jobDiscovery": {
                "lastSuccessAt": "2026-09-12T12:00:00Z",
                "lastAllSourceSuccessAt": "2026-09-11T19:24:00Z",
            }
        },
        generated_at="2026-09-12T13:00:00Z",
        publication_pointer={"activeVersion": "v2026-09-12.4", "publishedAt": "2026-09-12T14:32:50Z"},
    )
    assert again["jobs"]["currentCandidates"] == report["jobs"]["currentCandidates"]
    assert again["jobs"]["supportedCandidates"] == report["jobs"]["supportedCandidates"]
    assert again["publication"]["activeVersion"] == "v2026-09-12.4"

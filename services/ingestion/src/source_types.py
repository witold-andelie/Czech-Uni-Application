"""Canonical job-listing source types accepted by production discovery."""

from __future__ import annotations

JOB_LISTING_SOURCE_TYPES = frozenset(
    {
        "official_job_listing",
        "official_job_listing_candidate",
        "official_job_listing_supplemental",
    }
)

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from storage.facts import job_fact_hash  # noqa: E402


URL = "https://jobs.czu.cz/job/tf_asistent-znalostniho-transferu-t1/"


def test_fact_hash_ignores_derived_scope_label() -> None:
    left = job_fact_hash(
        {
            "title": "TF_Asistent znalostního transferu – T1",
            "paid_status": "confirmed",
            "track": "post_master",
            "catalogue_scope_status": "included",
            "scope_classification": "research_technical",
        },
        URL,
    )
    right = job_fact_hash(
        {
            "title": "TF_Asistent znalostního transferu – T1",
            "paid_status": "confirmed",
            "track": "post_master",
            "catalogue_scope_status": "included",
            "scope_classification": "included",
        },
        URL,
    )
    assert left == right


def test_english_display_title_does_not_change_hash_when_original_matches() -> None:
    official = job_fact_hash(
        {
            "title": "TF_Asistent znalostního transferu – T1",
            "paid_status": "confirmed",
            "track": "post_master",
            "catalogue_scope_status": "included",
        },
        URL,
    )
    localized = job_fact_hash(
        {
            "title": {
                "cs": "TF_Asistent znalostního transferu – T1",
                "en": "Faculty of Engineering Knowledge Transfer Assistant – T1",
            },
            "paid_status": "confirmed",
            "track": "post_master",
            "catalogue_scope_status": "included",
        },
        URL,
    )
    assert official == localized

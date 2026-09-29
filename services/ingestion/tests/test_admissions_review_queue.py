"""Incremental review triage must not silently approve or lose old records."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from build_admissions_review_queue import build_queue, review_packet_markdown  # noqa: E402

AS_OF = datetime(2026, 9, 29, 20, tzinfo=timezone.utc)
HASH_A = "a" * 64
HASH_B = "b" * 64
URL = "https://study.czu.cz/programmes/example/"


def fixture(*, source_hash: str = HASH_A, fetched_at: str = "2026-09-29T19:00:00Z", reviewed: bool = False):
    inventory = {"schools": [{"id": "msmt-vs_41000", "rows": [["inv-one", "Example", "m", "faculty", 2, "en", "0413"]]}]}
    links = {"links": {"inv-one": {
        "url": URL, "kind": "school_programme_page", "institutionId": "msmt-vs_41000",
        "rowTitle": "Example", "degree": "m", "language": "en", "reachability": "verified",
    }}}
    candidate = {
        "id": "czu-study-1", "institutionId": "msmt-vs_41000", "titles": {"en": "Example"},
        "sourceLanguage": "en", "studyLanguage": "en", "degree": "m",
        "officialProgrammeUrl": URL, "sourceHtmlSha256": source_hash,
        "durationYears": 2, "tuition": {"amount": 2000, "currency": "EUR"},
        "applicationWindows": [{"start": "2026-09-15", "end": "2027-03-31"}],
    }
    source = {"generatedAt": fetched_at, "institutionId": "msmt-vs_41000",
              "sourceUrls": {"catalogue": "https://study.czu.cz/"}, "programmes": [candidate]}
    approved = {"offerings": [{
        "id": "inv-one", "institutionId": "msmt-vs_41000", "candidateIds": ["czu-study-1"],
        "titleOriginal": "Example", "degree": "master", "teachingLanguages": ["en"],
        "officialProgrammeUrl": URL, "factsReviewedAt": "2026-09-28T12:00:00Z",
    }], "evidence": [{"url": URL, "sourceHash": f"sha256:{HASH_A}"}]} if reviewed else {}
    return inventory, links, [("official.json", source)], approved


def queue_from(*args):
    return build_queue(*args, as_of=AS_OF)


def test_new_candidate_waits_for_live_refresh_when_extract_is_old():
    inventory, links, sources, approved = fixture(fetched_at="2026-09-11T19:00:00Z")
    queue = queue_from(inventory, links, sources, approved)
    assert queue["summary"]["statuses"] == {"refresh_before_review": 1}
    assert "older_than_limit" in queue["items"][0]["warnings"][0]
    assert "not an approval" in review_packet_markdown(queue)


def test_existing_review_is_carried_forward_without_reapproval():
    queue = queue_from(*fixture(reviewed=True))
    assert queue["summary"]["statuses"] == {"reviewed_unchanged": 1}
    assert "## inv-one" not in review_packet_markdown(queue)


def test_changed_source_is_flagged_even_when_structured_facts_look_the_same():
    queue = queue_from(*fixture(source_hash=HASH_B, reviewed=True))
    assert queue["items"][0]["status"] == "reviewed_source_changed"


def test_ambiguous_register_identity_never_enters_review_queue():
    inventory, links, sources, approved = fixture()
    inventory["schools"][0]["rows"].append(["inv-two", "Example", "m", "other faculty", 2, "en", "0413"])
    queue = queue_from(inventory, links, sources, approved)
    assert queue["items"] == []
    assert queue["diagnostics"][0]["reason"] == "ambiguous_register_rows"


def test_off_site_candidate_and_missing_reviewed_candidate_are_not_approved():
    inventory, links, sources, approved = fixture(reviewed=True)
    sources[0][1]["programmes"][0]["officialProgrammeUrl"] = "https://other.example/programmes/example/"
    queue = queue_from(inventory, links, sources, approved)
    assert queue["diagnostics"][0]["reason"] == "invalid_official_url"
    assert queue["items"][0]["status"] == "reviewed_candidate_missing"


def test_two_official_portal_candidates_make_one_inventory_review_row():
    inventory, links, sources, approved = fixture()
    second = dict(sources[0][1]["programmes"][0])
    second.update({"id": "czu-studuj-1", "titles": {"cs": "Example"},
                   "sourceLanguage": "cs", "officialProgrammeUrl": "https://studuj.czu.cz/programmes/example/"})
    sources.append(("czech.json", {"generatedAt": "2026-09-29T19:00:00Z",
                    "institutionId": "msmt-vs_41000", "sourceUrls": {"catalogue": "https://studuj.czu.cz/"},
                    "programmes": [second]}))
    queue = queue_from(inventory, links, sources, approved)
    assert queue["summary"]["mappedReviewRows"] == 1
    assert queue["items"][0]["status"] == "new_review"
    assert len(queue["items"][0]["candidates"]) == 2

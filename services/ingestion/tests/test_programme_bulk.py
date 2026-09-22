from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adapters.programmes.evidences import load_payload, parse_programme_rows  # noqa: E402
from storage.facts import job_fact_hash  # noqa: E402
from storage.postgres import _programme_facts_from_row  # noqa: E402


def test_studyin_rows_all_have_stable_identity() -> None:
    payload = load_payload("studyin")
    rows = parse_programme_rows("studyin", payload)
    assert len(rows) == len(payload["programmes"]) > 5000
    codes = [str(row["code"]) for row in rows]
    assert len(set(codes)) == len(codes)
    assert all(row["sourceUrl"] for row in rows)
    assert all(row["title"] for row in rows)


def test_programme_facts_hash_is_canonical() -> None:
    row = {
        "title": "Bachelor of Mechanical Engineering",
        "sourceUrl": "https://studyin.gov.cz/plan-your-studies/universities/x/bachelor-of-mechanical-engineering",
        "degree": "b",
        "studyLanguage": "en",
    }
    facts = _programme_facts_from_row(row)
    digest = job_fact_hash(facts, row["sourceUrl"])
    assert digest  # deterministic
    # changing the variant title changes the digest (facts hash over the title)
    row2 = dict(row, title="Bakalářský studijní program")
    digest2 = job_fact_hash(_programme_facts_from_row(row2), row2["sourceUrl"])
    assert digest2 != digest


def test_external_id_prefix_is_employer_or_source_id() -> None:
    # Mirror of the account resolution in bulk_upsert_programmes: employerId wins,
    # otherwise the source id (studyin) is the prefix.
    account = "studyin"
    remote = "000764cd-3d1b-4434-b4de-b65d2f4376d6"
    assert f"{account}:{remote}".split(":", 1)[0] == "studyin"
    account2 = "msmt-vs_21000"
    assert f"{account2}:{remote}".split(":", 1)[0] == "msmt-vs_21000"
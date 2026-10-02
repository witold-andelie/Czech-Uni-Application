from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import resolve_programme_links as resolver  # noqa: E402


def _school(ident: str, resolved: int, offerings: int, stamp: str) -> dict:
    return {"institutionId": ident, "offerings": offerings, "resolved": resolved, "unresolved": offerings - resolved, "resolvedAt": stamp}


def _link(school: str, url: str) -> dict:
    return {"url": url, "institutionId": school, "reachability": "verified"}


PREVIOUS = {
    "generatedAt": "2026-09-28T00:00:00Z",
    "coverage": {"schools": [_school("a", 1, 2, "2026-09-28T00:00:00Z"), _school("b", 1, 1, "2026-09-27T00:00:00Z"), _school("c", 2, 2, "2026-09-27T00:00:00Z")]},
    "links": {
        "a1": _link("a", "https://a.cz/1"),
        "b1": _link("b", "https://b.cz/1"),
        "c1": _link("c", "https://c.cz/1"),
        "c2": _link("c", "https://c.cz/2"),
    },
    "unresolved": [{"institutionId": "a", "rowId": "a2", "reason": "no_candidate_page"}],
    "requests": 9,
}


def test_schools_are_dealt_round_robin_from_the_rotation() -> None:
    order = [{"id": name} for name in "abcdefg"]
    assert resolver.shard_schools(order, 0, 3) == ["a", "d", "g"]
    assert resolver.shard_schools(order, 2, 3) == ["c", "f"]


def test_merge_takes_each_school_from_the_shard_that_read_it() -> None:
    stamp = "2026-10-03T04:00:00Z"
    shard = {
        "generatedAt": stamp,
        # Shard read a; b is carried from the previous index inside the shard.
        "coverage": {"schools": [_school("a", 2, 2, stamp), _school("b", 0, 1, "2026-09-27T00:00:00Z")]},
        "links": {"a1": _link("a", "https://a.cz/1"), "a2": _link("a", "https://a.cz/2")},
        "unresolved": [{"institutionId": "b", "rowId": "b1", "reason": "not_attempted"}],
        "requests": 40,
    }
    merged = resolver.merge_shards(PREVIOUS, [shard])
    assert set(merged["links"]) == {"a1", "a2", "b1", "c1", "c2"}
    assert merged["unresolved"] == []
    assert merged["counts"]["linked"] == 5
    assert merged["counts"]["offerings"] == 5
    assert merged["requests"] == 40


def test_a_school_read_below_its_floor_keeps_its_previous_links() -> None:
    stamp = "2026-10-03T04:00:00Z"
    shard = {
        "generatedAt": stamp,
        "coverage": {"schools": [_school("c", 0, 2, stamp)]},
        "links": {},
        "unresolved": [
            {"institutionId": "c", "rowId": "c1", "reason": "no_candidate_page"},
            {"institutionId": "c", "rowId": "c2", "reason": "no_candidate_page"},
        ],
    }
    kept: list[str] = []
    merged = resolver.merge_shards(PREVIOUS, [shard], floor={"c": 2}, kept_below_floor=kept)
    assert {"c1", "c2"} <= set(merged["links"])
    assert kept == ["c: read 0, floor 2"]

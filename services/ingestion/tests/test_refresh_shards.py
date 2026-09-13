from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from refresh_shards import (  # noqa: E402
    SHARD_COUNT,
    assign_shards,
    assign_shards_stable,
    merge_sharded_jobs,
    merge_sharded_portals,
    next_utc_midnight,
    shard_index_for_date,
    shard_sizes,
    units_for_shard,
)


def test_five_shards_cover_all_and_differ_by_at_most_one() -> None:
    ids = [f"msmt-vs_{index:05d}" for index in range(54)]
    mapping = assign_shards(ids)
    assert set(mapping) == set(ids)
    assert set(mapping.values()) == set(range(SHARD_COUNT))
    sizes = shard_sizes(ids)
    assert sum(sizes) == 54
    assert max(sizes) - min(sizes) <= 1
    combined = [item for shard in range(SHARD_COUNT) for item in units_for_shard(ids, shard)]
    assert sorted(combined) == sorted(ids)
    assert len(combined) == len(set(combined))


def test_assignment_is_stable() -> None:
    ids = ["msmt-vs_27000", "msmt-vs_11000", "msmt-vs_14000"]
    first = assign_shards(ids)
    second = assign_shards(list(reversed(ids)))
    assert first == second
    assert first["msmt-vs_11000"] == assign_shards(["msmt-vs_11000", "msmt-vs_99999"])["msmt-vs_11000"]


def test_stable_assignment_does_not_rotate_when_baseline_gains_a_school() -> None:
    original = ["msmt-vs_11000", "msmt-vs_14000", "msmt-vs_27000", "msmt-vs_41000", "msmt-vs_51000"]
    previous = assign_shards(original)
    expanded = original + ["msmt-vs_12000"]
    naive = assign_shards(expanded)
    stable = assign_shards_stable(expanded, previous)
    assert stable["msmt-vs_51000"] == previous["msmt-vs_51000"]
    assert naive["msmt-vs_51000"] != previous["msmt-vs_51000"]
    assert set(stable) == set(expanded)
    removed = assign_shards_stable(original, stable)
    for ident in original:
        assert removed[ident] == stable[ident]


def test_date_maps_to_fifth_and_repeats_every_five_days() -> None:
    anchor = date(2026, 9, 1)
    assert shard_index_for_date(anchor, anchor=anchor) == 0
    assert shard_index_for_date(date(2026, 9, 2), anchor=anchor) == 1
    assert shard_index_for_date(date(2026, 9, 6), anchor=anchor) == 0
    assert [shard_index_for_date(date(2026, 9, 1 + offset), anchor=anchor) for offset in range(5)] == [0, 1, 2, 3, 4]


def test_merge_keeps_other_shards() -> None:
    previous = {
        "jobs": [{"id": "a"}, {"id": "b"}],
        "windows": [{"ownerId": "a"}, {"ownerId": "b"}],
        "evidence": [{"id": "ev-a"}, {"id": "ev-b"}],
        "skipped": [],
    }
    shard = {
        "generatedAt": "2026-09-07T00:00:00Z",
        "jobs": [{"id": "a", "fresh": True}],
        "windows": [{"ownerId": "a", "fresh": True}],
        "evidence": [{"id": "ev-a", "fresh": True}],
        "skipped": [{"id": "a", "reason": "http-503"}],
    }
    merged = merge_sharded_jobs(previous, shard, {"a"})
    ids = {item["id"] for item in merged["jobs"]}
    assert ids == {"a", "b"}
    assert next(item for item in merged["jobs"] if item["id"] == "a")["fresh"] is True
    assert next(item for item in merged["jobs"] if item["id"] == "b") == {"id": "b"}
    assert merged["counts"]["jobs"] == 2


def test_merge_portals_replaces_only_shard_rows() -> None:
    previous = {
        "institutions": [
            {"institutionId": "a", "kind": "e_application"},
            {"institutionId": "b", "kind": "missing"},
        ]
    }
    merged = merge_sharded_portals(
        previous,
        [{"institutionId": "a", "kind": "admissions_info"}],
        ["a", "b"],
    )
    assert merged["counts"]["institutions"] == 2
    assert merged["institutions"][0]["kind"] == "admissions_info"
    assert merged["institutions"][1]["kind"] == "missing"


def test_next_midnight_is_tomorrow_utc() -> None:
    now = datetime(2026, 9, 7, 23, 30, tzinfo=timezone.utc)
    nxt = next_utc_midnight(now)
    assert nxt == datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)

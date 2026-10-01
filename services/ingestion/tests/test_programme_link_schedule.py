"""Tests for the programme page link scheduler wiring and its regression floor."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from check_programme_link_coverage import check  # noqa: E402
from ci_refresh import FLAGS, task_command  # noqa: E402
from schedule import (  # noqa: E402
    PROGRAMME_LINK_RESOLUTION_INTERVAL_HOURS,
    ScheduleManager,
    VOLATILE_TASKS,
)


def test_the_link_resolution_task_is_scheduled_on_the_full_official_cycle():
    spec = VOLATILE_TASKS["programme_link_resolution"]
    # The whole official-source sweep is 120 hours (docs/REFRESH_POLICY.md); a
    # shorter cadence here would re-read every school's site every tick.
    assert spec["intervalHours"] == PROGRAMME_LINK_RESOLUTION_INTERVAL_HOURS == 120
    assert FLAGS["programme_link_resolution"] == "--resolve-programme-links"
    assert task_command({"type": "programme_link_resolution"})[-1] == "--resolve-programme-links"


def test_a_due_task_reaches_the_worker_flag(tmp_path):
    manager = ScheduleManager(tmp_path / "state.json")
    tasks = manager.get_pending_tasks()
    assert any(task["type"] == "programme_link_resolution" for task in tasks)


def test_the_worker_runs_the_link_resolution_task(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))
    import worker

    recorded: dict = {}

    def fake_resolve(*, budget_seconds, **_kwargs):
        recorded["budget"] = budget_seconds
        return {"status": "succeeded", "counts": {"linked": 3}}

    monkeypatch.setattr(worker, "resolve_programme_page_links", fake_resolve)
    monkeypatch.setenv("PROGRAMME_LINK_BUDGET_SECONDS", "123")
    original_argv = sys.argv
    try:
        sys.argv = ["worker.py", "--resolve-programme-links"]
        worker.main()
    finally:
        sys.argv = original_argv
    assert recorded["budget"] == 123.0


def _links_payload(resolved: int, offerings: int) -> dict:
    return {
        "coverage": {
            "totals": {"resolved": resolved, "offerings": offerings},
            "schools": [
                {
                    "institutionId": "msmt-vs_41000",
                    "offerings": offerings,
                    "resolved": resolved,
                }
            ],
        }
    }


def _floor(resolved: int) -> dict:
    return {"resolvedTotal": resolved, "resolvedBySchool": {"msmt-vs_41000": resolved}}


def test_equal_coverage_passes_the_floor(tmp_path):
    links = tmp_path / "links.json"
    floor = tmp_path / "floor.json"
    links.write_text(json.dumps(_links_payload(107, 186)), encoding="utf-8")
    floor.write_text(json.dumps(_floor(107)), encoding="utf-8")
    ok, messages = check(links, floor)
    assert ok, messages
    assert any("107" in message for message in messages)


def test_a_single_school_regression_fails_the_floor(tmp_path):
    links = tmp_path / "links.json"
    floor = tmp_path / "floor.json"
    links.write_text(json.dumps(_links_payload(12, 186)), encoding="utf-8")
    floor.write_text(json.dumps(_floor(107)), encoding="utf-8")
    ok, messages = check(links, floor)
    assert not ok
    assert any("PROGRAMME_LINK_REGRESSION" in message for message in messages)


def test_a_missing_school_in_the_new_index_fails_the_floor(tmp_path):
    links = tmp_path / "links.json"
    floor = tmp_path / "floor.json"
    links.write_text(json.dumps(_links_payload(0, 0)), encoding="utf-8")
    floor.write_text(json.dumps(_floor(107)), encoding="utf-8")
    ok, messages = check(links, floor)
    assert not ok


def test_an_absent_index_is_not_reported_as_a_regression(tmp_path):
    links = tmp_path / "missing.json"
    floor = tmp_path / "floor.json"
    floor.write_text(json.dumps(_floor(107)), encoding="utf-8")
    ok, messages = check(links, floor)
    assert ok, messages


def _links_payload_with_links(resolved: int, offerings: int, **links) -> dict:
    payload = _links_payload(resolved, offerings)
    payload["generatedAt"] = "2026-09-27T11:54:10Z"
    payload["links"] = links
    return payload


def test_a_proven_link_the_built_inventory_does_not_publish_is_reported(tmp_path):
    """The gate must not lose a school's own page without anyone saying so.

    The index proves one link on the school's own domain; the inventory built
    from this same index carries none of it. That is a drop, and CI fails.
    """
    links = tmp_path / "links.json"
    floor = tmp_path / "floor.json"
    inventory = tmp_path / "inventory.json"
    links.write_text(
        json.dumps(
            _links_payload_with_links(
                1,
                186,
                **{
                    "inv-czu-1": {
                        "url": "https://studuj.czu.cz/programmes/obchod-a-podnikani-s-technikou-2/",
                        "kind": "school_programme_page",
                        "institutionId": "msmt-vs_41000",
                        "reachability": "verified",
                    }
                },
            )
        ),
        encoding="utf-8",
    )
    floor.write_text(json.dumps(_floor(1)), encoding="utf-8")
    row = ["inv-czu-1", "Obchod a podnikání s technikou", "b", "PEF", 3, "cs", "0413"]
    inventory.write_text(
        json.dumps(
            {
                "programmeLinkGeneratedAt": "2026-09-27T11:54:10Z",
                "programmeLinks": {},
                "schools": [{"id": "msmt-vs_41000", "rows": [row]}],
            }
        ),
        encoding="utf-8",
    )
    ok, messages = check(
        links,
        floor,
        inventory_path=inventory,
        domains={"msmt-vs_41000": {"czu.cz"}},
    )
    assert not ok
    assert any("PROGRAMME_LINK_DROPPED_IN_PUBLICATION" in message for message in messages)

    # The same link for a row the register no longer lists is a register
    # change, not a page the gate dropped.
    inventory.write_text(
        json.dumps(
            {
                "programmeLinkGeneratedAt": "2026-09-27T11:54:10Z",
                "programmeLinks": {},
                "schools": [{"id": "msmt-vs_41000", "rows": []}],
            }
        ),
        encoding="utf-8",
    )
    ok, messages = check(
        links,
        floor,
        inventory_path=inventory,
        domains={"msmt-vs_41000": {"czu.cz"}},
    )
    assert ok, messages


def test_an_inventory_older_than_the_index_is_not_faulted_for_missing_links(tmp_path):
    """A stale build is simply older; only a build of this index can be judged."""
    links = tmp_path / "links.json"
    floor = tmp_path / "floor.json"
    inventory = tmp_path / "inventory.json"
    links.write_text(
        json.dumps(
            _links_payload_with_links(
                1,
                186,
                **{
                    "inv-czu-1": {
                        "url": "https://studuj.czu.cz/programmes/obchod-a-podnikani/",
                        "institutionId": "msmt-vs_41000",
                    }
                },
            )
        ),
        encoding="utf-8",
    )
    floor.write_text(json.dumps(_floor(1)), encoding="utf-8")
    inventory.write_text(
        json.dumps(
            {"programmeLinkGeneratedAt": "2026-09-27T08:00:00Z", "programmeLinks": {}}
        ),
        encoding="utf-8",
    )
    ok, messages = check(
        links,
        floor,
        inventory_path=inventory,
        domains={"msmt-vs_41000": {"czu.cz"}},
    )
    assert ok, messages


def test_a_tick_records_the_link_task_failure_like_any_other(tmp_path):
    from ci_refresh import run_tick

    manager = ScheduleManager(tmp_path / "state.json")
    manager.get_pending_tasks = lambda: [{"type": "programme_link_resolution"}]

    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    report = run_tick(manager, run=run, output=tmp_path / "report.json")
    assert report["failed"]
    state = manager.load_state()["programmeLinkResolution"]
    assert state["retryAt"]
    assert state["lastSuccessAt"] is None
    assert "timed out" in (state.get("lastError") or "")

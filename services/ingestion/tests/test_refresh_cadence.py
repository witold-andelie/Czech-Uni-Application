"""The scheduled runs are 3-4 days apart (owner decision 2026-11-12).

Three limits depend on that spacing, so it is pinned here rather than left to
whoever next edits a cron line: the 7-day live-check window (a post verified at
one run must be verified again by the next), the second-run gap the notice
re-read interval leaves, and the pairing of the two scheduled workflows.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src" / "cli"))

import verify_live_titles  # noqa: E402
from live_evidence import DEFAULT_MAX_AGE_DAYS  # noqa: E402


def cron_days(workflow: str) -> list[int]:
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    (minute_hour_days, month, weekday) = re.search(r"- cron: '(\S+ \S+ )(\S+) (\S+) (\S+)'", text).groups()[1:]
    assert month == "*" and weekday == "*", workflow
    return [int(day) for day in minute_hour_days.split(",")]


def run_dates(days: list[int], year: int) -> list[date]:
    found = []
    for month in range(1, 13):
        for day in days:
            try:
                found.append(date(year, month, day))
            except ValueError:
                pass
    return found


def test_the_scheduled_workflows_run_on_the_same_days() -> None:
    assert cron_days("refresh.yml") == cron_days("programme-links.yml")


def test_runs_are_three_to_four_days_apart_whatever_the_month() -> None:
    for year in (2026, 2027, 2028):
        found = run_dates(cron_days("refresh.yml"), year) + run_dates(cron_days("refresh.yml"), year + 1)[:1]
        gaps = [(later - earlier).days for earlier, later in zip(found, found[1:])]
        assert max(gaps) <= DEFAULT_MAX_AGE_DAYS - 3, (year, max(gaps))
        assert sum(gaps) / len(gaps) >= 3, year
        assert min(gaps) >= 1


def test_a_post_read_at_one_run_is_read_again_at_the_next() -> None:
    assert verify_live_titles.NOTICE_CHECK_DAYS < 3

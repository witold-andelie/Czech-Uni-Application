from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import harvest_czu_programmes as czu  # noqa: E402
import worker  # noqa: E402
from schedule import ScheduleManager, to_iso  # noqa: E402


def _api_row(post_id: int, title: str, degree: str, faculty: str) -> dict:
    degree_id = 65 if degree == "bachelor" else 64
    faculty_id = 19 if faculty == "fzp" else 21
    return {
        "id": post_id,
        "modified_gmt": "2026-09-01T10:00:00",
        "slug": title.casefold().replace(" ", "-"),
        "status": "publish",
        "type": "programmes",
        "link": f"https://study.czu.cz/programmes/{title.casefold().replace(' ', '-')}/",
        "title": {"rendered": title},
        "degree": [degree_id],
        "faculty": [faculty_id],
        "programme-fields": [8],
        "_embedded": {
            "wp:term": [
                [{"id": degree_id, "slug": degree, "name": degree.title(), "taxonomy": "degree"}],
                [{"id": faculty_id, "slug": faculty, "name": "Faculty of Environmental Sciences", "taxonomy": "faculty"}],
                [{"id": 8, "slug": "environment", "name": "Environment", "taxonomy": "programme-fields"}],
            ]
        },
    }


def _detail(post_id: int, start: str, end: str, *, linked_apply: bool = False) -> str:
    href = ' href="https://is.czu.cz/prihlaska/?lang=en"' if linked_apply else ""
    return f"""
    <html><body class="single-programmes postid-{post_id}">
      <h2>Admission requirements</h2>
      <div><p>Bachelor diploma.</p><a href="https://www.fzp.czu.cz/admissions">Details</a></div>
      <a class="button"{href}><span>Apply now!</span></a>
      <h2>Study duration</h2><div>2 years</div>
      <h2>Tuition fee</h2><div>€ 2,000 per year*</div>
      <h2>Tuition fee (EU students)</h2><div>€ 500 per year*</div>
      <h2>Application</h2><div></div>
      <h2>Applications start</h2><div>{start}</div>
      <h2>Applications end</h2><div>{end}</div>
      <h2>Contact</h2><div>Admissions office</div>
    </body></html>
    """


def _source_pages() -> tuple[dict[str, tuple[int, dict[str, str], str]], list[dict]]:
    rows = [
        _api_row(101, "Environmental Data Science", "bachelor", "fzp"),
        _api_row(102, "Environmental Modelling", "master", "fzp"),
    ]
    pages = {
        czu.PROGRAMMES_API: (200, {"x-wp-total": "2", "x-wp-totalpages": "1"}, json.dumps(rows)),
        czu.OPEN_PROGRAMMES_URL: (200, {}, '<span class="jet-engine-query-count query-8 count-type-total">0</span> programmes found'),
        czu.ADMISSIONS_URL: (
            200,
            {},
            '<h1>CZU Admissions</h1><p>The admission fee is CZK 850.</p>'
            '<a href="https://is.czu.cz/prihlaska/?lang=en">Apply online</a>',
        ),
        rows[0]["link"]: (200, {}, _detail(101, "15 September, 2026", "15 January, 2027")),
        rows[1]["link"]: (200, {}, _detail(102, "14 September, 2026", "15 January, 2027")),
    }
    return pages, rows


def test_czu_harvest_cross_checks_api_and_reads_every_detail() -> None:
    pages, _ = _source_pages()
    now = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    payload = czu.harvest_catalog(
        lambda url: pages[url],
        now=now,
        sleep=lambda _seconds: None,
        delay_seconds=0,
    )

    assert payload["catalogKind"] == "candidate_not_published"
    assert payload["scope"]["teachingLanguages"] == ["en"]
    assert payload["counts"]["programmes"] == 2
    assert payload["counts"]["degrees"] == {"bachelor": 1, "master": 1}
    assert payload["counts"]["detailsWithCompleteWindow"] == 2
    assert payload["counts"]["upcomingByDetailDates"] == 2
    assert payload["coverage"]["complete"] is True
    assert payload["coverage"]["availabilityCrosscheck"] == "agrees"
    first = payload["programmes"][0]
    assert first["applicationWindows"][0]["start"] == "2026-09-15"
    assert first["applicationStatus"] == "upcoming"
    assert first["tuition"] == {
        "amount": 2000.0,
        "currency": "EUR",
        "period": "year",
        "displayOriginal": "€ 2,000 per year*",
    }
    assert first["applyUrl"] is None
    assert first["generalApplyPortalUrl"] == "https://is.czu.cz/prihlaska/?lang=en"


def test_czu_api_total_mismatch_is_never_complete() -> None:
    rows = [_api_row(101, "Environmental Data Science", "bachelor", "fzp")]
    with pytest.raises(czu.HarvestIncomplete, match="pagination mismatch"):
        czu.parse_programme_api(
            json.dumps(rows),
            {"x-wp-total": "2", "x-wp-totalpages": "1"},
        )


def test_czu_refresh_has_an_independent_two_hour_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages, _ = _source_pages()
    monkeypatch.setattr(worker, "RUNS", tmp_path / "runs")
    manager = ScheduleManager(tmp_path / "schedule.json")
    now = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    manager.init_state(now)

    result = worker.refresh_czu_programme_availability(
        lambda url: pages[url],
        now,
        output_path=tmp_path / "czu.json",
        schedule_manager=manager,
        use_lock=False,
        sleep=lambda _seconds: None,
        delay_seconds=0,
    )
    state = manager.load_state(now)
    assert result["counts"]["programmes"] == 2
    assert state["czuProgrammeAvailability"]["lastSuccessAt"] == to_iso(now)
    assert state["czuProgrammeAvailability"]["nextDueAt"] == to_iso(now + timedelta(hours=2))
    assert state["programmeAvailability"]["lastSuccessAt"] is None


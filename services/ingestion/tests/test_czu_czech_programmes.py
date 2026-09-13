from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import harvest_czu_czech_programmes as czu_cs  # noqa: E402
import worker  # noqa: E402
from schedule import ScheduleManager, to_iso  # noqa: E402


def _detail(
    post_id: int,
    title: str,
    *,
    degree: str,
    language: str,
    start: str,
    end: str,
) -> str:
    degree_label = "Bakalářský" if degree == "bakalar" else "Magisterský"
    return f"""
    <html><body class="single-programmes postid-{post_id}">
      <div class="post-{post_id} programmes type-programmes status-publish degree-{degree} faculty-fzp programme-fields-informatika">
        <h1>{title}</h1>
        <h2>Požadavky na přijetí</h2><div><p>Předchozí vzdělání.</p><a href="https://www.fzp.czu.cz/prijeti">Podmínky</a></div>
        <a href="https://is.czu.cz/prihlaska/">Přihlásit se</a>
        <h2>Stupeň studia</h2><div>{degree_label}</div>
        <h2>Délka studia</h2><div>{'3' if degree == 'bakalar' else '2'} roky</div>
        <h2>Druh studia</h2><div>Prezenční</div>
        <h2>Jazyk studia</h2><div>{language}</div>
        <h2>Přihlášky</h2><div></div>
        <h2>Příjem přihlášek od</h2><div>{start}</div>
        <h2>Příjem přihlášek do</h2><div>{end}</div>
        <h2>Kontakt</h2><div>Studijní oddělení</div>
      </div>
    </body></html>
    """


def _pages() -> tuple[dict[str, tuple[int, dict[str, str], str]], dict]:
    cs_url = f"{czu_cs.PROGRAMMES_ARCHIVE_URL}informatika/"
    en_url = f"{czu_cs.PROGRAMMES_ARCHIVE_URL}environmental-modelling/"
    index = f"""<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>{czu_cs.PROGRAMMES_SITEMAP_URL}</loc></sitemap>
    </sitemapindex>"""
    sitemap = f"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>{czu_cs.PROGRAMMES_ARCHIVE_URL}</loc><lastmod>2026-09-01T00:00:00Z</lastmod></url>
      <url><loc>{cs_url}</loc><lastmod>2026-09-01T00:00:00Z</lastmod></url>
      <url><loc>{en_url}</loc><lastmod>2026-09-01T00:00:00Z</lastmod></url>
    </urlset>"""
    pages = {
        czu_cs.CATALOGUE_URL: (
            200,
            {},
            '<span class="jet-engine-query-count query-5 count-type-total">2</span>',
        ),
        czu_cs.SITEMAP_INDEX_URL: (200, {}, index),
        czu_cs.PROGRAMMES_SITEMAP_URL: (200, {}, sitemap),
        czu_cs.ADMISSIONS_URL: (
            200,
            {},
            '<h1>Harmonogram přijímacího řízení ČZU</h1>'
            '<p>Poplatek za přijímací řízení činí 850 Kč.</p>'
            '<a href="https://is.czu.cz/prihlaska/">Podat přihlášku</a>',
        ),
        cs_url: (
            200,
            {},
            _detail(
                101,
                "Informatika",
                degree="bakalar",
                language="Čeština",
                start="7. listopadu 2025",
                end="31. března 2026",
            ),
        ),
        en_url: (
            200,
            {},
            _detail(
                102,
                "Environmental Modelling",
                degree="magistr",
                language="Angličtina",
                start="15. září 2026",
                end="15. ledna 2027",
            ),
        ),
    }
    english = {
        "coverage": {"complete": True},
        "programmes": [
            {"titles": {"en": "Environmental Modelling"}, "degree": "m"}
        ],
    }
    return pages, english


def test_czu_czech_portal_matches_home_sitemap_and_every_detail() -> None:
    pages, english = _pages()
    now = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    payload = czu_cs.harvest_catalog(
        lambda url: pages[url],
        now=now,
        sleep=lambda _seconds: None,
        delay_seconds=0,
        english_payload=english,
    )

    assert payload["catalogKind"] == "candidate_not_published"
    assert payload["counts"]["programmes"] == 2
    assert payload["counts"]["teachingLanguages"] == {"cs": 1, "en": 1}
    assert payload["counts"]["detailsWithCompleteWindow"] == 2
    assert payload["counts"]["closedByDetailDates"] == 1
    assert payload["counts"]["upcomingByDetailDates"] == 1
    assert payload["coverage"]["complete"] is True
    assert payload["coverage"]["englishSourceCrosscheck"]["status"] == "agrees"
    czech = next(item for item in payload["programmes"] if item["studyLanguage"] == "cs")
    assert czech["applicationWindows"][0]["start"] == "2025-11-07"
    assert czech["applicationWindows"][0]["end"] == "2026-03-31"
    assert czech["tuition"] is None
    assert czech["applyUrl"] == "https://is.czu.cz/prihlaska/"


def test_czu_czech_home_and_sitemap_count_mismatch_fails_closed() -> None:
    pages, english = _pages()
    pages[czu_cs.CATALOGUE_URL] = (
        200,
        {},
        '<span class="jet-engine-query-count query-5 count-type-total">3</span>',
    )
    with pytest.raises(czu_cs.HarvestIncomplete, match="total mismatch"):
        czu_cs.harvest_catalog(
            lambda url: pages[url],
            now=datetime(2026, 9, 10, tzinfo=timezone.utc),
            sleep=lambda _seconds: None,
            delay_seconds=0,
            english_payload=english,
        )


def test_czu_czech_refresh_has_an_independent_two_hour_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages, english = _pages()
    monkeypatch.setattr(worker, "RUNS", tmp_path / "runs")
    manager = ScheduleManager(tmp_path / "schedule.json")
    now = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    manager.init_state(now)

    result = worker.refresh_czu_czech_programme_availability(
        lambda url: pages[url],
        now,
        output_path=tmp_path / "czu-cs.json",
        schedule_manager=manager,
        use_lock=False,
        sleep=lambda _seconds: None,
        delay_seconds=0,
        english_payload=english,
    )
    state = manager.load_state(now)
    assert result["counts"]["programmes"] == 2
    assert state["czuCzechProgrammeAvailability"]["lastSuccessAt"] == to_iso(now)
    assert state["czuCzechProgrammeAvailability"]["nextDueAt"] == to_iso(
        now + timedelta(hours=2)
    )
    assert state["czuProgrammeAvailability"]["lastSuccessAt"] is None


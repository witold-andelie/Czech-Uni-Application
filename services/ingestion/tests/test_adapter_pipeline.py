from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.jobs.czu_wp_job_manager import CzuWpJobManagerAdapter  # noqa: E402
from engine.run_source import run_source  # noqa: E402
from engine.urls import official_detail_allowed  # noqa: E402
from storage.memory import MemoryStore  # noqa: E402


PORTAL = "https://jobs.czu.test/"
PUBLIC_API = "https://jobs.czu.test/jm-ajax/get_listings/"
REST_API = "https://jobs.czu.test/wp-json/wp/v2/job-listings"
TECHNICAL_URL = "https://jobs.czu.test/job/tf_asistent-znalostniho-transferu-t1/"
ADMIN_URL = "https://jobs.czu.test/job/ekonomicky-referent/"
TECHNICAL_TITLE = "TF_Asistent znalostního transferu – T1"
ADMIN_TITLE = "Ekonomický referent"


def _source() -> dict:
    return {
        "id": "czu-central-jobs",
        "url": PORTAL,
        "publicListUrl": PUBLIC_API,
        "apiUrl": REST_API,
        "sourceType": "official_job_listing",
        "employerId": "msmt-vs_41000",
        "parser": "czu_wp_job_manager",
        "perPage": 100,
        "maxPages": 20,
    }


def _public_payload() -> str:
    return json.dumps(
        {
            "found_jobs": True,
            "max_num_pages": 1,
            "html": (
                f'<li class="post-1604 job_listing status-publish"><a href="{TECHNICAL_URL}"><h3>{TECHNICAL_TITLE}</h3></a></li>'
                f'<li class="post-1605 job_listing status-publish"><a href="{ADMIN_URL}"><h3>{ADMIN_TITLE}</h3></a></li>'
                f'<li class="post-1597 job_listing status-expired"><a href="https://jobs.czu.test/job/expired/"><h3>Expired role</h3></a></li>'
            ),
        },
        ensure_ascii=False,
    )


def _rest_row(code: int, title: str, url: str, body: str) -> dict:
    return {
        "id": code,
        "date": "2026-08-20T20:03:06",
        "status": "publish",
        "type": "job_listing",
        "link": url,
        "title": {"rendered": title},
        "content": {"rendered": body},
        "meta": {"_filled": 0},
    }


def _rest_payload() -> str:
    technical_body = (
        "<p>Náplň práce: vývoji a implementaci softwarového vybavení (firmwaru), "
        "programování algoritmů a laboratorní testování.</p>"
        "<p>Požadavky: Vysokoškolské vzdělání minimálně druhého stupně "
        "(Ing., Mgr., MSc.).</p>"
        "<p>Nabízíme: Ohodnocení na celý úvazek 60 000,- Kč hrubého. "
        "Přihlášky budou přijímány do 17.09.2026.</p>"
    )
    administrative_body = (
        "<p>Administrativní a ekonomická podpora vedení, evidence dokumentů a pracovních cest. "
        "Pracovní smlouva.</p>"
    )
    return json.dumps(
        [
            _rest_row(1604, TECHNICAL_TITLE, TECHNICAL_URL, technical_body),
            _rest_row(1605, ADMIN_TITLE, ADMIN_URL, administrative_body),
        ],
        ensure_ascii=False,
    )


def _fetch(url: str) -> tuple[int, str]:
    if url == PORTAL:
        return 200, '<script src="wp-job-manager.js"></script><div class="job_listings"></div><script>"/jm-ajax/%%endpoint%%/"</script>'
    if url.startswith(PUBLIC_API):
        return 200, _public_payload()
    if url.startswith(REST_API):
        return 200, _rest_payload()
    raise AssertionError(url)


def test_czu_adapter_keeps_every_official_vacancy_including_admin() -> None:
    outcome = run_source(CzuWpJobManagerAdapter(_source()), _source(), {"fetch_page": _fetch})
    assert outcome["run"]["status"] == "succeeded"
    assert outcome["completeness"].ok
    assert {item.remote_id for item in outcome["candidates"]} == {"1604", "1605"}
    by_id = {item.remote_id: item for item in outcome["candidates"]}
    assert by_id["1604"].official_detail_url == TECHNICAL_URL
    assert by_id["1604"].track == "post_master"
    assert by_id["1604"].catalogue_scope_status == "included"
    assert by_id["1605"].official_detail_url == ADMIN_URL
    assert by_id["1605"].track is None
    assert by_id["1605"].scope_classification == "unknown"
    assert by_id["1605"].catalogue_scope_status == "unspecified"
    assert len(outcome["store"].jobs) == 2
    assert len(outcome["store"].versions) == 2


def test_unchanged_rerun_does_not_duplicate_identities_or_versions() -> None:
    store = MemoryStore()
    adapter = CzuWpJobManagerAdapter(_source())
    first = run_source(adapter, _source(), {"fetch_page": _fetch}, store)
    second = run_source(CzuWpJobManagerAdapter(_source()), _source(), {"fetch_page": _fetch}, store)
    assert first["run"]["status"] == second["run"]["status"] == "succeeded"
    assert len(store.jobs) == 2
    assert len(store.versions) == 2
    assert len(store.runs) == 2


def test_changed_detail_creates_one_new_version_and_stales_review() -> None:
    store = MemoryStore()
    run_source(CzuWpJobManagerAdapter(_source()), _source(), {"fetch_page": _fetch}, store)

    def fetch_changed(url: str) -> tuple[int, str]:
        if url.startswith(REST_API):
            payload = json.loads(_rest_payload())
            payload[0]["title"]["rendered"] = TECHNICAL_TITLE + " (updated)"
            listing = json.loads(_public_payload())
            listing["html"] = listing["html"].replace(TECHNICAL_TITLE, TECHNICAL_TITLE + " (updated)")
            if url.startswith(PUBLIC_API):
                return 200, json.dumps(listing, ensure_ascii=False)
            return 200, json.dumps(payload, ensure_ascii=False)
        if url.startswith(PUBLIC_API):
            listing = json.loads(_public_payload())
            listing["html"] = listing["html"].replace(TECHNICAL_TITLE, TECHNICAL_TITLE + " (updated)")
            return 200, json.dumps(listing, ensure_ascii=False)
        return _fetch(url)

    run_source(CzuWpJobManagerAdapter(_source()), _source(), {"fetch_page": fetch_changed}, store)
    assert len(store.jobs) == 2
    assert len(store.versions) == 3
    stale = [item for item in store.versions if item.get("review_stale")]
    assert len(stale) == 1


def test_incomplete_pagination_closes_nothing() -> None:
    store = MemoryStore()
    first = run_source(CzuWpJobManagerAdapter(_source()), _source(), {"fetch_page": _fetch}, store)
    assert first["run"]["status"] == "succeeded"
    job_ids = set(store.jobs)
    versions = len(store.versions)

    def fetch_partial(url: str) -> tuple[int, str]:
        if url.startswith(PUBLIC_API):
            page_one = json.dumps(
                {
                    "found_jobs": True,
                    "max_num_pages": 2,
                    "html": f'<li class="post-1604 job_listing status-publish"><a href="{TECHNICAL_URL}"><h3>{TECHNICAL_TITLE}</h3></a></li>',
                },
                ensure_ascii=False,
            )
            if "&page=1&" in url:
                return 200, page_one
            return 503, ""
        return _fetch(url)

    partial = run_source(CzuWpJobManagerAdapter(_source()), _source(), {"fetch_page": fetch_partial}, store)
    assert partial["run"]["status"] in {"partial", "failed"}
    assert not partial["completeness"].ok
    assert set(store.jobs) == job_ids
    assert len(store.versions) == versions
    assert all(job["consecutive_absence"] == 0 for job in store.jobs.values())


def test_generic_listing_url_is_rejected_for_publication() -> None:
    source = {"id": "d3s", "url": "https://www.d3s.mff.cuni.cz/positions/", "parser": "generic_listing_links"}
    ok, reason = official_detail_allowed("https://www.d3s.mff.cuni.cz/positions/", source)
    assert ok is False
    assert reason == "official-detail-url-is-generic-listing"
    ok, reason = official_detail_allowed("https://www.d3s.mff.cuni.cz/positions/2026-1/", source)
    assert ok is True
    assert reason is None

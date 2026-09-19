from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.transport import OfficialFetcher, dynamic_fetch_kwargs, fetch_official_page  # noqa: E402


SHELL = "<html><body><p>Please enable JavaScript to continue.</p></body></html>"
JOB_HTML = (
    "<html><body><div class='job_listings'>"
    "<li class='job_listing post-1604'><h3>Research engineer</h3></li>"
    "</div></body></html>"
)
TURNSTILE = "<html><body><div class='cf-turnstile' data-sitekey='x'></div></body></html>"


def test_ordinary_success_does_not_call_scrapling() -> None:
    calls = []

    def ordinary(_url: str) -> tuple[int, str]:
        calls.append("ordinary")
        return 200, JOB_HTML

    def boom(_url: str, **_kwargs):
        raise AssertionError("scrapling must not run")

    result = fetch_official_page(
        "https://jobs.czu.test/",
        ordinary=ordinary,
        scrapling_get=boom,
        scrapling_fetch=boom,
    )
    assert result.tool == "ordinary_http"
    assert result.status == 200
    assert calls == ["ordinary"]
    assert result.attempts[0]["tool"] == "ordinary_http"


def test_empty_ordinary_escalates_to_scrapling_get() -> None:
    def ordinary(_url: str) -> tuple[int, str]:
        return 200, ""

    def scrapling_get(_url: str) -> tuple[int, str]:
        return 200, JOB_HTML

    result = fetch_official_page(
        "https://jobs.czu.test/",
        ordinary=ordinary,
        scrapling_get=scrapling_get,
        scrapling_fetch=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("browser")),
    )
    assert result.tool == "scrapling_get"
    assert "Research engineer" in result.body
    assert [item["tool"] for item in result.attempts] == ["ordinary_http", "scrapling_get"]


def test_javascript_shell_escalates_to_scrapling_fetch_with_wait_selector() -> None:
    seen = {}

    def ordinary(_url: str) -> tuple[int, str]:
        return 200, SHELL

    def scrapling_get(_url: str) -> tuple[int, str]:
        return 200, SHELL

    def scrapling_fetch(url: str, wait_selector=None) -> tuple[int, str]:
        seen["url"] = url
        seen["wait_selector"] = wait_selector
        return 200, JOB_HTML

    result = fetch_official_page(
        "https://jobs.czu.test/",
        ordinary=ordinary,
        scrapling_get=scrapling_get,
        scrapling_fetch=scrapling_fetch,
        wait_selector="li.job_listing",
    )
    assert result.tool == "scrapling_fetch"
    assert seen["wait_selector"] == "li.job_listing"
    assert result.reasons[0] == "javascript-shell"


def test_turnstile_is_not_bypassed_with_a_browser() -> None:
    def ordinary(_url: str) -> tuple[int, str]:
        return 200, TURNSTILE

    result = fetch_official_page(
        "https://www.vetuni.cz/uredni-deska",
        ordinary=ordinary,
        scrapling_get=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("get")),
        scrapling_fetch=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("fetch")),
    )
    assert result.blocked is True
    assert result.reasons == ["turnstile"]
    assert result.tool == "ordinary_http"


def test_json_api_never_starts_a_browser() -> None:
    payload = "{}"

    def ordinary(_url: str) -> tuple[int, str]:
        return 503, ""

    def scrapling_get(_url: str) -> tuple[int, str]:
        return 503, payload

    result = fetch_official_page(
        "https://jobs.czu.test/wp-json/wp/v2/job-listings",
        ordinary=ordinary,
        scrapling_get=scrapling_get,
        scrapling_fetch=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("browser")),
    )
    assert "browser-not-used" in result.reasons
    assert result.tool == "scrapling_get"


def test_dynamic_fetch_does_not_wait_for_network_idle() -> None:
    kwargs = dynamic_fetch_kwargs(wait_selector="li.job_listing")
    assert kwargs["network_idle"] is False
    assert kwargs["timeout"] <= 20_000
    assert kwargs["wait_selector"] == "li.job_listing"


def test_missing_chromium_does_not_launch_browser(monkeypatch) -> None:
    monkeypatch.setattr("engine.transport.chromium_ready", lambda: False)

    def boom(*_args, **_kwargs):
        raise AssertionError("browser must stay off when Chromium is missing")

    monkeypatch.setattr("engine.transport._live_scrapling_fetch", boom)
    result = fetch_official_page(
        "https://jobs.czu.test/",
        ordinary=lambda _url: (200, SHELL),
        scrapling_get=lambda _url: (200, SHELL),
    )
    assert "browser-not-used" in result.reasons
    assert result.tool == "scrapling_get"


def test_official_fetcher_records_escalation_for_adapters() -> None:
    fetcher = OfficialFetcher(
        ordinary=lambda _url: (200, SHELL),
        scrapling_get=lambda _url: (200, SHELL),
        scrapling_fetch=lambda _url, wait_selector=None: (200, JOB_HTML),
        source={"waitSelector": "li.job_listing"},
    )
    status, body = fetcher("https://jobs.czu.test/")
    assert status == 200
    assert "job_listing" in body
    assert fetcher.attempts[0]["tool"] == "scrapling_fetch"

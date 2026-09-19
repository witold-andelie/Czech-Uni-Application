from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.runtime import probe_scrapling, require_http_fetcher  # noqa: E402
from engine.transport import fetch_official_page  # noqa: E402


SHELL = "<html><body><p>Please enable JavaScript to continue.</p></body></html>"


def test_probe_does_not_fetch_network() -> None:
    report = probe_scrapling()
    assert "httpFetcher" in report
    assert "dynamicFetcherImport" in report
    assert report["required"] is False


def test_require_http_fetcher_exits_when_cloud_runner_is_missing_scrapling() -> None:
    with pytest.raises(SystemExit):
        require_http_fetcher({"required": True, "httpFetcher": False})


def test_require_http_fetcher_is_silent_when_not_required() -> None:
    require_http_fetcher({"required": False, "httpFetcher": False})


def test_browser_escalation_can_be_disabled_by_env(monkeypatch) -> None:
    monkeypatch.setenv("SCRAPLING_ALLOW_BROWSER", "0")

    def boom(*_args, **_kwargs):
        raise AssertionError("browser must stay off")

    result = fetch_official_page(
        "https://jobs.czu.test/",
        ordinary=lambda _url: (200, SHELL),
        scrapling_get=lambda _url: (200, SHELL),
        scrapling_fetch=boom,
    )
    assert "browser-not-used" in result.reasons
    assert result.tool == "scrapling_get"
    monkeypatch.delenv("SCRAPLING_ALLOW_BROWSER", raising=False)
    os.environ.pop("SCRAPLING_ALLOW_BROWSER", None)

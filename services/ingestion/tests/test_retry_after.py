from __future__ import annotations

import io
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import harvest_nine_hei_jobs as jobs  # noqa: E402
from harvest_nine_hei_jobs import (  # noqa: E402
    MAX_IN_PROCESS_RETRY_SECONDS,
    REQUEST_RETRY_DELAYS,
    clear_host_cooldowns,
    export_host_cooldowns,
    load_host_cooldowns,
    parse_retry_after,
    set_host_cooldown,
)


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def _http_error(status: int, headers: dict[str, str], body: bytes = b"limited") -> urllib.error.HTTPError:
    message = Message()
    for key, value in headers.items():
        message[key] = value
    return urllib.error.HTTPError("https://jobs.example.test/list", status, "limited", message, io.BytesIO(body))


def test_parse_retry_after_delay_seconds_http_date_invalid_and_past() -> None:
    assert parse_retry_after("3600", NOW) == NOW + timedelta(seconds=3600)
    http_date = parse_retry_after("Sat, 12 Sep 2026 13:00:00 GMT", NOW)
    assert http_date == datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc)
    assert parse_retry_after("soon", NOW) is None
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", NOW) is None
    assert parse_retry_after("", NOW) is None


def test_long_retry_after_is_deferred_not_slept(monkeypatch) -> None:
    clear_host_cooldowns()
    sleeps: list[float] = []
    calls = 0

    def fake_urlopen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise _http_error(429, {"Retry-After": "3600"})

    monkeypatch.setattr(jobs.urllib.request, "urlopen", fake_urlopen)
    req = jobs.urllib.request.Request("https://jobs.example.test/list")
    result = jobs._request_bytes_with_retry(req, timeout=1, now=NOW, sleep_fn=sleeps.append)
    assert calls == 1
    assert result.status == 429
    assert result.deferred is True
    assert result.retry_at == NOW + timedelta(seconds=3600)
    assert sleeps == []
    assert export_host_cooldowns()["jobs.example.test"].endswith("Z")


def test_short_retry_after_is_slept_then_retried(monkeypatch) -> None:
    clear_host_cooldowns()
    sleeps: list[float] = []
    calls = 0

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args) -> bytes:
            return b"ok"

    def fake_urlopen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _http_error(503, {"Retry-After": "5"})
        return Response()

    monkeypatch.setattr(jobs.urllib.request, "urlopen", fake_urlopen)
    req = jobs.urllib.request.Request("https://jobs.example.test/list")
    result = jobs._request_bytes_with_retry(req, timeout=1, now=NOW, sleep_fn=sleeps.append)
    assert calls == 2
    assert result.status == 200
    assert result.deferred is False
    assert sleeps == [5]


def test_missing_or_malformed_retry_after_keeps_local_backoff(monkeypatch) -> None:
    clear_host_cooldowns()
    sleeps: list[float] = []
    calls = 0

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args) -> bytes:
            return b"ok"

    def fake_urlopen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _http_error(429, {"Retry-After": "not-a-delay"})
        return Response()

    monkeypatch.setattr(jobs.urllib.request, "urlopen", fake_urlopen)
    req = jobs.urllib.request.Request("https://jobs.example.test/list")
    result = jobs._request_bytes_with_retry(req, timeout=1, now=NOW, sleep_fn=sleeps.append)
    assert result.status == 200
    assert sleeps == [REQUEST_RETRY_DELAYS[0]]
    assert MAX_IN_PROCESS_RETRY_SECONDS == 30.0


def test_host_cooldown_survives_process_restart_without_new_request(monkeypatch) -> None:
    clear_host_cooldowns()
    set_host_cooldown("https://jobs.example.test/list", NOW + timedelta(hours=1))
    dumped = export_host_cooldowns()
    clear_host_cooldowns()
    load_host_cooldowns(dumped, NOW)

    def boom(*_args, **_kwargs):
        raise AssertionError("cooldown must not hit the network")

    monkeypatch.setattr(jobs.urllib.request, "urlopen", boom)
    req = jobs.urllib.request.Request("https://jobs.example.test/other")
    result = jobs._request_bytes_with_retry(req, timeout=1, now=NOW, sleep_fn=lambda _s: None)
    assert result.deferred is True
    assert result.status == 429

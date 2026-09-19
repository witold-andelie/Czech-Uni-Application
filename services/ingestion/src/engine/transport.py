"""Official-page transport: ordinary HTTP, then Scrapling GET, then Scrapling fetch.

Hard public pages must use the locally installed Scrapling 0.4.9
(https://github.com/D4Vinci/Scrapling). Login walls, paywalls and Turnstile
are recorded as access-control failures; they are never bypassed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

from engine.runtime import allow_browser as env_allow_browser

OrdinaryGet = Callable[[str], tuple[int, str]]
ScraplingCall = Callable[..., tuple[int, str]]

ACCESS_CONTROL_STATUSES = {401, 403, 407, 451}
TURNSTILE_MARKERS = (
    "cf-turnstile",
    "data-cf-turnstile",
    "challenges.cloudflare.com/turnstile",
    "cf-chl-bypass",
)
LOGIN_MARKERS = (
    "name=\"password\"",
    "name='password'",
    "type=\"password\"",
    "type='password'",
    "wp-login.php",
)
JS_SHELL_MARKERS = (
    "enable javascript",
    "please enable javascript",
    "please enable cookies",
    "requires javascript",
    "without javascript",
)
CHALLENGE_MARKERS = (
    "just a moment",
    "cf-challenge",
    "cf-browser-verification",
    "attention required",
    "checking your browser",
)
TAG = re.compile(r"<[^>]+>")


@dataclass
class FetchResult:
    status: int
    body: str
    tool: str
    final_url: str
    blocked: bool = False
    reasons: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)


def _plain(html: str) -> str:
    return TAG.sub(" ", html or "")


def _looks_json(url: str, body: str) -> bool:
    path = urlsplit(url).path.casefold()
    if "/wp-json/" in path or "jm-ajax" in path or path.endswith(".json"):
        return True
    stripped = (body or "").lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def access_control_reason(status: int, body: str) -> str | None:
    if status in ACCESS_CONTROL_STATUSES:
        return "http-access-control"
    lower = (body or "").casefold()
    if any(marker in lower for marker in TURNSTILE_MARKERS):
        return "turnstile"
    if status == 200 and any(marker in lower for marker in LOGIN_MARKERS) and len(_plain(body)) < 1200:
        return "login-wall"
    return None


def insufficiency_reason(status: int, body: str, required_markers: tuple[str, ...] = ()) -> str | None:
    if status != 200:
        return f"http-{status}" if status else "transport-error"
    if not (body or "").strip():
        return "empty-body"
    lower = body.casefold()
    text = _plain(body)
    if len(text.strip()) < 80 and any(marker in lower for marker in JS_SHELL_MARKERS):
        return "javascript-shell"
    if any(marker in lower for marker in CHALLENGE_MARKERS) and len(text.strip()) < 2000:
        return "browser-challenge"
    if required_markers and any(marker not in body for marker in required_markers):
        return "missing-required-markers"
    return None


def _record(attempts: list[dict[str, Any]], tool: str, status: int, body: str, reason: str | None) -> None:
    attempts.append(
        {
            "tool": tool,
            "status": status,
            "bytes": len((body or "").encode("utf-8")),
            "reason": reason,
        }
    )


def _live_scrapling_get(url: str, timeout: int = 40) -> tuple[int, str]:
    try:
        from scrapling.fetchers import Fetcher
    except ImportError:
        return 0, ""
    page = Fetcher.get(
        url,
        timeout=timeout,
        stealthy_headers=True,
        headers={"X-Crawler-Contact": "https://czech-uni-application.com/contact"},
    )
    body = page.body
    if isinstance(body, bytes):
        text = body.decode(getattr(page, "encoding", None) or "utf-8", errors="replace")
    else:
        text = getattr(page, "html_content", None) or str(body or "")
    return int(getattr(page, "status", 0) or 0), text


def _live_scrapling_fetch(url: str, timeout_ms: int = 45_000, wait_selector: str | None = None) -> tuple[int, str]:
    try:
        from scrapling.fetchers import DynamicFetcher
    except ImportError:
        return 0, ""
    kwargs: dict[str, Any] = {
        "headless": True,
        "timeout": timeout_ms,
        "wait": 1500,
        "disable_resources": False,
        "network_idle": True,
    }
    if wait_selector:
        kwargs["wait_selector"] = wait_selector
    page = DynamicFetcher.fetch(url, **kwargs)
    body = page.body
    if isinstance(body, bytes):
        text = body.decode(getattr(page, "encoding", None) or "utf-8", errors="replace")
    else:
        text = getattr(page, "html_content", None) or str(body or "")
    return int(getattr(page, "status", 0) or 0), text


def fetch_official_page(
    url: str,
    *,
    ordinary: OrdinaryGet | None = None,
    scrapling_get: ScraplingCall | None = None,
    scrapling_fetch: ScraplingCall | None = None,
    wait_selector: str | None = None,
    required_markers: tuple[str, ...] = (),
    allow_browser: bool = True,
) -> FetchResult:
    """Escalate only when the cheaper read is insufficient.

    Order: ordinary HTTP → Scrapling GET → Scrapling dynamic fetch.
    JSON/API URLs never start a browser. Access-control responses stop the chain.
    """
    attempts: list[dict[str, Any]] = []
    reasons: list[str] = []

    if ordinary is None:
        from harvest_nine_hei_jobs import request as ordinary

    status, body = ordinary(url)
    blocked = access_control_reason(status, body)
    weak = insufficiency_reason(status, body, required_markers)
    _record(attempts, "ordinary_http", status, body, blocked or weak)
    if blocked:
        return FetchResult(status, body, "ordinary_http", url, True, [blocked], attempts)
    if weak is None:
        return FetchResult(status, body, "ordinary_http", url, False, [], attempts)
    reasons.append(weak)

    get_fn = scrapling_get or _live_scrapling_get
    previous_status, previous_body = status, body
    try:
        get_status, get_body = get_fn(url)
    except Exception as exc:  # noqa: BLE001 — keep the previous body
        reasons.append(f"scrapling-get-error:{type(exc).__name__}")
        _record(attempts, "scrapling_get", 0, "", type(exc).__name__)
        get_status, get_body = previous_status, previous_body
    else:
        if get_status == 0 and not get_body:
            reasons.append("scrapling-get-unavailable")
            get_status, get_body = previous_status, previous_body
        blocked = access_control_reason(get_status, get_body)
        weak = insufficiency_reason(get_status, get_body, required_markers)
        _record(attempts, "scrapling_get", get_status, get_body, blocked or weak)
        if blocked:
            return FetchResult(get_status, get_body, "scrapling_get", url, True, reasons + [blocked], attempts)
        if weak is None:
            return FetchResult(get_status, get_body, "scrapling_get", url, False, reasons, attempts)
        reasons.append(weak)
        status, body = get_status, get_body

    if not allow_browser or not env_allow_browser() or _looks_json(url, body):
        reasons.append("browser-not-used")
        return FetchResult(status, body, attempts[-1]["tool"], url, False, reasons, attempts)

    fetch_fn = scrapling_fetch or _live_scrapling_fetch
    try:
        try:
            status, body = fetch_fn(url, wait_selector=wait_selector)
        except TypeError:
            status, body = fetch_fn(url)
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"scrapling-fetch-error:{type(exc).__name__}")
        _record(attempts, "scrapling_fetch", 0, "", type(exc).__name__)
        return FetchResult(status, body, attempts[-1]["tool"], url, False, reasons, attempts)

    if status == 0 and not body:
        reasons.append("scrapling-fetch-unavailable")
    blocked = access_control_reason(status, body)
    weak = insufficiency_reason(status, body, required_markers)
    _record(attempts, "scrapling_fetch", status, body, blocked or weak)
    if blocked:
        return FetchResult(status, body, "scrapling_fetch", url, True, reasons + [blocked], attempts)
    if weak:
        reasons.append(weak)
    return FetchResult(status, body, "scrapling_fetch", url, False, reasons, attempts)


def live_fetcher(source: dict | None = None) -> OfficialFetcher:
    """Production fetch_page: ordinary HTTP, then Scrapling GET, then browser."""
    from harvest_nine_hei_jobs import request

    return OfficialFetcher(ordinary=request, source=source or {})


class OfficialFetcher:
    """Adapter `fetch_page` callable with escalation metadata."""

    def __init__(
        self,
        *,
        ordinary: OrdinaryGet | None = None,
        scrapling_get: ScraplingCall | None = None,
        scrapling_fetch: ScraplingCall | None = None,
        source: dict | None = None,
    ):
        self.ordinary = ordinary
        self.scrapling_get = scrapling_get
        self.scrapling_fetch = scrapling_fetch
        self.source = source or {}
        self.attempts: list[dict[str, Any]] = []

    def __call__(self, url: str) -> tuple[int, str]:
        markers = self.source.get("requiredMarkers")
        required = tuple(markers) if isinstance(markers, list) else ()
        result = fetch_official_page(
            url,
            ordinary=self.ordinary,
            scrapling_get=self.scrapling_get,
            scrapling_fetch=self.scrapling_fetch,
            wait_selector=self.source.get("waitSelector"),
            required_markers=required,
            allow_browser=self.source.get("allowBrowser", True) is not False,
        )
        self.attempts.append(
            {
                "url": url,
                "tool": result.tool,
                "status": result.status,
                "blocked": result.blocked,
                "reasons": list(result.reasons),
                "attempts": result.attempts,
            }
        )
        return result.status, result.body

"""Scrapling capability probe for local and GitHub Actions collectors."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def allow_browser() -> bool:
    return os.environ.get("SCRAPLING_ALLOW_BROWSER", "1").strip().lower() not in {"0", "false", "no", "off"}


def probe_scrapling() -> dict[str, Any]:
    """Import-only probe. Does not fetch university pages."""
    report: dict[str, Any] = {
        "version": None,
        "httpFetcher": False,
        "dynamicFetcherImport": False,
        "playwrightImport": False,
        "allowBrowser": allow_browser(),
        "required": env_flag("SCRAPLING_REQUIRED"),
        "error": None,
    }
    try:
        import scrapling

        report["version"] = getattr(scrapling, "__version__", None)
        from scrapling.fetchers import Fetcher  # noqa: F401

        report["httpFetcher"] = True
        from scrapling.fetchers import DynamicFetcher  # noqa: F401

        report["dynamicFetcherImport"] = True
    except Exception as exc:  # noqa: BLE001
        report["error"] = type(exc).__name__
        return report
    try:
        import playwright  # noqa: F401

        report["playwrightImport"] = True
    except Exception:
        report["playwrightImport"] = False
    return report


def write_runtime_report(path: Path) -> dict[str, Any]:
    report = probe_scrapling()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def require_http_fetcher(report: dict[str, Any] | None = None) -> dict[str, Any]:
    current = report or probe_scrapling()
    if current.get("required") and not current.get("httpFetcher"):
        raise SystemExit(
            "Scrapling HTTP Fetcher is required on this runner (SCRAPLING_REQUIRED=1) "
            "but scrapling.fetchers.Fetcher could not be imported"
        )
    return current

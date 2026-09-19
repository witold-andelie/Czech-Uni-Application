"""Job-source adapters keyed by registry ``parser`` values."""

from __future__ import annotations

from adapters.jobs.czu_wp_job_manager import CzuWpJobManagerAdapter

ADAPTERS_BY_PARSER = {
    "czu_wp_job_manager": CzuWpJobManagerAdapter,
}


def adapter_for(source: dict) -> object | None:
    parser = source.get("parser")
    cls = ADAPTERS_BY_PARSER.get(parser)
    if cls is None:
        return None
    return cls(source)

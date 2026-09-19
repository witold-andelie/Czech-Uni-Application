"""Job-source adapters keyed by registry ``parser`` values."""

from __future__ import annotations

from adapters.jobs.cuni_ajax import CuniAjaxAdapter
from adapters.jobs.czu_wp_job_manager import CzuWpJobManagerAdapter
from adapters.jobs.registered_listing import HarvestListingAdapter, uses_binary_or_private_api

ADAPTERS_BY_PARSER = {
    "cuni_ajax": CuniAjaxAdapter,
    "czu_wp_job_manager": CzuWpJobManagerAdapter,
}


def adapter_for(source: dict) -> object | None:
    parser = source.get("parser")
    cls = ADAPTERS_BY_PARSER.get(parser)
    if cls is not None:
        return cls(source)
    if not parser or uses_binary_or_private_api(source):
        return None
    return HarvestListingAdapter(source)


def adapter_sources(registry: list[dict] | None = None) -> list[dict]:
    from harvest_nine_hei_jobs import load_registered_job_sources

    sources = registry if registry is not None else load_registered_job_sources()
    return [item for item in sources if adapter_for(item) is not None]

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

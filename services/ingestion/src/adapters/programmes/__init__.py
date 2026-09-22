"""Programme source adapters keyed by registry ``sourceType`` values."""

from __future__ import annotations

from adapters.programmes.programme_listing import ProgrammeListingAdapter

PROGRAMME_SOURCE_TYPES = frozenset(
    {
        "official_programme_directory",
        "official_university_programme_catalogue",
    }
)


def programme_adapter_for(source: dict) -> object | None:
    if source.get("sourceType") not in PROGRAMME_SOURCE_TYPES:
        return None
    return ProgrammeListingAdapter(source)


def programme_sources(registry: list[dict] | None = None) -> list[dict]:
    sources = registry if registry is not None else _registered_sources()
    return [item for item in sources if programme_adapter_for(item) is not None]


def _registered_sources() -> list[dict]:
    from harvest_nine_hei_jobs import load_registered_programme_sources

    return load_registered_programme_sources()
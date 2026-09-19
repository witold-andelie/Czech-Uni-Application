"""Official vacancy URL rules used before a record can be published."""

from __future__ import annotations

from urllib.parse import urlsplit


GENERIC_PATHS = {
    "/",
    "/en",
    "/en/",
    "/cs",
    "/cs/",
}


def is_http_url(value: str | None) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").casefold()
    return bool(host)


def same_resource(left: str, right: str) -> bool:
    def norm(url: str) -> tuple[str, str]:
        parsed = urlsplit(url.strip())
        path = parsed.path.rstrip("/") or "/"
        return ((parsed.hostname or "").casefold(), path.casefold())

    return norm(left) == norm(right)


def is_generic_listing_url(url: str, source: dict) -> bool:
    """True when *url* is the source's listing/home page, not a vacancy document.

    A source that is itself a single-vacancy document (``singleVacancyDocument``)
    is allowed to reuse its entry URL.
    """
    if source.get("singleVacancyDocument") is True:
        return False
    listing = source.get("url") or source.get("publicUrl") or source.get("listingUrl")
    if isinstance(listing, str) and listing.strip() and same_resource(url, listing):
        return True
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/") or "/"
    if path.casefold() in GENERIC_PATHS:
        return True
    host = (parsed.hostname or "").casefold()
    if host == "www.d3s.mff.cuni.cz" and path.casefold() == "/positions":
        return True
    return False


def official_detail_allowed(url: str, source: dict) -> tuple[bool, str | None]:
    if not is_http_url(url):
        return False, "official-detail-url-not-https"
    if is_generic_listing_url(url, source):
        return False, "official-detail-url-is-generic-listing"
    return True, None

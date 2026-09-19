"""Official vacancy URL rules used before a record can be published."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit


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


def vacancy_query_id(url: str) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    for key in ("pracid", "id"):
        values = query.get(key) or []
        if values and values[0].strip():
            return key, values[0].strip()
    return None


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
        url_id = vacancy_query_id(url)
        listing_id = vacancy_query_id(listing)
        if url_id and url_id != listing_id:
            return False
        return True
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/") or "/"
    if path.casefold() in GENERIC_PATHS:
        return True
    host = (parsed.hostname or "").casefold()
    if host == "www.d3s.mff.cuni.cz" and path.casefold() == "/positions":
        return True
    if host in {"cuni.cz", "www.cuni.cz"} and path.casefold().endswith("/uken-1573.html"):
        if not parse_qs(parsed.query).get("pracid"):
            return True
    if host == "www.muni.cz":
        parts = [item for item in path.casefold().split("/") if item]
        if parts[:4] == ["en", "about-us", "careers", "vacancies"] and (len(parts) < 5 or not parts[4].isdigit()):
            return True
    if host == "jobs.czu.cz" and not path.casefold().startswith("/job/"):
        return True
    return False


def official_detail_allowed(url: str, source: dict) -> tuple[bool, str | None]:
    if not is_http_url(url):
        return False, "official-detail-url-not-https"
    if is_generic_listing_url(url, source):
        return False, "official-detail-url-is-generic-listing"
    return True, None

"""EURAXESS as a discovery source for Czech research vacancies (owner decision 2026-10-03).

EURAXESS carries vacancies that Czech universities post nowhere else we read:
doctoral studentship topics (ČVUT faculties, VŠCHT), faculty and research-centre
postdocs (CUNI Law, MUNI Medicine, CEITEC). Facts come from the EURAXESS notice;
the employer is the "Organisation/Company" it names, resolved to an MŠMT
university; the application target is an address on that university's own
domains found in the notice. EURAXESS itself is never the application target
(a record without an official address is kept but not published), and a
vacancy that a direct university source already carries is not published twice
(auto_review.py). Public research institutions (AV ČR institutes and other
v. v. i.) are employers too, from the MŠMT register (harvest_research_
institutions.py); their own website host, not the shared cas.cz, is where the
application address must be. Other employers (hospitals, companies) stay out.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[3]
EURAXESS_HOSTS = {"euraxess.ec.europa.eu", "www.euraxess.cz", "euraxess.cz"}

# Read each notice once (owner, 2026-10-08). EURAXESS throttles GitHub's
# shared runners after about twenty quick requests; reading every notice of
# every listing page daily, then again for the recheck and the live check,
# came to some 220 requests a day. A notice already read is not read again
# until its title changes or its refresh is due, and the day's listing
# stands in for the notice in the recheck and the live title check.
NOTICES_PATH = ROOT / "data" / "sources" / "coverage" / "euraxess-notices.json"
LISTING_PATH = ROOT / "data" / "sources" / "coverage" / "euraxess-listing.json"
CANDIDATES_PATH = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
NOTICE_REFRESH_DAYS = 7
# A listing older than this is not evidence that a notice is still posted.
LISTING_MAX_AGE_HOURS = 72


def _read_json(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, dict) else default


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10)
    temporary.write_bytes(text.encode("utf-8"))
    temporary.replace(path)


def _parse_time(value: object):
    from datetime import datetime, timezone

    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _iso(moment) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_notices(path: Path | None = None) -> dict[str, dict]:
    notices = _read_json(path or NOTICES_PATH, {}).get("notices")
    return dict(notices) if isinstance(notices, dict) else {}


def save_notices(notices: dict[str, dict], path: Path | None = None) -> None:
    _write_json(path or NOTICES_PATH, {"schemaVersion": 1, "notices": notices})


def notice_due(entry: dict | None, title: str, code: str, now) -> bool:
    """True when a listed notice must be read: new, retitled or due a refresh.

    Refreshes spread over a week by the notice number, so a first full read
    does not come due again on a single day.
    """
    from datetime import timedelta

    if not isinstance(entry, dict) or entry.get("title") != title:
        return True
    fetched = _parse_time(entry.get("fetchedAt"))
    if fetched is None:
        return True
    spread = int(re.sub(r"\D", "", code) or 0) % NOTICE_REFRESH_DAYS
    return now - fetched >= timedelta(days=NOTICE_REFRESH_DAYS + spread)


def stored_jobs_by_url(path: Path | None = None) -> dict[str, dict]:
    """Stored candidate records keyed by their EURAXESS notice URL."""
    jobs = _read_json(path or CANDIDATES_PATH, {}).get("jobs") or []
    return {
        str(job.get("sourceUrl")): job
        for job in jobs
        if isinstance(job, dict) and (urlsplit(str(job.get("sourceUrl") or "")).hostname or "").lower() in EURAXESS_HOSTS
    }


def save_listing(notices: dict[str, str], complete: bool, now, path: Path | None = None) -> None:
    """The day's listing: notice URL -> title, and whether every page was read.

    An incomplete read does not replace a complete listing still young enough
    to stand as evidence (LISTING_MAX_AGE_HOURS): what it lacks is not news.
    """
    from datetime import timedelta

    target = path or LISTING_PATH
    if not complete:
        kept = _read_json(target, {})
        checked = _parse_time(kept.get("checkedAt"))
        if kept.get("complete") and checked is not None and now - checked <= timedelta(hours=LISTING_MAX_AGE_HOURS):
            return
    _write_json(target, {"schemaVersion": 1, "checkedAt": _iso(now), "complete": bool(complete), "notices": notices})


def listing_evidence(url: str, now, path: Path | None = None) -> dict | None:
    """What a recent complete listing says of a notice, or None without one.

    {"listed": bool, "title": str | None, "checkedAt": str}
    """
    from datetime import timedelta

    listing = _read_json(path or LISTING_PATH, {})
    checked = _parse_time(listing.get("checkedAt"))
    if not listing.get("complete") or checked is None or now - checked > timedelta(hours=LISTING_MAX_AGE_HOURS):
        return None
    notices = listing.get("notices") if isinstance(listing.get("notices"), dict) else {}
    return {"listed": url in notices, "title": notices.get(url), "checkedAt": listing.get("checkedAt")}


def official_post_url(url: str, path: Path | None = None) -> str | None:
    """The employer's own page for a notice, when its first read found the post there."""
    for entry in load_notices(path).values():
        if isinstance(entry, dict) and entry.get("url") == url and entry.get("officialPostUrl"):
            return str(entry["officialPostUrl"])
    return None

# English and other names EURAXESS uses that the official register does not.
ALIASES = {
    "ceitec mu": "msmt-vs_14000",
    "ceitec masaryk university": "msmt-vs_14000",
    "ceitec but": "msmt-vs_26000",
    "ceitec vut": "msmt-vs_26000",
    "masaryk university": "msmt-vs_14000",
    "charles university": "msmt-vs_11000",
    "czech technical university": "msmt-vs_21000",
    "czech technical university in prague": "msmt-vs_21000",
    "ctu in prague": "msmt-vs_21000",
    "ciirc": "msmt-vs_21000",
    "brno university of technology": "msmt-vs_26000",
    "university of chemistry and technology": "msmt-vs_22000",
    "vscht": "msmt-vs_22000",
    "vscht praha": "msmt-vs_22000",
    "uct prague": "msmt-vs_22000",
    "vsb technical university of ostrava": "msmt-vs_27000",
    "vsb tu ostrava": "msmt-vs_27000",
    "it4innovations": "msmt-vs_27000",
    "palacky university": "msmt-vs_15000",
    "palacky university olomouc": "msmt-vs_15000",
    "university of hradec kralove": "msmt-vs_18000",
    "univerzita hradec kralove": "msmt-vs_18000",
    "mendel university": "msmt-vs_43000",
    "tomas bata university": "msmt-vs_28000",
    "university of west bohemia": "msmt-vs_23000",
    "university of south bohemia": "msmt-vs_12000",
    "technical university of liberec": "msmt-vs_24000",
    "czech university of life sciences": "msmt-vs_41000",
    "university of pardubice": "msmt-vs_25000",
    "university of ostrava": "msmt-vs_17000",
    "silesian university": "msmt-vs_19000",
    "prague university of economics and business": "msmt-vs_31000",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", unescape(str(text or ""))).encode("ascii", "ignore").decode().lower()
    # "Archeology"/"Archaeology": the Academy writes both for one institute.
    text = text.replace("archeolog", "archaeolog")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


RESEARCH_INSTITUTIONS = ROOT / "data" / "sources" / "research-institutions.json"


def research_institutions() -> list[dict]:
    if not RESEARCH_INSTITUTIONS.is_file():
        return []
    return json.loads(RESEARCH_INSTITUTIONS.read_text(encoding="utf-8")).get("institutions") or []


def research_name_variants(record: dict) -> set[str]:
    """The ways notices name a public research institution.

    "Fyzikální ústav AV ČR, v. v. i." / "Institute of Physics of the CAS" are
    also written "... of the Czech Academy of Sciences" or "... Academy of
    Sciences of the Czech Republic"; the legal suffix is often left out.
    """
    variants: set[str] = set()
    czech = _norm(record.get("officialName") or "")
    if czech:
        variants.add(czech)
        variants.add(re.sub(r"\s+(?:v v i|verejna vyzkumna instituce)$", "", czech))
    english = _norm(record.get("officialNameEn") or "")
    if english:
        variants.add(english)
        for academy in ("the czech academy of sciences", "the academy of sciences of the czech republic"):
            variants.add(english.replace("the cas", academy))
        variants.add(english.replace(" of the cas", " cas"))
    return {variant for variant in variants if len(variant) >= 12}


def research_hosts() -> dict[str, set[str]]:
    """Each institution's own website host (asu.cas.cz, not the shared cas.cz)."""
    return {item["id"]: {item["webHost"]} for item in research_institutions() if item.get("webHost")}


@lru_cache(maxsize=1)
def name_index() -> dict[str, str]:
    """Normalised employer names (register, studyin cs/en, aliases, research institutions) -> id."""
    index: dict[str, str] = {}
    baseline = json.loads((ROOT / "data" / "sources" / "msmt-hei-baseline.json").read_text(encoding="utf-8"))
    for item in baseline.get("institutions") or []:
        if item.get("officialName"):
            index[_norm(item["officialName"])] = item["id"]
    studyin = ROOT / "data" / "sources" / "admissions" / "studyin-programmes.json"
    if studyin.is_file():
        for row in json.loads(studyin.read_text(encoding="utf-8")).get("programmes") or []:
            for name in (row.get("institutionNames") or {}).values():
                if name and row.get("institutionId"):
                    index.setdefault(_norm(name), row["institutionId"])
    index.update(ALIASES)
    for record in research_institutions():
        for variant in research_name_variants(record):
            index.setdefault(variant, record["id"])
    return index


def resolve_employer(organisation: str) -> str | None:
    """The MŠMT university an organisation string names, by its longest known name."""
    text = _norm(organisation)
    if not text:
        return None
    best = None
    for name, ident in name_index().items():
        if len(name) >= 4 and (text == name or text.startswith(name + " ") or f" {name} " in f" {text} "):
            if best is None or len(name) > len(best[0]):
                best = (name, ident)
    return best[1] if best else None


def parse_search(html: str, page_url: str) -> list[dict]:
    """Rows of one EURAXESS search-result page: title, detail URL, organisation text."""
    rows: list[dict] = []
    seen: set[str] = set()
    for block in re.split(r"(?=<article\b)", html):
        if not block.startswith("<article"):
            continue
        link = re.search(r'href="(/jobs/(\d+))"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        url = urljoin(page_url, link.group(1))
        if url in seen:
            continue
        seen.add(url)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(link.group(3)))).strip()
        rows.append({"title": title, "code": f"eu{link.group(2)}", "sourceUrl": url})
    return rows


def page_urls(html: str, first_url: str, page_size: int = 10) -> list[str]:
    """Every further result page, from the stated total ("Search results (93)")."""
    match = re.search(r"Search results\s*\((\d+)\)", re.sub(r"<[^>]+>", " ", html))
    if not match:
        return []
    total = int(match.group(1))
    pages = (total + page_size - 1) // page_size
    joiner = "&" if "?" in first_url else "?"
    return [f"{first_url}{joiner}page={number}" for number in range(1, pages)]


# The work location every card of the registered search (job_country:747) names.
COUNTRY_NAME = "Czech Republic"


def listing_problem(html: str, page_url: str, earlier: set[str]) -> str | None:
    """Why a search page is not a page of the Czech listing asked for, or None.

    On 2026-10-10 the runner was served the unfiltered first page for every
    request: ten offers from the Netherlands and Scotland, the same ten on all
    sixty pages read, and a total past the page limit. Such a page is not the
    listing; its offers are not read as Czech notices, and paging stops.
    """
    cards = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block))
        for block in re.split(r"(?=<article\b)", html)
        if block.startswith("<article") and re.search(r'href="/jobs/\d+"', block)
    ]
    foreign = sum(1 for card in cards if COUNTRY_NAME not in card)
    # Most cards, not every one: an offer in several countries may name
    # Czechia past what its card shows.
    if cards and foreign * 2 > len(cards):
        return "unfiltered-listing"
    urls = {row["sourceUrl"] for row in parse_search(html, page_url)}
    if urls and urls <= earlier:
        return "page-parameter-ignored"
    return None


def detail_fields(text: str) -> dict:
    """Organisation, website and e-mail fields of a EURAXESS notice's visible text."""
    def field(label: str, stop: str) -> str | None:
        match = re.search(rf"\b{label}\s+(.+?)\s+(?:{stop})\b", text)
        return match.group(1).strip() if match else None

    return {
        "organisation": field("Organisation/Company", "Department|Research Field|Researcher Profile"),
        "website": (re.search(r"\bWebsite\s+(https?://\S+)", text) or [None, None])[1],
        "email": (re.search(r"\bE-mail\s+(\S+@\S+)", text) or [None, None])[1],
    }


def official_application_url(html: str, page_url: str, website: str | None, employer_hosts: set[str]) -> str | None:
    """The first link in the notice on the employer's own domains, the Website field first."""
    def on_employer(url: str) -> bool:
        host = urlsplit(url).netloc.lower().split(":")[0]
        return url.startswith("https://") and any(host == h or host.endswith("." + h) for h in employer_hosts)

    candidates = [website] if website else []
    candidates += [unescape(href) for href in re.findall(r'href="(https?://[^"]+)"', html)]
    for url in candidates:
        if url and urlsplit(url).netloc.lower() not in EURAXESS_HOSTS and on_employer(url):
            return url
    return None

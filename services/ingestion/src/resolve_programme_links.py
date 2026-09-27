"""Resolve a school-owned programme page for every register inventory row.

The MŠMT register extract names a programme but never links to the page the
university itself publishes for it, so every inventory card would otherwise
point at a university-level application portal. This module collects
candidate programme pages from each school's own site (already harvested
school-owned catalogue records, catalogue pages, and sitemaps) and links a
row only when the normalised page text equals the normalised register title
for the same degree and teaching language.

Matching is deliberately exact. Fuzzy or partial matching would happily bind
"Chemie" to "Chemie se zaměřením na vzdělávání" and "Historické vědy" to
"Pomocné vědy historické"; a wrong "specific" link is worse than the
university-site fallback the UI already shows. A row that cannot be proven
stays unresolved and is reported, never guessed.

Discovery is offline ingestion: no visitor request ever reaches a school.
Does not write data/published/.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable, Iterable

from build_nine_hei_inventory import DEGREE_CODE as REGISTER_DEGREES, row_id

ROOT = Path(__file__).resolve().parents[3]
REGISTER_DIR = ROOT / "data" / "sources" / "programmes"
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
SOURCES_CONFIG = ROOT / "config" / "programme-page-sources.json"
DEFAULT_OUT = ROOT / "data" / "sources" / "admissions" / "programme-links.json"

LINK_KIND = "school_programme_page"
PER_HOST_SLEEP_SECONDS = 1.0
# docs/REFRESH_POLICY.md: a link confirmed inside this window is not re-fetched.
RECHECK_AFTER_SECONDS = 120 * 3600
# Harvested school files write degrees as codes ("b"), the register as names
# ("bachelor"); both spellings must reach the same code.
NAME_BY_CODE = {code: name for name, code in REGISTER_DEGREES.items()}

SITEMAP_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemapindex.xml",
    "/en/sitemap.xml",
    "/sitemap1.xml",
)
# Words that mark a page as a programme catalogue (school's own navigation).
CATALOGUE_TOKEN_RE = re.compile(
    r"(program|obor|studijn[íi]|nab[íi]dk|degree|combination|kombinac|přij[íi]m|prijim)",
    re.I,
)
# Words that mark a URL as a programme page rather than a news post.
PROGRAMME_PAGE_TOKEN_RE = re.compile(
    r"(program|obor|studijn[íi]|sm[eě]r|combination|kombinac)", re.I
)
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
ANCHOR_RE = re.compile(r"<a\b[^>]*?href\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", re.I | re.S)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
# A catalogue page often states the level next to the programme name ("Kynologie
# (Bc.)", "Kynologie - master", /programy/bakalar/...). Only a level the school's
# own page states is used: a level found together with a conflicting one is
# treated as unstated, never chosen between.
BACHELOR_TOKEN_RE = re.compile(
    r"(bakal[aá]řsk\w*|bakalarsk\w*|bachelor\w*|\bbc\b|\bbsc\b|b\.?c\.)", re.I
)
MASTER_TOKEN_RE = re.compile(
    r"(magistersk\w*|navazuj[ií]c\w*|master\w*|\bmgr\b|\bmsc\b|m\.?sc\.)", re.I
)
DOCTORAL_TOKEN_RE = re.compile(
    r"(doktorsk\w*|doktorsk\w*|phd|ph\.?\s?d\.?|doctor\w*)", re.I
)
ID_SEGMENT_RE = re.compile(r"^(?:r|node|program|obor|id)?-?\d+$", re.I)
NEUTRAL_SEGMENTS = {
    "en",
    "cs",
    "cz",
    "programmes",
    "programs",
    "programy",
    "program",
    "study",
    "studium",
    "studuj",
    "pro-studenty",
    "pro-uchazece",
    "uchazeci",
    "applicants",
    "students",
    "bachelor",
    "master",
    "doctoral",
    "phd",
    "bakalarske",
    "magisterske",
    "doktorske",
    "obory",
    "nabidka",
    "katalog",
}

NOTE = (
    "School-owned programme page links for the MŠMT register inventory. "
    "Each link was resolved from the university's own site by exact normalised "
    "title/degree/language equality; a row without a proven page keeps the "
    "university-site fallback and is listed under unresolved. No fuzzy or "
    "partial matching, and no invented URLs."
)

FetchPage = Callable[[str], tuple[int, str]]

# Outcomes that remove a link again: the school's own page contradicts the
# binding, so the row goes back to the university-site fallback.
DROP_REASONS = {
    "dropped_404": "page_returned_404",
    "dropped_level_mismatch": "page_states_another_level",
}

# A school the run never read, because the budget ran out first. It is not a
# report about the school's pages: the next run that reaches it decides again,
# and until then it keeps whatever a previous run proved (docs/REFRESH_POLICY.md).
NOT_ATTEMPTED = "not_attempted"

# A candidate whose level the school's own page never states. It can still be
# bound when the register holds exactly one row of that exact title.
UNKNOWN_DEGREE = "u"


def degree_stated(text: str, url: str = "") -> str:
    """The study level a page states in its own words, or UNKNOWN_DEGREE.

    Czech and English catalogues both put the level beside the programme name
    ("Kynologie (Bc.)", "Kynologie - master") and in the URL
    (/programy/bakalar/). Only a level actually written down is returned: two
    different levels, or none at all, give UNKNOWN_DEGREE, and an unknown level
    binds a page only when the title identifies exactly one register row.
    """
    stated = ""
    for pattern, degree in (
        (BACHELOR_TOKEN_RE, "b"),
        (MASTER_TOKEN_RE, "m"),
        (DOCTORAL_TOKEN_RE, "d"),
    ):
        if not pattern.search(text or ""):
            continue
        if stated and stated != degree:
            return UNKNOWN_DEGREE
        stated = degree
    return stated or UNKNOWN_DEGREE


# --------------------------------------------------------------------------- #
# normalisation
# --------------------------------------------------------------------------- #


def normalise(value: object) -> str:
    """Conservative equality key: case, diacritic and punctuation insensitive.

    Mirrors foldKey() in apps/web/src/lib/expandInventory.ts so a title the
    browser treats as equal has the same key here.
    """
    text = "" if value is None else str(value)
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[^\W_]+", stripped, re.UNICODE))


def host_of(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").casefold()
    except ValueError:
        return ""


def registrable_host(url_or_host: str) -> str:
    host = host_of(url_or_host) or str(url_or_host).casefold()
    host = host.removeprefix("www.")
    labels = [label for label in host.split(".") if label]
    # .cz publishes no public-suffix list that would change this: the last two
    # labels are the registrable domain for every school in the MŠMT baseline.
    return ".".join(labels[-2:]) if len(labels) > 2 else ".".join(labels)


def is_https_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urllib.parse.urlsplit(value.strip())
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False
    return bool(parsed.hostname)


def https_twin(url: str) -> str | None:
    """The https address of a plain-http page, or None if it is not one.

    A university's own site often links its programme pages over plain http
    (UJEP's faculty site, CVUT's faculty site, IS MU). Such a page is still the
    school's own page for exactly that programme, so the resolver asks whether
    the school serves the same page over https rather than dropping it.
    """
    if not url.startswith("http://"):
        return None
    return "https://" + url[len("http://") :]


def absolute_url(base: str, href: str) -> str | None:
    href = (href or "").strip()
    if not href or href.startswith("#") or href.casefold().startswith(("mailto:", "tel:", "javascript:")):
        return None
    try:
        return urllib.parse.urljoin(base, href)
    except ValueError:
        return None


def degree_code(value: object) -> str:
    """Degree code from a register name ("bachelor") or a harvested code ("b")."""
    text = str(value if value is not None else "").strip().lower()
    if text in REGISTER_DEGREES:
        return REGISTER_DEGREES[text]
    if text in NAME_BY_CODE:
        return text
    return "u"


def slug_text(url: str) -> str:
    """Normalised last meaningful path segment: /programmes/agriculture-and-food/."""
    try:
        path = urllib.parse.urlsplit(url).path
    except ValueError:
        return ""
    segments = [segment for segment in path.split("/") if segment]
    while segments and (
        ID_SEGMENT_RE.match(segments[-1]) or segments[-1].casefold() in NEUTRAL_SEGMENTS
    ):
        segments.pop()
    if not segments:
        return ""
    return normalise(urllib.parse.unquote(segments[-1]).replace("-", " ").replace("_", " "))


def visible_text(fragment: str) -> str:
    without = TAG_RE.sub(" ", fragment or "")
    return " ".join(unescape(without).split())


def page_headings(body: str) -> list[str]:
    titles = [visible_text(match.group(1)) for match in TITLE_RE.finditer(body or "")][:2]
    headings = [visible_text(match.group(1)) for match in H1_RE.finditer(body or "")][:2]
    return [item for item in titles + headings if item]


def page_title_text(body: str) -> str:
    """The page's own title line, where a school states the study level."""
    headings = page_headings(body)
    return headings[0] if headings else ""


def anchors(body: str, base_url: str) -> list[tuple[str, str]]:
    """(absolute url, normalised anchor text) for every link on the page."""
    found: list[tuple[str, str]] = []
    for match in ANCHOR_RE.finditer(body or ""):
        url = absolute_url(base_url, unescape(match.group(2)))
        if not url:
            continue
        found.append((url, normalise(visible_text(match.group(3)))))
    return found


def sitemap_urls(body: str) -> list[str]:
    return [unescape(match.group(1)).strip() for match in LOC_RE.finditer(body or "")]


# --------------------------------------------------------------------------- #
# register rows
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Row:
    ident: str
    institution_id: str
    title: str
    degree: str
    language: str
    faculty: str


@dataclass
class Link:
    url: str
    row_id: str
    institution_id: str
    degree: str
    language: str
    matched_title: str
    row_title: str
    source_url: str
    matched_by: str
    reachability: str
    matched_at: str
    checked_at: str = ""
    page_title: str | None = None


@dataclass
class Candidate:
    url: str
    title: str
    degree: str = "u"
    language: str = ""
    source_url: str = ""
    matched_by: str = ""
    observed_at: str = ""


@dataclass
class Binding:
    """Register rows a candidate page could belong to, plus the reason if not one."""

    rows: list[Row] = field(default_factory=list)
    language: str = ""
    reason: str = ""


def register_rows(register_dir: Path | None = None) -> dict[str, list[Row]]:
    """Register rows keyed by institution, using the inventory's own row ids."""
    source = register_dir or REGISTER_DIR
    rows_by_institution: dict[str, list[Row]] = {}
    for path in sorted(source.glob("vs_*.json")):
        institution_id = f"msmt-{path.stem}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        seen: set[str] = set()
        for programme in payload.get("programmes") or []:
            if not isinstance(programme, dict):
                continue
            title = str(programme.get("titleOriginal") or "").strip()
            language = str(programme.get("teachingLanguage") or "").strip().lower()
            if not title or not language:
                continue
            degree = degree_code(programme.get("degree"))
            faculty = str(programme.get("facultyName") or "").strip()
            ident = row_id(institution_id, title, NAME_BY_CODE.get(degree, "unknown"), language, faculty)
            if ident in seen:
                continue
            seen.add(ident)
            rows_by_institution.setdefault(institution_id, []).append(
                Row(
                    ident=ident,
                    institution_id=institution_id,
                    title=title,
                    degree=degree,
                    language=language,
                    faculty=faculty,
                )
            )
    for rows in rows_by_institution.values():
        rows.sort(key=lambda item: (normalise(item.title), item.degree, item.language))
    return rows_by_institution


# --------------------------------------------------------------------------- #
# exact matching
# --------------------------------------------------------------------------- #


class Match:
    """One school's index of its own normalised register titles."""

    def __init__(self, rows: Iterable[Row]):
        self.rows = list(rows)
        self.by_language: dict[tuple[str, str, str], list[Row]] = {}
        self.by_title_degree: dict[tuple[str, str], list[Row]] = {}
        # A catalogue anchor often states no level at all; the title alone then
        # has to identify exactly one register row for the page to be bound.
        self.by_title: dict[str, list[Row]] = {}
        for row in self.rows:
            key = (normalise(row.title), row.degree, row.language)
            self.by_language.setdefault(key, []).append(row)
            self.by_title_degree.setdefault((normalise(row.title), row.degree), []).append(row)
            self.by_title.setdefault(normalise(row.title), []).append(row)

    def bind(self, candidate: Candidate) -> Binding:
        """Bind a candidate page to register rows, or explain why it cannot.

        The source's own teaching language decides first. A cross-language
        candidate is accepted only when exactly one row of that degree carries
        the normalised title; two rows means the register itself is ambiguous
        and every one of them keeps the university-site fallback.
        """
        title_key = normalise(candidate.title)
        if candidate.degree and candidate.degree != UNKNOWN_DEGREE:
            exact = self.by_language.get((title_key, candidate.degree, candidate.language)) or []
            if len(exact) == 1:
                return Binding(rows=exact, language=candidate.language)
            if len(exact) > 1:
                return Binding(rows=exact, reason="ambiguous_register_rows")
            cross = self.by_title_degree.get((title_key, candidate.degree)) or []
            if len(cross) == 1:
                return Binding(rows=cross, language=cross[0].language)
            if len(cross) > 1:
                return Binding(rows=cross, reason="ambiguous_register_rows")
            return Binding(rows=[])

        # No level stated on the page: bind only when the exact title names one
        # register row, so a bachelor page can never take over a master's row.
        by_title = self.by_title.get(title_key) or []
        if len(by_title) == 1:
            return Binding(rows=by_title, language=by_title[0].language)
        if len(by_title) > 1:
            return Binding(rows=by_title, reason="ambiguous_register_rows")
        return Binding(rows=[])


def slug_agrees(url: str, row_title: str) -> bool:
    """Does the page's own URL slug restate this programme's name?

    A page whose slug contradicts the name is not that programme's page: the
    CZU English harvest carries one record whose link is a test programme URL.
    Used for ranking only, because plenty of schools publish programme pages
    at id-shaped URLs (e.g. /program/12345) where no slug exists at all.
    """
    slug = slug_text(url)
    if not slug:
        return False
    expected = normalise(row_title)
    if slug == expected:
        return True
    # CMS duplicate-slug artifacts append a numeric suffix ("...-2").
    return re.sub(r"\s\d+$", "", slug) == expected


SOURCE_RANK = {
    "school_harvested_programme_page": 0,
    "school_catalogue_anchor": 1,
    "school_catalogue_sitemap": 2,
    "school_sitemap_slug": 3,
    "previous_run": 4,
}


def candidate_rank(candidate: Candidate, row: Row) -> tuple[int, int, str]:
    """Deterministic order among the school's own pages for one programme."""
    return (
        0 if slug_agrees(candidate.url, row.title) else 1,
        SOURCE_RANK.get(candidate.matched_by, 9),
        candidate.url,
    )


# --------------------------------------------------------------------------- #
# already harvested school-owned programme pages
# --------------------------------------------------------------------------- #


def load_sources_config(path: Path | None = None) -> dict:
    source = path or SOURCES_CONFIG
    if not source.is_file():
        return {"harvestedSources": [], "schools": []}
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload.setdefault("harvestedSources", [])
    payload.setdefault("schools", [])
    return payload


def harvested_candidates(config: dict, now_text: str) -> dict[str, list[Candidate]]:
    """Candidates per registrable domain, from already harvested school sources."""
    by_domain: dict[str, list[Candidate]] = {}
    for entry in config.get("harvestedSources") or []:
        if not isinstance(entry, dict):
            continue
        relative = str(entry.get("path") or "")
        if not relative:
            continue
        path = Path(relative) if Path(relative).is_absolute() else ROOT / relative
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        title_field = str(entry.get("titleField") or "titles")
        for record in payload.get("programmes") or []:
            if not isinstance(record, dict):
                continue
            url = str(record.get(str(entry.get("urlField") or "officialProgrammeUrl")) or "").strip()
            if not is_https_url(url):
                continue
            raw_titles = record.get(title_field)
            titles = raw_titles if isinstance(raw_titles, dict) else {"original": raw_titles}
            degree = degree_code(record.get(str(entry.get("degreeField") or "degree")))
            language = str(record.get(str(entry.get("languageField") or "studyLanguage")) or "").strip().lower()
            domain = registrable_host(url)
            for key, value in titles.items():
                text = str(value or "").strip()
                if not text:
                    continue
                by_domain.setdefault(domain, []).append(
                    Candidate(
                        url=url,
                        title=text,
                        degree=degree,
                        language=language or str(key or "").strip().lower(),
                        source_url=url,
                        matched_by="school_harvested_programme_page",
                        observed_at=now_text,
                    )
                )
    return by_domain


# --------------------------------------------------------------------------- #
# live discovery
# --------------------------------------------------------------------------- #


@dataclass
class Limits:
    # One university home page links to a catalogue, the catalogue to a faculty,
    # and only the faculty page names the programmes, so the walk takes one hop
    # past the first catalogue. It stays bounded per school and per run.
    # Depth measured 2026-09-27 (work/programme-link-probe/): at 14 entries
    # Charles University resolves 1 of 912 rows, at 60 entries it resolves 56,
    # and CVUT goes from 0 to 48 of 283, so the walk is 60 catalogue pages.
    max_catalogue_entries: int = 60
    max_sitemap_children: int = 30
    max_locs: int = 20_000
    # Pages one school may cost. The same measurement put Charles University at
    # 121 requests and CVUT at 223 for the depths above, so a school is allowed
    # 260 before it stops reading and its remaining rows keep the university
    # site. This is per school, not per run: counted run-wide it starves every
    # school after the first few (the run-wide 240 budget left Charles
    # University, CVUT and Palacky at 0 with "budget_exhausted").
    max_page_fetches: int = 260
    max_candidates_per_page: int = 1_500
    # Pages read to learn which level a same-titled programme page belongs to.
    # Bounded per school and counted against the same page budget as discovery.
    max_level_probes: int = 60
    # Verification shares a school's page budget with discovery, so one school
    # cannot spend the whole run re-checking links it already checked.
    max_verifications: int = 400
    # Pages read to learn whether the school serves a plain-http page over
    # https as well. Only links that would otherwise be dropped for their
    # scheme are probed, one read each.
    max_scheme_promotions: int = 40


class Budget:
    def __init__(self, seconds: float):
        self.deadline = time.monotonic() + max(0.0, seconds)

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self.deadline


class ThrottledFetch:
    """Per-host spacing shared across every school in one run."""

    def __init__(self, fetch: FetchPage | None, sleep: Callable[[float], None] = time.sleep):
        self._fetch = fetch
        self._sleep = sleep
        self._last_call: dict[str, float] = {}
        self.requests = 0
        # Pages spent on the school currently being resolved. Both counters are
        # needed: this one bounds a single school (Limits.max_page_fetches), the
        # run-wide one is reported so the cost of a tick stays visible.
        self.school_requests = 0

    @property
    def live(self) -> bool:
        return self._fetch is not None

    def begin_school(self) -> None:
        """Open the page budget for the next school in this run."""
        self.school_requests = 0

    def __call__(self, url: str) -> tuple[int, str]:
        if self._fetch is None:
            return 0, ""
        host = host_of(url)
        previous = self._last_call.get(host)
        if previous is not None:
            delay = PER_HOST_SLEEP_SECONDS - (time.monotonic() - previous)
            if delay > 0:
                self._sleep(delay)
        self._last_call[host] = time.monotonic()
        self.requests += 1
        self.school_requests += 1
        return self._fetch(url)


def host_in_domains(url: str, allowed_domains: set[str]) -> bool:
    """Whether a URL sits on one of the school's own registrable domains.

    A university names its programmes on a subdomain just as often as on its
    apex host - is.muni.cz, ff.cuni.cz, study.czu.cz - so discovery reads any
    subdomain of a domain the school owns. This widens reading only: a page
    still has to equal a register title, degree and language exactly, and the
    publication gate rejects any link outside these same domains
    (docs/DATA_MODEL.md). No other organisation's site is ever read.
    """
    host = host_of(url)
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def catalogue_entries(body: str, base_url: str, allowed_domains: set[str]) -> list[str]:
    """Catalogue pages the school's own homepage links to, best first."""
    scored: dict[str, int] = {}
    for url, text in anchors(body, base_url):
        if not host_in_domains(url, allowed_domains):
            continue
        try:
            path = urllib.parse.urlsplit(url).path
        except ValueError:
            continue
        score = 0
        if CATALOGUE_TOKEN_RE.search(text):
            score += 3
        if PROGRAMME_PAGE_TOKEN_RE.search(path):
            score += 2
        if CATALOGUE_TOKEN_RE.search(path):
            score += 1
        if not score:
            continue
        candidate = url.split("#", 1)[0].rstrip("/")
        if candidate:
            scored[candidate] = max(scored.get(candidate, 0), score)
    return [url for url, _score in sorted(scored.items(), key=lambda item: (-item[1], item[0]))]


def discover_candidates(
    target: dict,
    fetch: ThrottledFetch,
    limits: Limits,
    budget: Budget,
) -> tuple[list[Candidate], list[str]]:
    """Collect programme-page candidates from the school's own site.

    One university home page rarely links straight to a programme: it links to
    a catalogue, the catalogue links to a faculty, and only the faculty page
    lists the programmes. So the catalogue walk is breadth-first with one extra
    hop - a page read as a catalogue may itself yield further catalogue pages -
    bounded by ``max_catalogue_entries`` per school and by this school's
    page-fetch and time budget. Every page is read at most once per school, so a
    page that turns out to be a programme page costs one bounded request. A school
    whose programmes are only reachable through a deeper tree stays unresolved
    rather than being guessed at.
    """
    notes: list[str] = []
    note_counts: dict[str, int] = {}

    def note(text: str) -> None:
        # A bounded walk can hit the same failure on many catalogue pages; one
        # note per reason, counted, keeps a school's coverage readable.
        note_counts[text] = note_counts.get(text, 0) + 1

    allowed_domains = set(target.get("allowedDomains") or set())
    homepage = str(target.get("officialUrl") or "")
    queue: list[str] = [str(url) for url in target.get("entryUrls") or []]
    if not queue and is_https_url(homepage):
        status, body = fetch(homepage)
        if status == 200 and body:
            queue.extend(catalogue_entries(body, homepage, allowed_domains))
        else:
            note(f"homepage_unreachable_http_{status}")

    observed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidates: list[Candidate] = []
    seen: set[str] = set()
    read: set[str] = set()
    queued: set[str] = set(queue)

    def keep(url: str, title: str, source_url: str, matched_by: str) -> None:
        if len(candidates) >= limits.max_candidates_per_page or url in seen:
            return
        if not host_in_domains(url, allowed_domains):
            return
        seen.add(url)
        candidates.append(
            Candidate(
                url=url,
                title=title,
                # The level written beside the programme name on this page, if
                # the page states one at all.
                degree=degree_stated(title, url),
                language="",
                source_url=source_url,
                matched_by=matched_by,
                observed_at=observed_at,
            )
        )

    while queue and len(read) < limits.max_catalogue_entries:
        entry = queue.pop(0)
        if entry in read:
            continue
        if budget.expired or fetch.school_requests >= limits.max_page_fetches:
            note("budget_exhausted")
            break
        read.add(entry)
        status, body = fetch(entry)
        if status != 200 or not body:
            note(f"catalogue_unreachable_http_{status}")
            continue
        for url, text in anchors(body, entry):
            if not text:
                continue
            keep(url, text, entry, "school_catalogue_anchor")
        for url in sitemap_urls(body):
            slug = slug_text(url)
            if slug:
                keep(url, slug, entry, "school_catalogue_sitemap")
        # One extra hop: a catalogue page often only lists faculties or
        # departments, whose own pages hold the programme names.
        if len(read) < limits.max_catalogue_entries:
            for url in catalogue_entries(body, entry, allowed_domains):
                if url in read or url in queued:
                    continue
                queued.add(url)
                queue.append(url)

    sitemap_candidates, sitemap_notes = discover_from_sitemaps(target, fetch, limits, budget, allowed_domains)
    for note_text in sitemap_notes:
        note(note_text)
    for candidate in sitemap_candidates:
        keep(candidate.url, candidate.title, candidate.source_url, candidate.matched_by)
    notes.extend(
        f"{text} (x{count})" if count > 1 else text for text, count in sorted(note_counts.items())
    )
    return candidates, notes


def discover_from_sitemaps(
    target: dict,
    fetch: ThrottledFetch,
    limits: Limits,
    budget: Budget,
    allowed_domains: set[str],
) -> tuple[list[Candidate], list[str]]:
    notes: list[str] = []
    bases = [str(target.get("officialUrl") or "")] + [str(url) for url in target.get("entryUrls") or []]
    roots: list[str] = []
    for base in bases:
        if not is_https_url(base):
            continue
        try:
            parsed = urllib.parse.urlsplit(base)
        except ValueError:
            continue
        for suffix in SITEMAP_PATHS:
            url = f"{parsed.scheme}://{parsed.netloc}{suffix}"
            if url not in roots:
                roots.append(url)

    locs: list[str] = []
    children_read = 0
    for root in roots:
        if budget.expired or fetch.school_requests >= limits.max_page_fetches:
            notes.append("budget_exhausted")
            break
        status, body = fetch(root)
        if status != 200 or "<" not in (body or ""):
            continue
        found = sitemap_urls(body)
        if not found:
            continue
        direct = [url for url in found if not url.casefold().endswith(".xml")]
        child_maps = [url for url in found if url.casefold().endswith(".xml")]
        locs.extend(direct)
        for child in child_maps:
            if children_read >= limits.max_sitemap_children or budget.expired:
                break
            if not CATALOGUE_TOKEN_RE.search(child):
                continue
            children_read += 1
            child_status, child_body = fetch(child)
            if child_status == 200:
                locs.extend(sitemap_urls(child_body))
        if direct:
            break

    if not locs:
        return [], notes

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for url in locs[: limits.max_locs]:
        if not host_in_domains(url, allowed_domains):
            continue
        try:
            path = urllib.parse.urlsplit(url).path
        except ValueError:
            continue
        if not PROGRAMME_PAGE_TOKEN_RE.search(path):
            continue
        slug = slug_text(url)
        if not slug or url in seen:
            continue
        seen.add(url)
        candidates.append(
            Candidate(
                url=url,
                title=slug,
                source_url=url,
                matched_by="school_sitemap_slug",
                observed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
    return candidates, notes


def checked_recently(link: Link, now: datetime, window_seconds: float) -> bool:
    """Was this link confirmed inside the refresh window already?

    Keeps a bounded CI run incremental: it re-checks new links first and only
    re-walks stale ones, so coverage grows without any run having to fetch the
    whole index.
    """
    if not link.checked_at or window_seconds <= 0:
        return False
    try:
        checked_at = datetime.strptime(link.checked_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (now - checked_at).total_seconds() < window_seconds


def assess_page(link: Link, body: str) -> str:
    """What one 200 answer says about a link: its reachability, or a drop reason.

    A page that names the register row exactly is verified; one that names
    nothing of it is kept but not confirmed. A page that states a different
    study level than this register row is the other programme's page, however
    exactly the name matched, so the link is dropped and the row keeps the
    university site. A page that states no level, or two, is checked no further.
    """
    expected = normalise(link.row_title)
    headings = page_headings(body)
    matched_heading = next((item for item in headings if normalise(item) == expected), None)
    link.page_title = matched_heading or (headings[0] if headings else None)
    stated_level = degree_stated(link.page_title or "")
    if stated_level != UNKNOWN_DEGREE and link.degree and stated_level != link.degree:
        return "dropped_level_mismatch"
    return "verified" if matched_heading else "http_200_title_not_confirmed"


def verify_links(
    links: dict[str, Link],
    fetch: ThrottledFetch,
    limits: Limits,
    budget: Budget,
    now: datetime | None = None,
    recheck_after_seconds: float = RECHECK_AFTER_SECONDS,
) -> dict[str, str]:
    """Confirm each link still resolves on the school's own site.

    A 404 drops the link (and the row returns to unresolved), and so does a page
    that states a different study level than its row. Access control, rate
    limiting, transport failure and budget exhaustion keep the link and mark it
    unverified: none of them is evidence that the page is gone.
    """
    outcomes: dict[str, str] = {}
    checked = 0
    current = now or datetime.now(timezone.utc)
    for ident, link in sorted(links.items(), key=lambda item: (item[1].checked_at or "", item[1].url)):
        if checked >= limits.max_verifications or budget.expired:
            outcomes[link.url] = "skipped_budget"
            continue
        if checked_recently(link, current, recheck_after_seconds):
            outcomes[link.url] = link.reachability or "unverified"
            continue
        checked += 1
        status, body = fetch(link.url)
        now_text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        link.checked_at = now_text
        if status == 404:
            outcomes[link.url] = "dropped_404"
            continue
        if status in {401, 403, 407, 451}:
            link.reachability = "access_control"
            outcomes[link.url] = "unverified_access_control"
            continue
        if status != 200:
            link.reachability = "unverified"
            outcomes[link.url] = f"unverified_http_{status or 0}"
            continue
        outcome = assess_page(link, body)
        if outcome not in DROP_REASONS:
            link.reachability = outcome
        outcomes[link.url] = outcome
    return outcomes


def promote_https(
    links: dict[str, Link],
    fetch: ThrottledFetch,
    limits: Limits,
    budget: Budget,
    now: datetime | None = None,
) -> list[str]:
    """Publish a plain-http page over https where the school serves both.

    The published inventory only accepts https addresses, so without this a
    school page reached over http would be dropped even though it is the
    school's own page for exactly that register row. The twin is read once, on
    the same host and path, and only a 200 answer that still names this row's
    programme replaces the address; anything else leaves the link alone and the
    row keeps the university-site fallback.
    """
    notes: list[str] = []
    if not fetch:
        return notes
    current = now or datetime.now(timezone.utc)
    promoted = 0
    for ident in sorted(links):
        if promoted >= limits.max_scheme_promotions or budget.expired:
            break
        link = links[ident]
        twin = https_twin(link.url)
        if not twin:
            continue
        status, body = fetch(twin)
        if status != 200:
            continue
        promoted_link = Link(
            url=twin,
            row_id=link.row_id,
            institution_id=link.institution_id,
            degree=link.degree,
            language=link.language,
            matched_title=link.matched_title,
            row_title=link.row_title,
            source_url=link.source_url,
            matched_by=link.matched_by,
            reachability=link.reachability,
            matched_at=link.matched_at,
        )
        outcome = assess_page(promoted_link, body)
        if outcome in DROP_REASONS:
            continue
        promoted_link.reachability = outcome
        promoted_link.checked_at = current.strftime("%Y-%m-%dT%H:%M:%SZ")
        links[ident] = promoted_link
        promoted += 1
    if promoted:
        notes.append(f"promoted_to_https: {promoted}")
    return notes


def promote_previous_https(
    previous: dict,
    fetch: ThrottledFetch,
    limits: Limits,
    budget: Budget,
    now: datetime | None = None,
) -> dict:
    """The same promotion for the links an earlier run folded forward.

    ``merge_previous`` keeps only https links, so a plain-http page a school
    still serves over https used to disappear from the index the moment a later
    run did not walk that school again. Promoting before the fold keeps it.
    """
    if not previous or not fetch:
        return previous
    promoted = {
        ident: Link(
            url=str(entry.get("url") or ""),
            row_id=ident,
            institution_id=str(entry.get("institutionId") or ""),
            degree=str(entry.get("degree") or "u"),
            language=str(entry.get("language") or ""),
            matched_title=str(entry.get("matchedTitle") or ""),
            row_title=str(entry.get("rowTitle") or ""),
            source_url=str(entry.get("sourceUrl") or ""),
            matched_by=str(entry.get("matchedBy") or "previous_run"),
            reachability=str(entry.get("reachability") or "unverified"),
            matched_at=str(entry.get("matchedAt") or ""),
        )
        for ident, entry in sorted(previous_links(previous).items())
        if https_twin(str(entry.get("url") or ""))
    }
    if not promoted:
        return previous
    notes = promote_https(promoted, fetch, limits, budget, now=now)
    if not notes:
        return previous
    payload = json.loads(json.dumps(previous))
    for ident, link in promoted.items():
        entry = payload.get("links", {}).get(ident)
        if not isinstance(entry, dict) or not link.url.startswith("https://"):
            continue
        entry["url"] = link.url
        entry["reachability"] = link.reachability
        if link.page_title:
            entry["pageTitle"] = link.page_title
        entry["checkedAt"] = link.checked_at
    return payload


# --------------------------------------------------------------------------- #
# resolution
# --------------------------------------------------------------------------- #


def probe_levels(
    match: Match,
    unresolved: dict[str, str],
    candidates_by_title: dict[str, list[Candidate]],
    fetch: ThrottledFetch,
    limits: Limits,
    budget: Budget,
) -> tuple[dict[str, list[tuple[Candidate, str]]], list[str]]:
    """Separate a title the register carries at two levels, using the page.

    A catalogue link usually states only the name ("Optika a optometrie"), while
    the register carries it once as a bachelor and once as a master programme.
    The school's own page states which ("– bakalářské studium"), so the page is
    read once and its level decides. Every read is bounded by
    ``max_level_probes`` per school and shares this school's page-fetch and
    time budgets; a title that stays undecided keeps the university-site fallback.
    """
    notes: list[str] = []
    probed: dict[str, list[tuple[Candidate, str]]] = {}
    rows_by_title: dict[str, list[Row]] = {}
    for row in match.rows:
        rows_by_title.setdefault(normalise(row.title), []).append(row)

    outstanding = sorted(
        title_key
        for title_key, rows in rows_by_title.items()
        if len({item.degree for item in rows}) > 1
        and any(unresolved.get(row.ident) == "ambiguous_register_rows" for row in rows)
        and candidates_by_title.get(title_key)
    )
    reads = 0
    for title_key in outstanding:
        if reads >= limits.max_level_probes or budget.expired:
            notes.append("level_probe_budget_exhausted")
            break
        if fetch.school_requests >= limits.max_page_fetches:
            notes.append("budget_exhausted")
            break
        rows_by_degree = {row.degree: row for row in rows_by_title[title_key]}
        for candidate in candidates_by_title[title_key]:
            if reads >= limits.max_level_probes or budget.expired:
                break
            reads += 1
            status, body = fetch(candidate.url)
            if status != 200 or not body:
                continue
            level = degree_stated(page_title_text(body))
            row = rows_by_degree.get(level)
            if row is None:
                continue
            probed.setdefault(row.ident, []).append((candidate, row.language))
            unresolved.pop(row.ident, None)
    return probed, notes


def resolve_school(
    target: dict,
    match: Match,
    harvested: list[Candidate],
    fetch: ThrottledFetch,
    limits: Limits,
    budget: Budget,
    live: bool,
) -> tuple[dict[str, Link], dict[str, str], int, list[str]]:
    """Resolve as many of one school's rows as can be proven.

    Several school-owned pages can carry the same programme name (CZU publishes
    one catalogue on study.czu.cz and another on studuj.czu.cz). Those are not
    contradictory, so every binding is collected and ranked, and the row keeps
    the best page rather than losing it. Only a genuinely ambiguous register
    row — two programmes sharing a normalised title and degree — stays
    unresolved, until the level probe below reads the school's own page and the
    level stated there separates them.
    """
    grouped: dict[str, list[tuple[Candidate, str]]] = {}
    unresolved = {row.ident: "no_candidate_page" for row in match.rows}
    notes: list[str] = []
    # Candidates whose title the register carries, kept so a title the register
    # holds at two levels can be separated by the level the page states.
    candidates_by_title: dict[str, list[Candidate]] = {}

    def collect(candidate: Candidate) -> None:
        binding = match.bind(candidate)
        if not binding.rows:
            return
        if binding.reason:
            for row in binding.rows:
                unresolved[row.ident] = binding.reason
            candidates_by_title.setdefault(normalise(candidate.title), []).append(candidate)
            return
        grouped.setdefault(binding.rows[0].ident, []).append((candidate, binding.language))

    for candidate in harvested:
        collect(candidate)

    if live:
        candidates, discovery_notes = discover_candidates(target, fetch, limits, budget)
        notes.extend(discovery_notes)
        for candidate in candidates:
            if budget.expired:
                notes.append("budget_exhausted")
                break
            collect(candidate)

    if live:
        probed, probe_notes = probe_levels(
            match, unresolved, candidates_by_title, fetch, limits, budget
        )
        notes.extend(probe_notes)
        for ident, bindings in probed.items():
            grouped.setdefault(ident, []).extend(bindings)

    if not grouped:
        return {}, unresolved, 0, notes

    links: dict[str, Link] = {}
    rows_by_ident = {row.ident: row for row in match.rows}
    multiple_pages = 0
    for ident, bindings in grouped.items():
        row = rows_by_ident[ident]
        candidate, language = min(
            bindings,
            key=lambda item: candidate_rank(item[0], row),
        )
        if len({item[0].url for item in bindings}) > 1:
            multiple_pages += 1
        links[ident] = Link(
            url=candidate.url,
            row_id=ident,
            institution_id=row.institution_id,
            degree=row.degree,
            language=language,
            matched_title=candidate.title,
            row_title=row.title,
            source_url=candidate.source_url or candidate.url,
            matched_by=candidate.matched_by,
            reachability="unverified",
            matched_at=candidate.observed_at,
        )
        unresolved.pop(ident, None)
    return links, unresolved, multiple_pages, notes


def school_target(institution: dict, override: dict) -> dict:
    """A school target with every domain its programme pages may live on."""
    official_url = str(institution.get("officialUrl") or "")
    domains = school_domains(institution, override)
    return {
        "id": str(institution["id"]),
        "name": str(institution.get("officialName") or institution["id"]),
        "officialUrl": official_url,
        "entryUrls": [str(url) for url in (override.get("entryUrls") or []) if is_https_url(url)],
        # Every subdomain of these registrable domains may be read while
        # discovering; matching and the publication gate stay exact.
        "allowedDomains": sorted(domains),
    }


def allowed_domains_by_institution(config: dict | None = None) -> dict[str, set[str]]:
    """Registrable domains each school's programme pages may live on.

    Doubles as the anti-fabrication gate for publication: a programme page must
    sit on a domain the school itself owns (cuni.cz, study.czu.cz, ...), never on
    a portal or an unrelated organisation.
    """
    return domains_for_institutions(baseline_schools(), config)


def domains_for_institutions(institutions: Iterable[dict], config: dict | None = None) -> dict[str, set[str]]:
    """Allowed registrable domains per institution id from given baseline records."""
    config = config if config is not None else load_sources_config()
    overrides = {
        str(entry["institutionId"]): entry
        for entry in config.get("schools") or []
        if isinstance(entry, dict) and entry.get("institutionId")
    }
    return {
        str(institution["id"]): school_domains(institution, overrides.get(str(institution["id"]), {}))
        for institution in institutions
        if isinstance(institution, dict) and institution.get("id")
    }


def school_domains(institution: dict, override: dict) -> set[str]:
    """The official host plus every extra domain configured for this school."""
    domains = {
        registrable_host(institution.get("webHost") or ""),
        registrable_host(institution.get("officialUrl") or ""),
    }
    domains.discard("")
    for extra in override.get("extraDomains") or []:
        domain = registrable_host(str(extra))
        if domain:
            domains.add(domain)
    return domains


def baseline_schools() -> list[dict]:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    return [item for item in payload.get("institutions") or [] if isinstance(item, dict) and item.get("id")]


def previous_links(payload: dict) -> dict[str, dict]:
    return {key: value for key, value in (payload.get("links") or {}).items() if isinstance(value, dict)}


def previous_candidates(previous: dict, target: dict, match: Match) -> list[Candidate]:
    """Last run's proven pages, offered to this run's ranking.

    A bounded run re-reads the same harvested catalogue every time, so without
    this the page chosen last week could silently differ from the page chosen
    today. Offering the previous page as a candidate keeps the choice stable
    and keeps coverage from regressing when discovery is cut short.
    """
    rows_by_ident = {row.ident: row for row in match.rows}
    candidates: list[Candidate] = []
    for ident, entry in previous_links(previous).items():
        row = rows_by_ident.get(ident)
        if row is None:
            continue
        url = str(entry.get("url") or "")
        if not is_https_url(url) or registrable_host(url) not in target["allowedDomains"]:
            continue
        candidates.append(
            Candidate(
                url=url,
                title=row.title,
                degree=row.degree,
                language=str(entry.get("language") or row.language),
                source_url=str(entry.get("sourceUrl") or url),
                matched_by="previous_run",
                observed_at=str(entry.get("matchedAt") or ""),
            )
        )
    return candidates


def merge_previous(
    previous: dict,
    links: dict[str, Link],
    unresolved: dict[str, str],
    coverage_schools: list[dict],
) -> tuple[dict[str, Link], dict[str, str], list[dict]]:
    """Fold schools this run did not touch back into the report.

    A one-school run, or one the budget cut short, still has to describe the
    whole index: every other school keeps its last result instead of appearing
    to have none, and says it was carried over. A row the budget never reached
    keeps its previous link and its previous reason, never "not_attempted": a
    rotation that walked two schools must not describe the other fifty-one as
    unresolved.
    """
    kept_links = dict(links)
    reasons = dict(unresolved)
    for ident, entry in previous_links(previous).items():
        if ident in kept_links:
            continue
        if reasons.get(ident) == NOT_ATTEMPTED:
            # The run never read this row's school, so this run has nothing to
            # say about it; the last run that did read it says it below.
            reasons.pop(ident, None)
        elif ident in reasons:
            continue
        url = str(entry.get("url") or "")
        if not is_https_url(url):
            continue
        kept_links[ident] = Link(
            url=url,
            row_id=ident,
            institution_id=str(entry.get("institutionId") or ""),
            degree=str(entry.get("degree") or "u"),
            language=str(entry.get("language") or ""),
            matched_title=str(entry.get("matchedTitle") or ""),
            row_title=str(entry.get("rowTitle") or ""),
            source_url=str(entry.get("sourceUrl") or url),
            matched_by=str(entry.get("matchedBy") or "previous_run"),
            reachability=str(entry.get("reachability") or "unverified"),
            matched_at=str(entry.get("matchedAt") or ""),
            checked_at=str(entry.get("checkedAt") or ""),
            page_title=entry.get("pageTitle") if isinstance(entry.get("pageTitle"), str) else None,
        )
    for item in previous.get("unresolved") or []:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("rowId") or "")
        reason = str(item.get("reason") or "carried_from_previous_run")
        # A row the run never read gets the reason the last run that did read it
        # proved; a row this run read keeps this run's answer.
        if ident and ident not in kept_links and reasons.get(ident, NOT_ATTEMPTED) == NOT_ATTEMPTED:
            reasons[ident] = reason
    previous_schools = {
        str(item.get("institutionId")): item
        for item in (previous.get("coverage") or {}).get("schools") or []
        if isinstance(item, dict) and item.get("institutionId")
    }
    folded_schools: list[dict] = []
    for entry in coverage_schools:
        institution_id = str(entry.get("institutionId") or "")
        last_read = previous_schools.get(institution_id)
        if last_read is None or NOT_ATTEMPTED not in (entry.get("unresolvedReasons") or {}):
            folded_schools.append(entry)
            continue
        # The run's budget ran out before it read this school, so this run's own
        # entry for it is empty. The school keeps the numbers of the run that
        # last read it - and that run's resolvedAt, so the next rotation knows
        # when it was last walked - and says it was not read this time.
        folded = dict(last_read)
        notes = [str(note) for note in folded.get("notes") or [] if note != "carried_from_previous_run"]
        if "not_attempted_this_run" not in notes:
            notes.append("not_attempted_this_run")
        folded["notes"] = notes
        folded_schools.append(folded)
    kept_schools: list[dict] = []
    for item in (previous.get("coverage") or {}).get("schools") or []:
        if not isinstance(item, dict) or item.get("institutionId") in {
            str(entry.get("institutionId")) for entry in folded_schools
        }:
            continue
        entry = dict(item)
        notes = [str(note) for note in entry.get("notes") or []]
        if "carried_from_previous_run" not in notes:
            notes.append("carried_from_previous_run")
        entry["notes"] = notes
        kept_schools.append(entry)
    return kept_links, reasons, folded_schools + kept_schools


def carry_verification(previous: dict, links: dict[str, Link]) -> None:
    """Reuse the last live check for pages that did not change.

    Keeps the refresh window meaningful: only pages that are new, changed, or
    older than the window are fetched again.
    """
    for ident, link in links.items():
        entry = previous_links(previous).get(ident) or {}
        if not entry or str(entry.get("url") or "") != link.url:
            continue
        if entry.get("reachability"):
            link.reachability = str(entry["reachability"])
        if entry.get("checkedAt"):
            link.checked_at = str(entry["checkedAt"])
        if entry.get("matchedAt"):
            link.matched_at = str(entry["matchedAt"])
        if isinstance(entry.get("pageTitle"), str) and entry["pageTitle"]:
            link.page_title = str(entry["pageTitle"])
        if entry.get("matchedBy"):
            link.matched_by = str(entry["matchedBy"])


def rotation_order(institutions: Iterable[dict], previous: dict) -> list[dict]:
    """Order the schools so a bounded walk eventually covers every one.

    One run cannot read all 53 schools: at the configured depth the measured
    cost is about 330 wall-clock seconds per school, so a 600-second run reads
    two. Without a rotation the walk always starts at the same schools and the
    rest are never read at all, which is how Charles University, CVUT and
    Palacky stayed at zero resolved programme pages.

    So the least-recently-read school goes first - a school never read goes
    first of all - and the run's own time budget decides where it stops. What
    it does not reach keeps the previous run's links (merge_previous), so the
    index only grows and every school is walked once per cycle of runs.
    """
    last_read: dict[str, str] = {}
    for entry in (previous.get("coverage") or {}).get("schools") or []:
        if not isinstance(entry, dict):
            continue
        institution_id = str(entry.get("institutionId") or "")
        if institution_id:
            last_read[institution_id] = str(entry.get("resolvedAt") or "")
    return sorted(
        institutions,
        key=lambda institution: (
            0 if str(institution.get("id")) not in last_read else 1,
            last_read.get(str(institution.get("id")), ""),
            str(institution.get("id")),
        ),
    )


def build_links(
    *,
    fetch: FetchPage | None = None,
    now: datetime | None = None,
    budget_seconds: float = 0.0,
    limits: Limits | None = None,
    config: dict | None = None,
    previous: dict | None = None,
    school_ids: Iterable[str] | None = None,
    rows_by_institution: dict[str, list[Row]] | None = None,
    institutions: list[dict] | None = None,
) -> dict:
    """Resolve links for every school, then report coverage honestly."""
    limits = limits or Limits()
    current = now or datetime.now(timezone.utc)
    now_text = current.strftime("%Y-%m-%dT%H:%M:%SZ")
    config = config if config is not None else load_sources_config()
    rows_by_institution = rows_by_institution if rows_by_institution is not None else register_rows()
    institution_of = {
        row.ident: institution_id
        for institution_id, rows in rows_by_institution.items()
        for row in rows
    }
    all_institutions = institutions if institutions is not None else baseline_schools()
    throttled = ThrottledFetch(fetch)
    budget = Budget(budget_seconds) if fetch else Budget(0.0)
    live = fetch is not None
    overrides = {
        str(entry["institutionId"]): entry
        for entry in config.get("schools") or []
        if isinstance(entry, dict) and entry.get("institutionId")
    }
    harvested = harvested_candidates(config, now_text)
    previous_payload = previous or {}
    selected = set(school_ids) if school_ids is not None else None
    previous_reads = {
        str(entry.get("institutionId")): str(entry.get("resolvedAt") or "")
        for entry in (previous_payload.get("coverage") or {}).get("schools") or []
        if isinstance(entry, dict) and entry.get("institutionId")
    }

    links: dict[str, Link] = {}
    unresolved_by_row: dict[str, str] = {}
    coverage_schools: list[dict] = []
    processed: set[str] = set()

    for institution in all_institutions:
        institution_id = str(institution["id"])
        if selected is not None and institution_id not in selected:
            continue
        rows = rows_by_institution.get(institution_id) or []
        if not rows:
            continue
        processed.add(institution_id)
        if live and budget.expired:
            last_read = previous_reads.get(institution_id, "")
            coverage_schools.append(
                {
                    "institutionId": institution_id,
                    "name": str(institution.get("officialName") or institution_id),
                    "offerings": len(rows),
                    "resolved": 0,
                    "unresolved": len(rows),
                    "unresolvedReasons": {NOT_ATTEMPTED: len(rows)},
                    # When the school was last read, if it ever was: a run that
                    # never reached it says nothing else about its pages.
                    **({"resolvedAt": last_read} if last_read else {}),
                    "notes": ["budget_exhausted_before_school"],
                }
            )
            unresolved_by_row.update({row.ident: NOT_ATTEMPTED for row in rows})
            continue
        # The page-fetch budget is per school, so every school in the run starts
        # with its own (Limits.max_page_fetches).
        throttled.begin_school()
        target = school_target(institution, overrides.get(institution_id, {}))
        match = Match(rows)
        harvested_for_school = [
            candidate
            for domain in target["allowedDomains"]
            for candidate in harvested.get(domain, [])
        ]
        if previous_payload:
            harvested_for_school.extend(previous_candidates(previous_payload, target, match))
        school_links, school_unresolved, multiple_pages, notes = resolve_school(
            target, match, harvested_for_school, throttled, limits, budget, live
        )
        if live:
            # Before the last live check is carried forward: a promoted address
            # is a new one, so the previous check does not describe it.
            notes.extend(promote_https(school_links, throttled, limits, budget, now=current))
        carry_verification(previous_payload, school_links)
        if live and school_links:
            for url, outcome in verify_links(
                school_links, throttled, limits, budget, now=current
            ).items():
                if outcome not in DROP_REASONS:
                    continue
                for ident in [key for key, value in school_links.items() if value.url == url]:
                    school_links.pop(ident)
                    school_unresolved[ident] = DROP_REASONS[outcome]
        links.update(school_links)
        unresolved_by_row.update(school_unresolved)
        coverage_schools.append(
            {
                "institutionId": institution_id,
                "name": target["name"],
                "allowedDomains": target["allowedDomains"],
                "offerings": len(rows),
                "resolved": len(school_links),
                "unresolved": len(school_unresolved),
                "rowsWithMultipleSchoolPages": multiple_pages,
                "unresolvedReasons": summarize(school_unresolved.values()),
                # When this school was read, so the next run walks the schools
                # that have gone longest without being read first.
                "resolvedAt": now_text,
                "notes": notes,
            }
        )

    # A run that walked only some schools (--school, or cut short by the budget)
    # must not present itself as the whole index: the untouched schools keep
    # their last reported entries and say so in the total.
    if selected is not None or (live and budget.expired):
        if live:
            previous_payload = promote_previous_https(
                previous_payload, throttled, limits, budget, now=current
            )
        links, unresolved, coverage_schools = merge_previous(
            previous_payload, links, unresolved_by_row, coverage_schools
        )
    else:
        unresolved = unresolved_by_row
    # Entries folded in from an earlier run carry that run's numbers; an entry
    # missing a field counts as zero rather than failing the whole run.
    totals = {
        "schools": len(coverage_schools),
        "offerings": sum(int(item.get("offerings") or 0) for item in coverage_schools),
        "resolved": len(links),
        "unresolved": len(unresolved),
        "rowsWithMultipleSchoolPages": sum(
            int(item.get("rowsWithMultipleSchoolPages") or 0) for item in coverage_schools
        ),
        "byReachability": summarize(link.reachability for link in links.values()),
    }
    return {
        "generatedAt": now_text,
        "dataClass": "school_owned_programme_page_index",
        "note": NOTE,
        "counts": {
            "schools": totals["schools"],
            "offerings": totals["offerings"],
            "linked": totals["resolved"],
            "unresolved": totals["unresolved"],
            "rowsWithMultipleSchoolPages": totals["rowsWithMultipleSchoolPages"],
        },
        "coverage": {
            "totals": totals,
            "schools": coverage_schools,
        },
        "links": {
            ident: {
                "url": link.url,
                "kind": LINK_KIND,
                "institutionId": link.institution_id,
                "degree": link.degree,
                "language": link.language,
                "matchedTitle": link.matched_title,
                "rowTitle": link.row_title,
                "sourceUrl": link.source_url,
                "matchedBy": link.matched_by,
                "pageTitle": link.page_title,
                "reachability": link.reachability,
                "matchedAt": link.matched_at,
                "checkedAt": link.checked_at,
            }
            for ident, link in sorted(links.items())
        },
        "unresolved": [
            {
                "institutionId": institution_of.get(ident, ""),
                "rowId": ident,
                "reason": reason,
            }
            for ident, reason in sorted(unresolved.items())
        ],
        "requests": throttled.requests,
    }


def summarize(values: Iterable[str]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for value in values:
        summary[value] = summary.get(value, 0) + 1
    return dict(sorted(summary.items()))


def load_previous(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_payload(payload: dict, path: Path | None = None) -> Path:
    target = path or DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve school-owned programme page links")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--budget-seconds", type=float, default=0.0)
    parser.add_argument("--live", action="store_true", help="fetch school sites (default: harvested sources only)")
    parser.add_argument("--school", action="append", default=None, help="institution id; repeatable")
    parser.add_argument("--no-merge", action="store_true", help="ignore the previous index when writing a fresh one")
    args = parser.parse_args()

    fetch = None
    if args.live:
        from engine.transport import fetch_official_page

        def fetch(url: str) -> tuple[int, str]:
            # Offline ingestion transport: ordinary HTTP, then Scrapling GET if
            # the ordinary read is too weak. No visitor request ever reaches a
            # school through this path.
            result = fetch_official_page(url, allow_browser=False)
            return result.status, result.body

    payload = build_links(
        fetch=fetch,
        budget_seconds=args.budget_seconds,
        previous={} if args.no_merge else load_previous(args.output),
        school_ids=args.school,
    )
    write_payload(payload, args.output)
    output = str(args.output)
    if args.output.is_relative_to(ROOT):
        output = str(args.output.relative_to(ROOT)).replace("\\", "/")
    print(
        json.dumps(
            {
                "output": output,
                "live": bool(args.live),
                "requests": payload["requests"],
                "counts": payload["counts"],
                "byReachability": payload["coverage"]["totals"]["byReachability"],
                "unresolvedReasons": summarize(item["reason"] for item in payload["unresolved"]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

"""Harvest research and technical vacancies from registered official sources.

EURAXESS is discovery only. Apply URLs must be official school hosts. Missing
opensAt is not treated as open. Closed or past-deadline posts are not stored as
open. Does not invent salary amounts or write data/published/.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import ssl
import subprocess
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[3]
from publication_rules import (  # noqa: E402
    FACT_NORMALIZATION_VERSION,
    job_fact_hash,
    reviewer_role,
    translation_content_hash,
)
from source_types import JOB_LISTING_SOURCE_TYPES  # noqa: E402

RAW = ROOT / "work" / "raw" / "2026-09-06" / "jobs"
OUT = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
REVIEWS = ROOT / "data" / "sources" / "reviews" / "job-translations.json"
SOURCE_REGISTRY = ROOT / "data" / "sources" / "registry.json"
UA = (
    "Mozilla/5.0 (compatible; CzechUniApplyHarvest/0.1; "
    "+https://czech-uni-application.com/contact)"
)
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
SLEEP = 3
TODAY = date.today()
CTX = ssl.create_default_context()
LMC_GRAPHQL_ENDPOINT = "https://api.capybara.lmc.cz/api/graphql/widget"
WINDOWS_OCR = Path(__file__).with_name("windows_ocr.ps1")
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 12
TRANSIENT_HTTP_STATUSES = {0, 408, 425, 429, 500, 502, 503, 504}
REQUEST_RETRY_DELAYS = (3.0, 12.0)
MAX_IN_PROCESS_RETRY_SECONDS = 30.0
# A69: bumped whenever extraction logic changes. Stored records remember which
# parser version produced their facts so offline replay can target stale ones.
PARSER_VERSION = "jobs-parser-2026-09-12.2"


@dataclass
class TransportResult:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)
    retry_at: datetime | None = None
    deferred: bool = False

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


_host_cooldowns: dict[str, datetime] = {}


def _aware_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def parse_retry_after(value: str | None, now: datetime) -> datetime | None:
    """Parse RFC 9110 Retry-After as delay-seconds or HTTP-date."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    current = _aware_now(now)
    if text.isdigit():
        return current + timedelta(seconds=int(text))
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    if parsed <= current:
        return None
    return parsed


def host_key(url: str) -> str:
    return (urlsplit(url).hostname or "").casefold()


def host_cooldown_until(url: str, now: datetime | None = None) -> datetime | None:
    until = _host_cooldowns.get(host_key(url))
    if until is None:
        return None
    if until <= _aware_now(now):
        _host_cooldowns.pop(host_key(url), None)
        return None
    return until


def set_host_cooldown(url: str, until: datetime) -> None:
    host = host_key(url)
    if not host:
        return
    current = _host_cooldowns.get(host)
    if current is None or until > current:
        _host_cooldowns[host] = until


def clear_host_cooldowns() -> None:
    _host_cooldowns.clear()


def load_host_cooldowns(mapping: dict[str, str], now: datetime | None = None) -> None:
    current = _aware_now(now)
    for host, stamp in mapping.items():
        try:
            until = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            continue
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        until = until.astimezone(timezone.utc)
        if until > current:
            _host_cooldowns[str(host).casefold()] = until


def export_host_cooldowns() -> dict[str, str]:
    return {
        host: until.strftime("%Y-%m-%dT%H:%M:%SZ")
        for host, until in sorted(_host_cooldowns.items())
    }


def _header_map(headers) -> dict[str, str]:
    if headers is None:
        return {}
    try:
        items = headers.items()
    except AttributeError:
        return {}
    return {str(key).lower(): str(value) for key, value in items}
LMC_LIST_QUERY = """
query LmcJobList(
  $widgetId: ID!, $page: Int, $filters: [JobAdFilter!]!,
  $useExampleData: Boolean!, $host: String
) {
  widget(id: $widgetId, useExampleData: $useExampleData, host: $host) {
    jobAdList(page: $page, filters: $filters) {
      groupedJobAds {
        ...LmcJobGroup
        groups {
          ...LmcJobGroup
          groups {
            ...LmcJobGroup
            groups { ...LmcJobGroup }
          }
        }
      }
      paginator { currentPage lastPage totalNumberOfItems }
    }
  }
}
fragment LmcJobGroup on JobAdGroup {
  groupId
  groupName
  jobAds { id title validFrom teaser languageIso employer { companyName } }
}
""".strip()
LMC_DETAIL_QUERY = """
query LmcJobDetail($widgetId: ID!, $jobAdId: ID!, $host: String) {
  widget(id: $widgetId, host: $host) {
    jobAd(id: $jobAdId) {
      id
      title
      validFrom
      teaser
      languageIso
      content { htmlContent sections { title text } }
      locations { city }
      salary { min max period currency }
      parameters {
        employmentTypes
        employmentDurations
        contractTypes
        hoursPerWeek
        start
        end
        requiredEducation
        requiredLanguages { language skill }
        allLanguagesRequired
        benefits
      }
      employer { companyName contactCompanyName }
    }
  }
}
""".strip()
DEAD = (
    "we couldn’t find this page",
    "we couldn't find this page",
    "page not found",
    "stránka nenalezena",
    "stranka nenalezena",
    "404 not found",
    "this page doesn't exist",
    "this page does not exist",
)
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")
ISO_DATE = re.compile(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b")
TEXT_DATE = re.compile(
    r"\b(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2})\b",
    re.I,
)
MONTH_FIRST_DATE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b",
    re.I,
)
CZ_DATE = re.compile(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b")
CZ_TEXT_DATE = re.compile(
    r"\b(\d{1,2})\.?\s+"
    r"(ledna|února|unora|března|brezna|dubna|května|kvetna|června|cervna|"
    r"července|cervence|srpna|září|zari|října|rijna|listopadu|prosince)"
    r"\s+(20\d{2})\b",
    re.I,
)
MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
CZ_MONTHS = {
    "ledna": 1,
    "února": 2,
    "unora": 2,
    "března": 3,
    "brezna": 3,
    "dubna": 4,
    "května": 5,
    "kvetna": 5,
    "června": 6,
    "cervna": 6,
    "července": 7,
    "cervence": 7,
    "srpna": 8,
    "září": 9,
    "zari": 9,
    "října": 10,
    "rijna": 10,
    "listopadu": 11,
    "prosince": 12,
}

POSTDOC_MARKERS = (
    "postdoc",
    "post-doc",
    "post-doctoral",
    "postdoctoral",
    "postdoktor",
    "post-doktor",
    "postdoktorsk",
)
ASSISTANT_MARKERS = (
    "research assistant",
    "assistant researcher",
    "výzkumný asistent",
    "vyzkumny asistent",
    "asistent výzkumu",
    "asistent vyzkumu",
    "vědecký asistent",
    "vedecky asistent",
    "student researcher",
    "phd student",
    "ph.d. student",
    "phd position",
    "ph.d. position",
    "phd fellowship",
    "ph.d. fellowship",
    "doctoral candidate",
    "phd candidate",
    "ph.d. candidate",
    "doctoral student",
    "doktorand",
)
SKIP_MARKERS = (
    "dean",
    "rector",
    "secretary",
    "librarian",
    "accountant",
    "hr manager",
    "event manager",
    "personalista",
    "personalistka",
    "knihovník",
    "knihovnice",
    "tajemník",
    "tajemnice",
    "děkan",
    "dekan",
    "rektor",
    "accounting",
    "účetní",
    "ucetni",
    "financial manager",
    "finanční manažer",
    "financni manazer",
    "grant support",
    "grantové podpory",
    "grantove podpory",
    "referent",
    "security guard",
    "ostraha",
    "personnel director",
    "personální ředitel",
    "personalni reditel",
    "human resources director",
    "administrator",
    "administrátor",
    "administrator/ka",
    "administrative",
    "administrativní",
    "administrativni",
    "coordinator",
    "koordinátor",
    "koordinator",
    "public procurement",
    "veřejných zakázek",
    "verejnych zakazek",
    "student affairs",
    "studentských záležitostí",
    "studentskych zalezitosti",
    "legal department",
    "právního oddělení",
    "pravniho oddeleni",
    "webmaster",
    "správce web",
    "spravce web",
    "research support",
    "podpora výzkumu",
    "podpory výzkumu",
    "podpora vyzkumu",
    "podpory vyzkumu",
    "science communication",
    "popularizace vědy",
    "popularizaci vědy",
    "popularizace vedy",
    "popularizaci vedy",
    "housekeeper",
    "domovník",
    "domovnik",
)
TEACHING_ONLY = (
    "assistant professor",
    "associate professor",
    "odborný asistent",
    "odborny asistent",
    "lecturer",
    "lektor",
    "lektorka",
)

LISTING_PAGES: list[tuple[str, str]] = [
    ("msmt-vs_11000", "https://www.mff.cuni.cz/en/faculty/job-opportunities"),
    ("msmt-vs_11000", "https://www.d3s.mff.cuni.cz/positions/"),
    (
        "msmt-vs_11000",
        "https://cenmas.ff.cuni.cz/2026/06/09/we-are-hiring-researcher-in-comparative-area-studies-with-a-focus-on-asia-postdoctoral-level/",
    ),
    ("msmt-vs_14000", "https://www.muni.cz/en/about-us/careers"),
    ("msmt-vs_21000", "https://international.cvut.cz/jobs-at-ctu/"),
    ("msmt-vs_21000", "https://www.ciirc.cvut.cz/roboprox/job-positions/"),
    ("msmt-vs_21000", "https://www.aic.fel.cvut.cz/careers"),
    ("msmt-vs_21000", "https://www.fel.cvut.cz/en/faculty/careers"),
    ("msmt-vs_26000", "https://www.vut.cz/en/career"),
    ("msmt-vs_26000", "https://www.vut.cz/kariera"),
    ("msmt-vs_22000", "https://www.vscht.cz/en"),
    ("msmt-vs_31000", "https://www.vse.cz/english/career/"),
    ("msmt-vs_41000", "https://www.czu.cz/en"),
    ("msmt-vs_17000", "https://www.osu.eu/"),
    ("msmt-vs_15000", "https://www.upol.cz/en/"),
]

CITY = {
    "msmt-vs_11000": {"zh-CN": "布拉格", "en": "Prague", "cs": "Praha"},
    "msmt-vs_21000": {"zh-CN": "布拉格", "en": "Prague", "cs": "Praha"},
    "msmt-vs_41000": {"zh-CN": "布拉格", "en": "Prague", "cs": "Praha"},
    "msmt-vs_31000": {"zh-CN": "布拉格", "en": "Prague", "cs": "Praha"},
    "msmt-vs_22000": {"zh-CN": "布拉格", "en": "Prague", "cs": "Praha"},
    "msmt-vs_26000": {"zh-CN": "布尔诺", "en": "Brno", "cs": "Brno"},
    "msmt-vs_14000": {"zh-CN": "布尔诺", "en": "Brno", "cs": "Brno"},
    "msmt-vs_17000": {"zh-CN": "俄斯特拉发", "en": "Ostrava", "cs": "Ostrava"},
    "msmt-vs_15000": {"zh-CN": "奥洛穆茨", "en": "Olomouc", "cs": "Olomouc"},
    "msmt-vs_27000": {"zh-CN": "俄斯特拉发", "en": "Ostrava", "cs": "Ostrava"},
    "msmt-vs_12000": {"zh-CN": "捷克布杰约维采", "en": "České Budějovice", "cs": "České Budějovice"},
    "msmt-vs_13000": {"zh-CN": "拉贝河畔乌斯季", "en": "Ústí nad Labem", "cs": "Ústí nad Labem"},
    "msmt-vs_16000": {"zh-CN": "布尔诺", "en": "Brno", "cs": "Brno"},
    "msmt-vs_18000": {"zh-CN": "赫拉德茨-克拉洛韦", "en": "Hradec Králové", "cs": "Hradec Králové"},
    "msmt-vs_19000": {"zh-CN": "奥帕瓦", "en": "Opava", "cs": "Opava"},
    "msmt-vs_23000": {"zh-CN": "比尔森", "en": "Plzeň", "cs": "Plzeň"},
    "msmt-vs_24000": {"zh-CN": "利贝雷茨", "en": "Liberec", "cs": "Liberec"},
    "msmt-vs_25000": {"zh-CN": "帕尔杜比采", "en": "Pardubice", "cs": "Pardubice"},
    "msmt-vs_28000": {"zh-CN": "兹林", "en": "Zlín", "cs": "Zlín"},
    "msmt-vs_43000": {"zh-CN": "布尔诺", "en": "Brno", "cs": "Brno"},
    "msmt-vs_55000": {"zh-CN": "伊赫拉瓦", "en": "Jihlava", "cs": "Jihlava"},
    "msmt-vs_56000": {"zh-CN": "捷克布杰约维采", "en": "České Budějovice", "cs": "České Budějovice"},
    "msmt-vs_95000": {"zh-CN": "布尔诺", "en": "Brno", "cs": "Brno"},
}


def visible_text(html: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = TAG.sub(" ", text)
    return WS.sub(" ", unescape(text)).strip()


def extract_html_element(
    html: str,
    tag: str,
    *,
    class_name: str | None = None,
    element_id: str | None = None,
) -> str:
    """Return one balanced HTML element selected by tag and optional class/id."""
    token_pattern = re.compile(rf"(?is)</?{re.escape(tag)}\b[^>]*>")
    for opening in token_pattern.finditer(html):
        token = opening.group(0)
        if token.startswith("</"):
            continue
        attrs = token[len(tag) + 1 : -1]
        if class_name:
            class_match = re.search(r"\bclass\s*=\s*[\"']([^\"']*)[\"']", attrs, re.I)
            classes = class_match.group(1).split() if class_match else []
            if class_name not in classes:
                continue
        if element_id:
            id_match = re.search(r"\bid\s*=\s*[\"']([^\"']*)[\"']", attrs, re.I)
            if not id_match or id_match.group(1) != element_id:
                continue
        depth = 1
        for closing in token_pattern.finditer(html, opening.end()):
            if closing.group(0).startswith("</"):
                depth -= 1
            else:
                depth += 1
            if depth == 0:
                return html[opening.start() : closing.end()]
        return ""
    return ""


def configured_detail_html(html: str, source: dict) -> str:
    tag = source.get("detailContainerTag")
    if not isinstance(tag, str) or not tag.strip():
        return html
    return extract_html_element(
        html,
        tag.strip(),
        class_name=source.get("detailContainerClass")
        if isinstance(source.get("detailContainerClass"), str)
        else None,
        element_id=source.get("detailContainerId")
        if isinstance(source.get("detailContainerId"), str)
        else None,
    )


def source_text_hash(text: str) -> str:
    normalized = WS.sub(" ", text).strip()
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_job_reviews(path: Path = REVIEWS) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    reviews = payload.get("reviews") if isinstance(payload, dict) else None
    return reviews if isinstance(reviews, dict) else {}


def apply_translation_review(
    job: dict,
    source_hash: str,
    reviews: dict[str, dict] | None = None,
    windows: list[dict] | None = None,
) -> dict:
    """Bind publication approval to source, facts, translations, and evidence hashes."""
    reviews = reviews if reviews is not None else load_job_reviews()
    entry = reviews.get(job.get("id")) if isinstance(reviews, dict) else None
    entry = entry if isinstance(entry, dict) else None
    locales = entry.get("locales") if entry else None
    current_fact = job_fact_hash(job, windows)
    source_matches = entry is not None and entry.get("sourceHash") == source_hash
    evidence_matches = entry is not None and entry.get("evidenceHash") == source_hash
    facts_match = entry is not None and entry.get("factHash") == current_fact
    reviewer = reviewer_role(entry.get("reviewer") if entry else None)
    reviewed_title = entry.get("title") if entry else None
    titles_ok = isinstance(reviewed_title, dict) and all(
        isinstance(reviewed_title.get(locale), str) and reviewed_title[locale].strip()
        for locale in ("zh-CN", "en", "cs")
    )
    translations_ok = (
        isinstance(locales, dict)
        and titles_ok
        and all(
            isinstance(locales.get(locale), dict)
            and locales[locale].get("status") == "reviewed"
            and isinstance(locales[locale].get("reviewedAt"), str)
            and locales[locale]["reviewedAt"]
            and locales[locale].get("contentHash") == translation_content_hash(reviewed_title[locale])
            for locale in ("zh-CN", "en", "cs")
        )
    )
    fully_reviewed = (
        source_matches
        and evidence_matches
        and facts_match
        and reviewer is not None
        and translations_ok
        and entry.get("normalizationVersion") == FACT_NORMALIZATION_VERSION
    )

    job["sourceHash"] = source_hash
    if fully_reviewed:
        job["title"] = {locale: reviewed_title[locale] for locale in ("zh-CN", "en", "cs")}
        review_locales = {
            locale: {
                "status": "reviewed",
                "translatedFromHash": source_hash,
                "reviewedAt": locales[locale]["reviewedAt"],
                "contentHash": translation_content_hash(reviewed_title[locale]),
            }
            for locale in ("zh-CN", "en", "cs")
        }
        job["translationStatus"] = "verified"
        job["publicationStatus"] = "approved"
        if job.get("lifecycleStatus") not in {"closed", "expired"}:
            job["visibility"] = "public"
        job["reviewedAt"] = max(item["reviewedAt"] for item in review_locales.values())
        job["translationReview"] = {
            "sourceHash": source_hash,
            "factHash": current_fact,
            "evidenceHash": source_hash,
            "normalizationVersion": FACT_NORMALIZATION_VERSION,
            "reviewer": {"role": reviewer},
            "locales": review_locales,
        }
    else:
        review_locales = {}
        for locale in ("zh-CN", "en", "cs"):
            prior = locales.get(locale) if isinstance(locales, dict) else None
            review_locales[locale] = {
                "status": "stale" if source_matches is False and isinstance(prior, dict) else "missing",
                "translatedFromHash": entry.get("sourceHash") if entry else None,
                "reviewedAt": prior.get("reviewedAt") if isinstance(prior, dict) else None,
                "contentHash": prior.get("contentHash") if isinstance(prior, dict) else None,
            }
        job["translationStatus"] = "stale" if entry else "unreviewed"
        job["publicationStatus"] = "review_pending"
        if job.get("visibility") != "archived":
            job["visibility"] = "review_pending"
        job["reviewedAt"] = None
        job["translationReview"] = {
            "sourceHash": source_hash,
            "factHash": current_fact,
            "evidenceHash": source_hash,
            "normalizationVersion": FACT_NORMALIZATION_VERSION,
            "reviewer": {"role": reviewer} if reviewer else None,
            "locales": review_locales,
        }
    return job


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    match = ISO_DATE.search(text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = CZ_DATE.search(text)
    if match:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    match = CZ_TEXT_DATE.search(text)
    if match:
        return date(int(match.group(3)), CZ_MONTHS[match.group(2).lower()], int(match.group(1)))
    match = TEXT_DATE.search(text)
    if match:
        return date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)))
    match = MONTH_FIRST_DATE.search(text)
    if match:
        return date(int(match.group(3)), MONTHS[match.group(1).lower()], int(match.group(2)))
    return None


def iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def classify_track(title: str, body: str = "") -> str | None:
    blob = f"{title} {body}".lower()
    title_blob = title.lower()
    # University vacancy bodies commonly start with “the dean announces”.
    # Administrative-role exclusions apply to the position title, not to that
    # legally required boilerplate in an otherwise research-specific advert.
    if any(marker in title_blob for marker in SKIP_MARKERS):
        return None
    teaching = any(marker in blob for marker in TEACHING_ONLY)
    research = any(
        marker in blob
        for marker in (
            "research",
            "postdoc",
            "postdoktor",
            "scientist",
            "research engineer",
            "research software",
            "scientific programmer",
            "analytical laboratory",
            "analytické laboratoř",
            "analyticke laborato",
            "publikování výsledků",
            "publikovani vysledku",
        )
    ) or bool(re.search(r"\b(?:v[ýy]zkum\w*|v[eě]deck\w*)", blob, re.I))
    technical_title = any(
        marker in title_blob
        for marker in (
            "engineer",
            "inženýr",
            "inzenyr",
            "software",
            "developer",
            "vývojář",
            "vyvojar",
            "devops",
            "hardware",
            "embedded",
            "nanofabric",
            "nanofabrik",
            "it oddělení",
            "it oddeleni",
            "it specialist",
            "technik",
            "programmer",
            "programátor",
            "programator",
        )
    )
    # Some university adverts use a generic transfer-assistant title even when
    # the full duties are laboratory experiments, sensor engineering, power
    # electronics or embedded-software development.  These narrowly-scoped
    # phrases let the body establish technical work without letting incidental
    # mentions of an information system turn an administrative role into one.
    technical_duties = any(
        marker in blob
        for marker in (
            "experimentálních činnost",
            "experimental activities",
            "experimentálním ověřování",
            "experimental verification",
            "zpracování signálů",
            "signal processing",
            "instalace senzorů",
            "sensor installation",
            "vývoji a implementaci softwarového vybavení",
            "vyvoji a implementaci softwaroveho vybaveni",
            "firmware development",
            "programování algoritmů",
            "programovani algoritmu",
            "programming algorithms",
            "laboratorních metod pro testování",
            "laboratornich metod pro testovani",
        )
    )
    if teaching and not research:
        return None
    if any(marker in title_blob for marker in POSTDOC_MARKERS):
        return "postdoc"
    if any(marker in title_blob for marker in ASSISTANT_MARKERS):
        return "assistant"
    # Packet 3: some adverts carry the postdoc evidence only in the body
    # ("The postdoctoral researcher will work closely with PhD students…").
    # A strong role phrase confirms the candidate's own role is postdoctoral;
    # sentences about mentoring or supervising postdocs describe a senior
    # hire, not a postdoc.
    for match in re.finditer(
        r"\bpost[- ]?doc(?:toral)?\s+(?:position|researcher|fellow|scientist|appointment)\b",
        body,
        re.I,
    ):
        start = body.rfind(".", 0, match.start()) + 1
        end = body.find(".", match.end())
        sentence = body[start:end if end > 0 else len(body)]
        if not re.search(r"\b(?:mentor|supervis|manag)", sentence, re.I):
            return "postdoc"
    if research or technical_title or technical_duties:
        return "post_master"
    return None


PHD_REQUIRED = (
    "phd is required",
    "ph.d. is required",
    "phd required",
    "a phd is required",
    "required qualification: phd",
    "required qualification: ph.d",
    "requires a phd",
    "requires a ph.d",
    "must hold a phd",
    "must hold a ph.d",
    "doctoral degree required",
    "completed phd",
    "completed ph.d",
    "doktorské vzdělání podmínkou",
    "doktorský titul podmínkou",
    "požadováno doktorské vzdělání",
    "ukončené doktorské studium",
    "ukoncene doktorske studium",
    "vědecká hodnost ph.d",
    "vedecka hodnost ph.d",
    "vzdělání na úrovni ph.d",
    "vzdelani na urovni ph.d",
    "ukončené postgraduální vzdělání",
    "ukoncene postgradualni vzdelani",
    "titul ph.d.",
)
PHD_NOT_REQUIRED = (
    "phd is not required",
    "ph.d. is not required",
    "phd degree is not required",
    "ph.d. degree is not required",
    "doctoral degree is not required",
    "phd not required",
    "without a phd",
    "doktorské vzdělání není podmínkou",
    "bez nutnosti ph.d.",
)
CLOSED_PHRASES = (
    "applications are closed",
    "application is closed",
    "the position has been filled",
    "position has been filled",
    "the position is filled",
    "call is closed",
    "already closed",
    "no longer accepting",
    "obsazeno",
    "uzavřeno",
    "uzavreno",
    "cancelled",
    "canceled",
)
DEADLINE_MARKERS = (
    "application deadline",
    "submission deadline",
    "closing date",
    "lhůta pro včasné podání žádosti",
    "lhuta pro vcasne podani zadosti",
    "životopis zaslat",
    "zivotopis zaslat",
    "termín přihlášek",
    "termin prihlasek",
    "přihlášky do",
    "prihlasky do",
    "přihlášky budou přijímány do",
    "prihlasky budou prijimany do",
    "uzávěrka přihlášek",
    "uzaverka prihlasek",
    "uzávěrka",
    "uzaverka",
    "nejpozději do",
    "nejpozdeji do",
    "deadline",
    "termín",
    "termin",
)


def extract_qualifications(title: str, body: str) -> dict:
    blob = f"{title} {body}".lower()
    doctorate_required = None
    completed_or_started_doctorate = bool(
        re.search(
            r"\b(?:ukon[cč]en[eé]\s*/\s*zah[aá]jen[eé]|zah[aá]jen[eé]\s*/\s*ukon[cč]en[eé])"
            r"\s+doktorsk[eé]\s+studium\b",
            blob,
        )
    )
    # Negation has precedence.  Several phrases that express an optional PhD
    # also contain a shorter positive marker (for example "PhD ... required").
    if any(marker in blob for marker in PHD_NOT_REQUIRED):
        doctorate_required = False
    elif completed_or_started_doctorate:
        # A combined assistant/assistant-professor call may accept either a
        # completed doctorate or current doctoral study.  A doctorate is not a
        # strict prerequisite for every eligible applicant, while doctoral
        # enrolment is the minimum stated pathway.
        doctorate_required = False
    elif any(marker in blob for marker in PHD_REQUIRED) or re.search(
        r"\b(?:ukon[cč]en[eé]\s+ph\.?d\.?\s+studium|"
        r"doktorsk[ýy]\s+titul\s*\(?ph\.?d\.?\)?|"
        r"(?:candidate|applicant|researcher|uchaze[cč])[^.\n]{0,100}\b(?:with|m[aá])\s+(?:a\s+)?ph\.?d\.?\b|"
        r"(?:must|should|required|requirement|qualification|po[zž]adujeme)[^.\n]{0,120}\bph\.?d\.?\b)",
        blob,
    ):
        doctorate_required = True
    minimum = "unknown"
    if completed_or_started_doctorate:
        minimum = "master"
    elif doctorate_required:
        minimum = "doctorate"
    elif re.search(
        r"\b(?:master'?s?(?:\s+degree)?|master\s+degree|magistersk[eéý]\s+vzd[eě]l[aá]n[ií]|"
        r"inženýrsk[eéý]\s+vzd[eě]l[aá]n[ií]|inzenyrsk[eéý]\s+vzdelani|"
        r"vysokoškolsk[eéý]\s+vzd[eě]l[aá]n[ií]\s+minim[aá]ln[eě]\s+druh[eé]ho\s+stupn[eě]|"
        r"vysokoskolske\s+vzdelani\s+minimalne\s+druheho\s+stupne)\b",
        blob,
    ) or re.search(
        r"\b(?:degree|education|qualification|vzd[eě]l[aá]n[ií]|kvalifikace|titul)\b[^.\n]{0,60}"
        r"\b(?:mgr\.?|ing\.?|m\.?sc\.?)\b",
        blob,
    ) or re.search(
        # A67/A68: MUNI adverts write "MSc or equivalent degree (…)" — the degree
        # word may follow the abbreviation, so recognise both orders.
        r"\b(?:m\.?sc\.?|msc)\b[^.\n]{0,60}\b(?:degree|education|qualification|"
        r"vzd[eě]l[aá]n[ií]|kvalifikace)\b",
        blob,
    ):
        minimum = "master"
        if doctorate_required is None:
            doctorate_required = False
    elif re.search(
        r"\b(?:bachelor'?s?(?:\s+degree)?|bachelor\s+degree|bakal[aá]řsk[eéý]\s+vzd[eě]l[aá]n[ií]|"
        r"bakalarsk[eéý]\s+vzdelani)\b",
        blob,
    ) or re.search(
        r"\b(?:degree|education|qualification|vzd[eě]l[aá]n[ií]|kvalifikace|titul)\b[^.\n]{0,60}"
        r"\b(?:bc\.?|b\.?sc\.?)\b",
        blob,
    ):
        minimum = "bachelor"
        if doctorate_required is None:
            doctorate_required = False
    enrollment = assistant_enrollment(title, body)
    if completed_or_started_doctorate:
        enrollment = "required"
    return {
        "minimumDegree": minimum,
        "doctorateRequired": doctorate_required,
        "doctoralEnrollment": enrollment if enrollment != "unspecified" else "unspecified",
    }


def _contains_closed_signal(text: str) -> bool:
    blob = text.lower()
    contextual_czech = {"uzavřeno", "uzavreno"}
    if any(phrase in blob for phrase in CLOSED_PHRASES if phrase not in contextual_czech):
        return True
    context_markers = re.compile(
        r"(?:v[ýy]b[eě]rov|p[řr]ihl[aá][šs]|pozic|pracovn[ií]\s+m[ií]st|n[aá]bor|inzer)",
        re.I,
    )
    for phrase in contextual_czech:
        start = blob.find(phrase)
        while start >= 0:
            sentence_start = max(
                blob.rfind(marker, 0, start) for marker in (".", "!", "?", "\n")
            )
            following = [
                position
                for marker in (".", "!", "?", "\n")
                if (position := blob.find(marker, start + len(phrase))) >= 0
            ]
            sentence_end = min(following) if following else len(text)
            sentence = text[sentence_start + 1 : sentence_end]
            if context_markers.search(sentence):
                return True
            start = blob.find(phrase, start + len(phrase))
    return blob.strip() in contextual_czech


def is_mixed_listing(text: str) -> bool:
    blob = text.lower()
    has_closed = _contains_closed_signal(text)
    has_open = any(
        phrase in blob
        for phrase in (
            "applications open",
            "accepting applications",
            "open until",
            "přihlášky otevřeny",
            "přihlášky do",
            "application deadline:",
            "deadline:",
        )
    )
    multiple_jobs = len(re.findall(r"\bjob\s+[a-z0-9]|\bpozice\s+[0-9]|\bopen\s+position", blob)) > 1
    return (has_closed and has_open) or multiple_jobs


def entity_scope(text: str, target_title: str = "") -> str:
    """Return text belonging to one vacancy on a potentially mixed listing.

    This deliberately uses explicit neighbouring vacancy boundaries and known
    titles rather than a fixed character window, which can absorb the closure
    state or qualification text of the next listing item.
    """
    if not target_title:
        return text
    lowered = text.lower()
    # Repeated titles commonly occur once in a navigation list and again at the
    # actual vacancy heading.  The last occurrence is usually the content item.
    pos = lowered.rfind(target_title.lower())
    if pos == -1:
        return text
    tail = text[pos:]
    boundaries: list[int] = []

    for candidate in globals().get("VERIFIED_CANDIDATES", []):
        other = str(candidate.get("title") or "")
        if not other or other.casefold() == target_title.casefold():
            continue
        other_pos = tail.lower().find(other.lower(), len(target_title))
        before = tail[:other_pos].rstrip() if other_pos > 0 else ""
        after = tail[other_pos + len(other) :].lstrip() if other_pos > 0 else ""
        if (
            other_pos > 0
            and before
            and before[-1] in ".!?·|"
            and after.startswith(":")
        ):
            boundaries.append(other_pos)

    # Common flattened-list boundaries retained after HTML tags are removed.
    # A84: internal section headings ("Job Description: ...") must not count
    # as the next advert's title - the blocklist keeps employment, salary and
    # deadline sections inside the one vacancy scope.
    section_words = (
        "(?!Description\\b|Details\\b|Requirements\\b|Specification\\b|Profile\\b|"
        "Summary\\b|Purpose\\b|Responsibilities\\b|Qualifications\\b|Offer\\b|Benefits\\b|"
        "Popis\\b|Po\u017eadavky\\b|N\u00e1pl\u0148\\b|Nab\u00eddka\\b|Podm\u00ednky\\b)"
    )
    patterns = (
        r"(?i)(?:[.!?]\s+|\b20\d{2}\s+)(?=(?:job|position|vacancy|pozice)\s+"
        + section_words + r"[A-Z0-9][^:]{0,100}:)",
        r"(?i)(?:[.!?]\s+|\b20\d{2}\s+)(?=(?:post[- ]?doctoral|research\s+(?:assistant|fellow|researcher)|academic\s+researcher|ph\.?d\.?\s+(?:student|position|fellowship))\b"
        + section_words + r"[^.!?\n:]{0,100}:)",
    )
    for pattern in patterns:
        match = re.search(pattern, tail[len(target_title) :])
        if match:
            boundaries.append(len(target_title) + match.end())
    return tail[: min(boundaries)] if boundaries else tail


def page_is_closed(text: str, target_title: str = "") -> bool:
    if target_title:
        scope = entity_scope(text, target_title)
        if scope != text or target_title.lower() in text.lower():
            return _contains_closed_signal(scope)
    if is_mixed_listing(text):
        return False
    return _contains_closed_signal(text)


def extract_deadline(text: str) -> date | None:
    blob = text.lower()
    for marker in DEADLINE_MARKERS:
        idx = blob.find(marker)
        while idx != -1:
            snippet = text[idx : idx + len(marker) + 80]
            parsed = parse_date(snippet)
            if parsed:
                return parsed
            idx = blob.find(marker, idx + 1)
    return None


def extract_employment_fte(text: str) -> float | None:
    """Extract the vacancy's stated workload without confusing it with salary basis."""
    patterns = (
        r"\bpracovn[ií]\s+[úu]vazek\s*[:=\-]?\s*(0(?:[.,]\d+)?|1(?:[.,]0+)?)\b",
        r"\b(?:position\s+workload|employment\s+(?:fte|fraction)|workload(?:\s*\(fte\))?)"
        r"\s*[:=\-]?\s*(0(?:[.,]\d+)?|1(?:[.,]0+)?)\b",
        # A67/A68: MUNI adverts state "Working Hours: 0,5 FTE (part-time
        # employment of 20 hours per week)". Czech decimal commas included.
        r"\bworking\s+hours\s*[:=\-]?\s*(0(?:[.,]\d+)?|1(?:[.,]0+)?)\s*(?:FTE)?\b",
        r"\b(0[.,][1-9]|1(?:[.,]0+)?)\s*FTE\b",
        r"\bfull[- ]time\s+equivalent\s*[:=\-]?\s*(0(?:[.,]\d+)?|1(?:[.,]0+)?)\b",
        r"\bfull[- ]time\s*\((0(?:[.,]\d+)?|1(?:[.,]0+)?)\)(?:\s|$|,|\.)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = float(match.group(1).replace(",", "."))
        if 0 < value <= 1:
            return value
    return None


def extract_employment_start(text: str) -> date | None:
    """Extract an employment start date, keeping it separate from application windows."""
    for marker in (
        r"n[aá]stup\s+mo[zž]n[ýy]\s+od",
        r"n[aá]stup\s+od",
        r"possible\s+start\s+from",
        r"employment\s+start(?:s|ing)?\s+(?:on|from)",
        r"start\s+date",
        r"\bn[aá]stup\b",
    ):
        match = re.search(marker + r".{0,60}", text, re.I)
        if match:
            parsed = parse_date(match.group(0))
            if parsed:
                return parsed
    return None


# A67: money handling. A numeric money token must be read as a whole — the old
# pattern could start in the middle of "30,000" and keep only the trailing
# "000", turning a real funded-PhD salary into 0.
_MONEY_SPACE_CHARS = " \t\u00a0\u202f\u2009\u2007\u2008"
_MONEY_NUMBER = re.compile(rf"[0-9](?:[0-9{_MONEY_SPACE_CHARS}.,]*[0-9])?")
_MONEY_CURRENCY_WORD = r"(?:CZK|Kč|KČ|EUR|€)"
_GROUP3 = re.compile(
    rf"^[0-9]{{1,3}}(?:([{_MONEY_SPACE_CHARS},.])[0-9]{{3}})+$"
)
_DECIMAL_2 = re.compile(r"^([0-9]+)([.,])([0-9]{1,2})$")


def parse_money_number(raw: str | None) -> float | None:
    """Parse one contiguous money token, honouring grouping and decimal separators.

    Money never carries three decimal places, so a separator followed by groups
    of exactly three digits is a thousands separator ("30,000", "30 000",
    "60.000"). One or two trailing digits after a single separator are a decimal
    fraction ("0,5", "25,50", "1,234.56"). Mixed or inconsistent separators stay
    unknown rather than guessing a value.
    """
    if not isinstance(raw, str):
        return None
    token = raw.strip()
    if not token:
        return None
    if _GROUP3.fullmatch(token):
        return float(re.sub(rf"[{_MONEY_SPACE_CHARS},.]", "", token))
    compact = re.sub(rf"[{_MONEY_SPACE_CHARS}]", "", token)
    decimal_match = _DECIMAL_2.fullmatch(compact)
    if decimal_match:
        return float(f"{decimal_match.group(1)}.{decimal_match.group(3)}")
    match = re.fullmatch(r"([0-9]+)([.,])([0-9]+)(?:([.,])([0-9]+))?", compact)
    if match:
        if match.group(4):
            # Standard mixed form "1,234.56" / "1.234,56": exactly three digits
            # between the separators, one or two after the decimal point.
            if len(match.group(3)) == 3 and len(match.group(5)) in (1, 2):
                whole = re.sub(r"[.,]", "", match.group(1) + match.group(2) + match.group(3))
                return float(f"{whole}.{match.group(5)}")
            return None
        integer, _, fraction = match.group(1), match.group(2), match.group(3)
        if len(fraction) == 3:
            return float(integer + fraction)
        return None
    if compact.isdigit():
        return float(compact)
    return None


_SENTENCE_ABBR_MASK = (
    # Same-length masks keep indices valid: abbreviation periods must not end a
    # sentence, or "4-year Ph.D. programme with financial support" loses the
    # doctoral context that justifies the funding reading.
    ("Ph.D.", "Ph=D="),
    ("Ph.D", "Ph=D"),
)
# Thousands/decimal separators inside numbers ("2.000-2.600 EUR") must not act
# as sentence boundaries either, or the salary context is cut off mid-number.
_NUMERIC_SEPARATOR_MASK = re.compile(r"(?<=[0-9])[.,](?=[0-9])")


def _sentence_bounds(text: str, position: int) -> tuple[int, int]:
    masked = _NUMERIC_SEPARATOR_MASK.sub("\u00b7", text)
    for source, replacement in _SENTENCE_ABBR_MASK:
        masked = masked.replace(source, replacement)
    start = max(masked.rfind(mark, 0, position) for mark in (".", "!", "?", "\n"))
    following = [
        found
        for mark in (".", "!", "?", "\n")
        if (found := masked.find(mark, position)) >= 0
    ]
    end = min(following) if following else len(text)
    return start + 1, end


def _money_occurrences(text: str) -> list[dict]:
    """Find currency-adjacent numeric tokens without ever splitting a number."""
    results: list[dict] = []
    for match in re.finditer(_MONEY_CURRENCY_WORD, text):
        currency = "CZK" if match.group(0).casefold() in {"czk", "kč"} else "EUR"
        before = text[max(0, match.start() - 40) : match.start()]
        after = text[match.end() : match.end() + 40]
        candidates: list[tuple[int, int, str]] = []
        trailing = re.search(
            # "60 000,- Kč" — the Czech ",-" no-haléře suffix sits between the
            # number and the currency; it is punctuation, not part of the amount.
            rf"({_MONEY_NUMBER.pattern})[{_MONEY_SPACE_CHARS}]*(?:[,.][-–—-]?[{_MONEY_SPACE_CHARS}]*)?$",
            before.rstrip(""),
        )
        if trailing:
            start = match.start() - (len(before) - trailing.start())
            candidates.append((start, match.start(), trailing.group(1)))
        leading = re.match(rf"^[{_MONEY_SPACE_CHARS}]*({_MONEY_NUMBER.pattern})", after)
        if leading:
            start = match.end() + leading.start(1)
            candidates.append((start, start + len(leading.group(1)), leading.group(1)))
        if not candidates:
            continue
        # Prefer the token that carries more of a plausible amount and does not
        # cross into an unrelated word boundary.
        token_start, token_end, raw = max(
            candidates, key=lambda item: (len(re.sub(rf"[{_MONEY_SPACE_CHARS}]", "", item[2])), item[0])
        )
        results.append(
            {
                "start": token_start,
                "end": token_end,
                "raw": raw,
                "currency": currency,
                "position": "before" if token_end == match.start() else "after",
            }
        )
    return results


SALARY_TERM_RE = re.compile(
    r"\b(?:salary|wage|gross|net\b|netto|remuneration|compensation|monthly\s+pay|stipend(?:ium)?|"
    r"mzda|mzdov\w*|plat(?:ov\w*)?|odm[eě]n\w*|ohodnocen\w*)\b",
    re.I,
)
SALARY_CYCLE_YEAR_RE = re.compile(
    r"\b(?:per\s+(?:year|annum)|annually|annual\s+(?:salary|stipend|wage|remuneration|package)|"
    r"yearly\s+(?:salary|stipend|wage|package)|ro[čc]n[ěe]\s+(?:mzd\w*|plat\w*|ohodnocen\w*)|"
    r"mzda\s+ro[čc]n[ěe])\b",
    re.I,
)
SALARY_CYCLE_MONTH_RE = re.compile(
    r"\b(?:per\s+month|monthly|měs[íi][čc]n[ěe]|měs[íi][čc]n[íi]\s+(?:mzd\w*|plat\w*|ohodnocen\w*)|"
    r"mzda\s+měs[íi][čc]n[ěe]|za\s+měs[íi]c)\b",
    re.I,
)
SALARY_CYCLE_HOUR_RE = re.compile(r"\b(?:per\s+hour|hourly|hodinov[ěe])\b", re.I)
SALARY_TAX_NET_RE = re.compile(r"\b(?:net\b|netto|čist[ýáéeéí]\w*)\b", re.I)
SALARY_TAX_GROSS_RE = re.compile(r"\b(?:gross|hrub[ýáéeéí]\w*)\b", re.I)
UNPAID_NEGATIVE_RE = re.compile(
    r"\b(?:self[- ]funded|unfunded|unpaid|without\s+(?:a\s+)?(?:salary|stipend|remuneration)|"
    r"vlastn[íy]\s+prost[rř]edk\w*)\b",
    re.I,
)
DOCTORAL_POSITION_RE = re.compile(r"\b(?:ph\.?\s?d\.?|doctoral|doktorandsk\w*|diserta[čc]n\w*)\b", re.I)
SOFT_PAID_RE = re.compile(
    r"\b(?:stipend(?:ium)?|financial\s+support|financially\s+supported|funded)\b",
    re.I,
)
FUNDING_EMPLOYMENT_RE = re.compile(
    r"\b(?:employment|contract|salary|wage|remuneration|compensation|"
    r"pracovn[íi]\s+smlouva|pracovn[íi]\s+[úu]vazek|mzda|plat\b|ohodnocen[íi])\b",
    re.I,
)
FUNDING_STIPEND_RE = re.compile(
    r"\b(?:stipend(?:ium)?|scholarship|financial\s+support|financially\s+supported|"
    r"st[íi]pendn[íi]|soc[íi]áln[íi]\s+stipend)\b",
    re.I,
)


def extract_salary_facts(text: str) -> dict:
    """Extract salary amount, currency, cycle, tax basis and range with evidence.

    Each dimension is kept independent: an amount without a stated cycle stays
    ``unspecified``; a net figure is never relabelled gross; grant budgets and
    expense reimbursements in sentences without salary terms are not salaries.
    """
    facts: dict = {
        "amount": None,
        "amountMin": None,
        "amountMax": None,
        "currency": None,
        "cycle": None,
        "tax": None,
        "basisFte": None,
        "paidStatus": "unconfirmed",
        "reason": None,
    }
    occurrences = _money_occurrences(text)
    salary_context = ""
    chosen = None
    for occurrence in occurrences:
        start, end = _sentence_bounds(text, occurrence["start"])
        sentence = text[start:end]
        if SALARY_TERM_RE.search(sentence):
            salary_context = sentence
            chosen = occurrence
            break
    basis_match = re.search(
        r"\b(?:full[- ]time|cel[ýy]\s+[úu]vazek)\b", salary_context, re.I
    ) if salary_context else None
    mixed_basis = bool(
        salary_context
        and re.search(
            r"\bpart[- ]time.{0,30}(?:full[- ]time|cel[ýy]\s+[úu]vazek)"
            r"|(?:full[- ]time|cel[ýy]\s+[úu]vazek).{0,30}\bpart[- ]time\b",
            salary_context,
            re.I,
        )
    )
    if basis_match and not mixed_basis:
        facts["basisFte"] = 1.0
    if chosen is None:
        if occurrences:
            facts["reason"] = "currency-amount-found-without-salary-terms"
        return facts
    facts["paidStatus"] = "confirmed"
    facts["currency"] = chosen["currency"]
    if SALARY_TAX_NET_RE.search(salary_context):
        facts["tax"] = "net"
    elif SALARY_TAX_GROSS_RE.search(salary_context):
        facts["tax"] = "gross"
    if SALARY_CYCLE_HOUR_RE.search(salary_context):
        facts["cycle"] = "hour"
    elif SALARY_CYCLE_YEAR_RE.search(salary_context):
        facts["cycle"] = "year"
    elif SALARY_CYCLE_MONTH_RE.search(salary_context):
        facts["cycle"] = "month"
    elif basis_match and chosen["currency"] == "CZK":
        # Czech salary adverts quote the payroll amount against an úvazek; the
        # payroll period for such a basis is monthly unless stated otherwise.
        facts["cycle"] = "month"
    range_match = None
    prefix = text[: chosen["start"]]
    before_token = re.search(
        rf"({_MONEY_NUMBER.pattern})[{_MONEY_SPACE_CHARS}]*(?:[–—-]|to|až|do)[{_MONEY_SPACE_CHARS}]*$",
        prefix[-64:],
        re.I,
    )
    if before_token:
        range_match = before_token.group(1)
    else:
        between_token = re.search(
            rf"\bbetween\s+({_MONEY_NUMBER.pattern})[{_MONEY_SPACE_CHARS}]+and\s+$",
            prefix[-64:],
            re.I,
        )
        if between_token:
            range_match = between_token.group(1)
    if range_match is not None:
        low = parse_money_number(range_match)
        high = parse_money_number(chosen["raw"])
        if low is not None and high is not None and low < high:
            facts["amountMin"] = low
            facts["amountMax"] = high
            facts["reason"] = "range"
            return facts
    # Some official adverts repeat the currency on both ends, for example
    # ``from 65,000 CZK to 75,000 CZK``.  In that form the first number is the
    # chosen occurrence, so the backward-only range detector above cannot see
    # the upper bound.  Accept only the immediately connected next monetary
    # occurrence in the same salary sentence; unrelated benefits or another
    # role remain subject to the multiple-statement guard below.
    following = [item for item in occurrences if item["start"] > chosen["start"]]
    if following:
        other_occurrence = following[0]
        connector = text[chosen["end"] : other_occurrence["start"]]
        currency_token = r"(?:CZK|Kč|EUR|€|USD|US\$|\$|GBP|£|CHF|PLN|SEK|NOK|DKK|CNY|RMB|HUF)"
        if (
            other_occurrence["currency"] == chosen["currency"]
            and re.fullmatch(
                rf"[{_MONEY_SPACE_CHARS}]*(?:{currency_token})?[{_MONEY_SPACE_CHARS}]*"
                rf"(?:[–—-]|to|až|do)[{_MONEY_SPACE_CHARS}]*",
                connector,
                re.I,
            )
        ):
            low = parse_money_number(chosen["raw"])
            high = parse_money_number(other_occurrence["raw"])
            if low is not None and high is not None and low < high:
                facts["amountMin"] = low
                facts["amountMax"] = high
                facts["reason"] = "range"
                return facts
    amount = parse_money_number(chosen["raw"])
    if amount is None:
        facts["reason"] = "ambiguous-number-format"
        return facts
    for occurrence in occurrences:
        if occurrence["start"] == chosen["start"]:
            continue
        start, end = _sentence_bounds(text, occurrence["start"])
        sentence = text[start:end]
        if not SALARY_TERM_RE.search(sentence):
            continue
        other = parse_money_number(occurrence["raw"])
        if other is None or other == amount:
            continue
        if min(other, amount) / max(other, amount) < 0.7:
            # A85: distinct per-role pay statements (CZU's pro-rated 48,000 of
            # 60,000 stays a single basis at ratio 0.8; genuinely different
            # role salaries do not).
            facts["amount"] = None
            facts["currency"] = None
            facts["basisFte"] = None
            facts["reason"] = "multiple-salary-statements"
            return facts
    facts["amount"] = amount
    return facts


def extract_funding_type(text: str) -> str | None:
    """Classify compensation structure: employment, stipend, or a mixed package."""
    blob = text
    if UNPAID_NEGATIVE_RE.search(blob):
        return None
    employment = bool(FUNDING_EMPLOYMENT_RE.search(blob))
    stipend = bool(FUNDING_STIPEND_RE.search(blob))
    if employment and stipend:
        return "mixed"
    if employment:
        return "employment"
    if stipend:
        return "stipend"
    return None


def funding_supported_status(text: str) -> str | None:
    """Confirm pay from doctoral funding wording without accepting self-funded programmes."""
    for match in SOFT_PAID_RE.finditer(text):
        start, end = _sentence_bounds(text, match.start())
        sentence = text[start:end]
        if UNPAID_NEGATIVE_RE.search(sentence):
            continue
        if DOCTORAL_POSITION_RE.search(sentence):
            return "confirmed"
    return None



def assistant_enrollment(title: str, body: str) -> str:
    blob = f"{title} {body}".lower()
    doc_not_req_patterns = (
        r"(?:enroll(?:ed|ment)?|enrol(?:led|ment)?|registration|doctoral\s+stud(?:y|ies))[^.\n]{0,60}\b(?:not\s+required|is\s+optional)",
        r"\b(?:not\s+required|is\s+optional)[^.\n]{0,60}(?:enroll(?:ed|ment)?|enrol(?:led|ment)?|registration|doctoral\s+stud(?:y|ies))",
        r"\b(?:without\s+(?:the\s+)?need\s+to\s+enroll|bez\s+nutnosti\s+z[aá]pisu|bez\s+z[aá]pisu\s+do\s+doktorsk[eé]ho)\b",
        r"\b(?:doctoral\s+(?:enrollment|enrolment|registration)\s+not\s+required|ph\.?d\.??\s+(?:enrollment|enrolment|registration)\s+not\s+required)\b",
        r"\bz[aá]pis\s+do\s+doktorsk[eé]ho\s+studia[^.\n]{0,40}(?:nen[ií]\s+podm[ií]nkou|nen[ií]\s+nutn[ýy])",
    )
    if any(re.search(p, blob) for p in doc_not_req_patterns):
        return "not_required"
    title_blob = title.lower()
    title_requires_enrollment = any(
        marker in title_blob
        for marker in (
            "phd student",
            "ph.d. student",
            "phd position",
            "ph.d. position",
            "phd fellowship",
            "ph.d. fellowship",
            "phd candidate",
            "ph.d. candidate",
            "doctoral candidate",
            "doctoral student",
            "doctoral fellowship",
            "doktorand",
        )
    )
    explicit_required_patterns = (
        r"\b(?:must|required|requirement|condition)[^.\n]{0,80}(?:enrol|enroll|registration)[^.\n]{0,40}(?:ph\.?d|doctoral)",
        r"\b(?:enrol|enroll|registration)[^.\n]{0,60}(?:ph\.?d|doctoral)[^.\n]{0,40}(?:must|required|condition)",
        r"\b(?:enrolled|enrolment|enrollment|registration)\s+in\s+(?:a\s+)?(?:ph\.?d|doctoral)\b",
        r"\bz[aá]pis\s+do\s+doktorsk[eé]ho\s+studia\b",
        r"\bdoktorsk[eé]\s+studium[^.\n]{0,70}(?:podm[ií]nkou|po[zž]adov[aá]no|p[řr]ed\s+dokon[cč]en[ií]m)",
    )
    if title_requires_enrollment or any(re.search(pattern, blob) for pattern in explicit_required_patterns):
        return "required"
    return "unspecified"


def classify_degrees(track: str | None, title: str = "", body: str = "") -> dict:
    # ``track`` is a browse classification, never qualification evidence.
    # Unknown facts remain unknown until the vacancy body states them.
    return extract_qualifications(title, body) if (title or body) else {
        "minimumDegree": "unknown",
        "doctorateRequired": None,
        "doctoralEnrollment": "unspecified",
    }


def _request_bytes_with_retry(
    req: urllib.request.Request,
    *,
    timeout: int,
    max_bytes: int | None = None,
    now: datetime | None = None,
    sleep_fn=None,
) -> TransportResult:
    """Retry bounded, idempotent official-source reads on transient failures.

    A valid Retry-After is the earliest retry. Delays longer than
    MAX_IN_PROCESS_RETRY_SECONDS become a deferred result for the scheduler
    instead of an in-process sleep. Throttling is not opportunity closure.
    """
    url = str(req.full_url)
    sleeper = sleep_fn or time.sleep
    current = _aware_now(now)
    until = host_cooldown_until(url, current)
    if until is not None:
        return TransportResult(status=429, body=b"", headers={}, retry_at=until, deferred=True)
    last = TransportResult(status=0, body=b"")
    for attempt in range(len(REQUEST_RETRY_DELAYS) + 1):
        headers: dict[str, str] = {}
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as response:
                body = response.read() if max_bytes is None else response.read(max_bytes + 1)
                status = response.status
                headers = _header_map(getattr(response, "headers", None))
        except urllib.error.HTTPError as error:
            body = error.read() if error.fp else b""
            status = error.code
            headers = _header_map(getattr(error, "headers", None) or getattr(error, "hdrs", None))
        except Exception:
            body = b""
            status = 0
            headers = {}
        if max_bytes is not None and len(body) > max_bytes:
            return TransportResult(status=413, body=b"", headers=headers)
        last = TransportResult(status=status, body=body, headers=headers)
        if status not in TRANSIENT_HTTP_STATUSES:
            return last
        retry_at = parse_retry_after(headers.get("retry-after"), current)
        if retry_at is not None:
            wait = (retry_at - current).total_seconds()
            if wait > MAX_IN_PROCESS_RETRY_SECONDS:
                set_host_cooldown(url, retry_at)
                last.retry_at = retry_at
                last.deferred = True
                return last
            if wait > 0:
                sleeper(wait)
                current = _aware_now(current + timedelta(seconds=wait))
                continue
        if attempt == len(REQUEST_RETRY_DELAYS):
            return last
        sleeper(REQUEST_RETRY_DELAYS[attempt])
        current = _aware_now(current + timedelta(seconds=REQUEST_RETRY_DELAYS[attempt]))
    return last  # pragma: no cover - loop always returns


def request(url: str, timeout: int = 45, now: datetime | None = None) -> tuple[int, str]:
    host = (urlsplit(url).hostname or "").lower()
    # UHK returns HTTP 418 solely when the User-Agent contains a crawler name,
    # while serving the same public page to ordinary browsers. Keep the narrow
    # browser-compatible identity here and retain an explicit project contact.
    user_agent = CHROME_UA if host == "www.uhk.cz" else UA
    req = urllib.request.Request(
        _request_uri(url),
        headers={
            "User-Agent": user_agent,
            "X-Crawler-Contact": "https://czech-uni-application.com/contact",
            "Accept": "application/json" if host == "dumbledore.zcu.cz" else "text/html,application/xhtml+xml",
        },
    )
    result = _request_bytes_with_retry(req, timeout=timeout, now=now)
    return result.status, result.text()


def request_json(
    url: str,
    payload: dict,
    headers: dict[str, str] | None = None,
    timeout: int = 45,
) -> tuple[int, str]:
    """POST a JSON document for official career widgets used as source APIs."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    req = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    result = _request_bytes_with_retry(req, timeout=timeout)
    return result.status, result.text()


def _request_uri(url: str) -> str:
    """Encode an official IRI without double-encoding existing URL escapes."""
    parsed = urlsplit(url)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc.encode("idna").decode("ascii"),
            quote(parsed.path, safe="/%:@"),
            quote(parsed.query, safe="=&%:@?+,;"),
            quote(parsed.fragment, safe="%:@?+,;"),
        )
    )


def request_binary(url: str, timeout: int = 60) -> tuple[int, bytes]:
    """Read a bounded official attachment without decoding its binary body."""
    # ZCU's official xdoc gateway returns HTTP 406 for a PDF-specific Accept
    # header even though the response is a PDF. Keep this host exception narrow
    # so other attachment sources retain the stricter content negotiation.
    accept = "*/*" if urlsplit(url).hostname == "xdoc.zcu.cz" else "application/pdf,application/octet-stream"
    req = urllib.request.Request(
        _request_uri(url),
        headers={"User-Agent": UA, "Accept": accept},
    )
    result = _request_bytes_with_retry(req, timeout=timeout, max_bytes=MAX_PDF_BYTES)
    return result.status, result.body


def extract_pdf_text(body: bytes) -> str:
    """Extract a PDF text layer, then use local Windows OCR for scanned pages.

    The OCR path is deliberately local and bounded.  A host without the PDF or
    OCR dependencies returns no text, which makes the source run incomplete;
    it never converts an extraction failure into a vacancy disappearance.
    """
    if not body.startswith(b"%PDF") or len(body) > MAX_PDF_BYTES:
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(body), strict=False)
        direct = "\n".join((page.extract_text() or "") for page in reader.pages)
        direct = WS.sub(" ", direct).strip()
    except Exception:
        direct = ""
    if len(direct) >= 80:
        return direct
    if os.name == "nt" and not WINDOWS_OCR.is_file():
        return ""
    if os.name != "nt" and not shutil.which("tesseract"):
        return ""
    try:
        import fitz

        document = fitz.open(stream=body, filetype="pdf")
        if document.page_count < 1 or document.page_count > MAX_PDF_PAGES:
            return ""
        (ROOT / "work").mkdir(parents=True, exist_ok=True)
        chunks: list[str] = []
        with tempfile.TemporaryDirectory(prefix="ctu-ocr-", dir=ROOT / "work") as temp_dir:
            for page_number, page in enumerate(document):
                image_path = Path(temp_dir) / f"page-{page_number + 1}.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pixmap.save(image_path)
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(WINDOWS_OCR),
                        "-Path",
                        str(image_path),
                    ] if os.name == "nt" else ["tesseract", str(image_path), "stdout", "-l", "ces+eng"],
                    capture_output=True,
                    check=False,
                    encoding="utf-8",
                    errors="replace",
                    timeout=90,
                )
                text = WS.sub(" ", result.stdout).strip()
                if result.returncode != 0 or len(text) < 20:
                    return ""
                chunks.append(text)
        return "\n".join(chunks).strip()
    except Exception:
        return ""


def page_ok(status: int, html: str) -> bool:
    if status != 200 or not html.strip():
        return False
    head = visible_text(html)[:800].lower()
    return not any(phrase in head for phrase in DEAD)


def slug_id(employer_id: str, title: str, source_url: str) -> str:
    raw = f"{employer_id}|{title}|{source_url}"
    digest = __import__("hashlib").sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"job-{employer_id[-5:]}-{digest}"


def parse_mff_listing(html: str, page_url: str) -> list[dict]:
    text = visible_text(html)
    jobs = []
    pattern = re.compile(
        r"(Academic Researcher|Research Fellow|Postdoctoral position|Postdoctoral|Assistant Professor|Lecturer|Lector)[^\n]{0,180}?Job Offer Code:\s*(\S+)\s*Submission Deadline:\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
        re.I,
    )
    # The stored HTML may flatten newlines; use a looser split on Job Offer Code.
    chunks = re.split(r"Job Offer Code:\s*", text)
    if len(chunks) < 2:
        return jobs
    preamble = chunks[0]
    titles = re.split(r"\s{2,}| · ", preamble)
    current_title = titles[-1].strip() if titles else ""
    # Re-parse by walking "Title ... Job Offer Code: X Submission Deadline: Month DD, YYYY"
    matches = re.finditer(
        r"([A-Z][^:]{8,160}?)\s+Job Offer Code:\s*(\S+)\s+Submission Deadline:\s*([A-Za-z]+ \d{1,2}, 20\d{2})",
        text,
    )
    for match in matches:
        title = WS.sub(" ", match.group(1)).strip(" -·")
        if title.lower().startswith("open positions"):
            title = title.split("Open Positions")[-1].strip(" -·")
        track = classify_track(title)
        if not track:
            continue
        deadline = parse_date(match.group(3))
        jobs.append(
            {
                "title": title,
                "code": match.group(2),
                "closesAt": iso_date(deadline),
                "sourceUrl": page_url,
                "track": track,
            }
        )
    return jobs


def _cuni_ajax_html(payload_text: str) -> str | None:
    """Decode the HTML fragment returned by Charles University's job API."""
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    fragment = payload.get("html")
    if payload.get("result") != "ok" or not isinstance(fragment, str):
        return None
    return fragment


def parse_cuni_ajax_listing(
    payload_text: str,
    detail_base_url: str = "https://cuni.cz/UKEN-1573.html",
) -> list[dict]:
    """Parse the central Charles University active-position result pages.

    Listing titles are deliberately not used to decide eligibility.  Every
    entry is followed to its official detail and the full vacancy body makes
    the research, degree, doctoral-enrolment and pay decisions.
    """
    fragment = _cuni_ajax_html(payload_text)
    if fragment is None:
        return []
    results: list[dict] = []
    seen: set[str] = set()
    for match in re.finditer(
        r"(?is)<a\b[^>]*href=[\"']\?pracid=([^\"']+)[\"'][^>]*>(.*?)</a>",
        fragment,
    ):
        raw_code = unescape(match.group(1)).strip()
        code = parse_qs(f"pracid={raw_code}").get("pracid", [raw_code])[0]
        if not code or code in seen:
            continue
        block = match.group(2)
        name = re.search(r"(?is)data-name=[\"']([^\"']+)[\"']", block)
        title = unescape(name.group(1)).strip() if name else ""
        if not title:
            title_match = re.search(
                r"(?is)<div\b[^>]*class=[\"'][^\"']*\bname\b[^\"']*[\"'][^>]*>(.*?)</div>",
                block,
            )
            title = visible_text(title_match.group(1)) if title_match else ""
        if not title:
            continue
        seen.add(code)
        detail_url = f"{detail_base_url}?{urlencode({'pracid': code})}"
        results.append(
            {
                "title": WS.sub(" ", title),
                "code": code,
                "sourceUrl": detail_url,
                "applicationUrl": detail_url,
            }
        )
    return results


def _cuni_ajax_pagination_urls(payload_text: str, current_url: str) -> list[str]:
    fragment = _cuni_ajax_html(payload_text)
    if fragment is None:
        return []
    pages = sorted({int(value) for value in re.findall(r"data-page=[\"'](\d+)[\"']", fragment)})
    current = urlsplit(current_url)
    current_page = int(parse_qs(current.query).get("p", ["1"])[0])
    results: list[str] = []
    for page in pages:
        if page <= current_page:
            continue
        query = parse_qs(current.query, keep_blank_values=True)
        query["p"] = [str(page)]
        url = current._replace(query=urlencode(query, doseq=True)).geturl()
        if url not in results:
            results.append(url)
    return results


def parse_lmc_widget_config(html: str) -> dict | None:
    """Read the public widget configuration embedded by an official employer portal."""
    for match in re.finditer(
        r"(?is)__LMC_CAREER_WIDGET__\.push\s*\(\s*(\{.*?\})\s*\)\s*;",
        html,
    ):
        try:
            config = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(config, dict):
            continue
        if not all(isinstance(config.get(key), str) and config[key] for key in ("apiKey", "widgetId")):
            continue
        return config
    return None


def _lmc_listing_payload(config: dict, page: int) -> dict:
    return {
        "operationName": "LmcJobList",
        "query": LMC_LIST_QUERY,
        "variables": {
            "widgetId": config["widgetId"],
            "page": page,
            "filters": [],
            "useExampleData": False,
            "host": config.get("host"),
        },
    }


def _lmc_detail_payload(config: dict, job_id: str) -> dict:
    return {
        "operationName": "LmcJobDetail",
        "query": LMC_DETAIL_QUERY,
        "variables": {
            "widgetId": config["widgetId"],
            "jobAdId": job_id,
            "host": config.get("host"),
        },
    }


def _lmc_job_groups(group: dict) -> list[dict]:
    rows = [item for item in group.get("jobAds") or [] if isinstance(item, dict)]
    for child in group.get("groups") or []:
        if isinstance(child, dict):
            rows.extend(_lmc_job_groups(child))
    return rows


def parse_lmc_graphql_listing(
    payload_text: str,
    portal_url: str,
    detail_path: str = "detail-pozice",
) -> tuple[list[dict], dict] | None:
    """Parse one complete page returned by the public Alma/LMC career widget API."""
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("errors"):
        return None
    try:
        listing = payload["data"]["widget"]["jobAdList"]
        group = listing["groupedJobAds"]
        paginator = listing["paginator"]
    except (KeyError, TypeError):
        return None
    if not isinstance(group, dict) or not isinstance(paginator, dict):
        return None
    try:
        current_page = int(paginator["currentPage"])
        last_page = int(paginator["lastPage"])
        total_items = int(paginator["totalNumberOfItems"])
    except (KeyError, TypeError, ValueError):
        return None
    detail_base = urljoin(portal_url, detail_path.strip("/") + "/")
    rows: list[dict] = []
    seen: set[str] = set()
    for item in _lmc_job_groups(group):
        job_id = str(item.get("id") or "").strip()
        title = WS.sub(" ", str(item.get("title") or "")).strip()
        if not job_id or not title or job_id in seen:
            continue
        seen.add(job_id)
        detail_url = detail_base.rstrip("/") + "?" + urlencode({"r": "detail", "id": job_id})
        rows.append(
            {
                "code": job_id,
                "title": title,
                "sourceUrl": detail_url,
                "applicationUrl": detail_url,
            }
        )
    return rows, {
        "currentPage": current_page,
        "lastPage": last_page,
        "totalNumberOfItems": total_items,
    }


def _lmc_job_ad(payload_text: str) -> dict | None:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("errors"):
        return None
    try:
        job = payload["data"]["widget"]["jobAd"]
    except (KeyError, TypeError):
        return None
    return job if isinstance(job, dict) else None


def _lmc_working_languages(parameters: dict) -> list[str]:
    results: list[str] = []
    aliases = {
        "čeština": "cs",
        "cestina": "cs",
        "czech": "cs",
        "angličtina": "en",
        "anglictina": "en",
        "english": "en",
        "němčina": "de",
        "nemcina": "de",
        "german": "de",
        "slovenština": "sk",
        "slovenstina": "sk",
        "slovak": "sk",
    }
    for row in parameters.get("requiredLanguages") or []:
        if not isinstance(row, dict):
            continue
        raw = str(row.get("language") or "").strip().casefold()
        code = aliases.get(raw)
        if code and code not in results:
            results.append(code)
    return results


def _lmc_required_degree(value: object) -> tuple[str, bool | None] | None:
    """Map the widget's structured minimum-education field without guessing a level."""
    text = str(value or "").strip().casefold()
    if not text:
        return None
    if any(marker in text for marker in ("doktor", "phd", "ph.d")):
        return "doctorate", True
    if any(marker in text for marker in ("magister", "inženýr", "inzenyr", "master")):
        return "master", False
    if any(marker in text for marker in ("bakal", "bachelor")):
        return "bachelor", False
    # “University education” names no minimum cycle and stays unknown.
    return None


def parse_lmc_graphql_detail(
    payload_text: str,
    source_url: str,
    expected_id: str | None = None,
) -> dict | None:
    """Turn a widget detail response into a source-scoped research candidate."""
    job = _lmc_job_ad(payload_text)
    if job is None:
        return None
    job_id = str(job.get("id") or "").strip()
    if not job_id or (expected_id and job_id != expected_id):
        return None
    title = WS.sub(" ", str(job.get("title") or "")).strip()
    if not title:
        return None
    content = job.get("content") if isinstance(job.get("content"), dict) else {}
    html_content = str(content.get("htmlContent") or "")
    section_parts: list[str] = []
    for section in content.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_parts.extend([str(section.get("title") or ""), str(section.get("text") or "")])
    parameters = job.get("parameters") if isinstance(job.get("parameters"), dict) else {}
    structured_parts: list[str] = []
    for key in (
        "requiredEducation",
        "employmentTypes",
        "employmentDurations",
        "contractTypes",
        "hoursPerWeek",
        "start",
        "end",
    ):
        value = parameters.get(key)
        if isinstance(value, list):
            structured_parts.extend(str(item) for item in value if item)
        elif value:
            structured_parts.append(str(value))
    for language in parameters.get("requiredLanguages") or []:
        if isinstance(language, dict):
            structured_parts.append(
                " ".join(str(language.get(key) or "") for key in ("language", "skill")).strip()
            )
    raw_html = (
        f"<h1>{escape(title)}</h1>"
        + html_content
        + "".join(f"<p>{escape(value)}</p>" for value in section_parts + structured_parts if value)
    )
    parsed = parse_generic_job_page(raw_html, source_url, title)
    if parsed is None:
        return None
    valid_from = str(job.get("validFrom") or "")
    if re.match(r"^20\d{2}-\d{2}-\d{2}", valid_from):
        parsed["opensAt"] = valid_from[:10]
    salary = job.get("salary") if isinstance(job.get("salary"), dict) else None
    if salary:
        minimum = salary.get("min")
        maximum = salary.get("max")
        amount = minimum if isinstance(minimum, (int, float)) else maximum
        if isinstance(amount, (int, float)):
            parsed["salaryAmount"] = float(amount)
            parsed["salaryCurrency"] = salary.get("currency")
            parsed["paidStatus"] = "confirmed"
    structured_degree = _lmc_required_degree(parameters.get("requiredEducation"))
    if structured_degree is not None:
        parsed["minimumDegree"], parsed["doctorateRequired"] = structured_degree
        parsed["qualificationFactsAuthoritative"] = True
    language_iso = str(job.get("languageIso") or "").lower()
    if language_iso in {"cs", "en"}:
        parsed["sourceLanguage"] = language_iso
    parsed.update(
        {
            "code": job_id,
            "title": title,
            "sourceUrl": source_url,
            "applicationUrl": source_url,
            "applicationMethod": "official_ats",
            "workingLanguages": _lmc_working_languages(parameters),
            "_factHtml": raw_html,
            "_factText": visible_text(raw_html),
        }
    )
    return parsed


def discover_lmc_graphql_source(source: dict, fetch_page, post_json) -> dict:
    """Discover and fully read one official LMC widget without browser automation."""
    attempts: list[dict] = []
    quarantined: list[dict] = []
    portal_url = source["url"]
    status, landing_html = fetch_page(portal_url)
    landing_ok = page_ok(status, landing_html)
    attempts.append(
        {
            "sourceId": source["id"],
            "url": portal_url,
            "status": status,
            "ok": landing_ok,
            "kind": "listing-shell",
        }
    )
    if not landing_ok:
        return {"candidates": [], "attempts": attempts, "quarantined": quarantined, "complete": False}
    config = parse_lmc_widget_config(landing_html)
    if config is None:
        attempts.append(
            {
                "sourceId": source["id"],
                "url": portal_url,
                "status": status,
                "ok": False,
                "kind": "widget-config",
                "reason": "missing-public-widget-config",
            }
        )
        return {"candidates": [], "attempts": attempts, "quarantined": quarantined, "complete": False}

    endpoint = str(source.get("apiUrl") or LMC_GRAPHQL_ENDPOINT)
    headers = {"X-Api-Key": config["apiKey"]}
    max_pages = max(1, min(int(source.get("maxPages") or 20), 20))
    listing_rows: list[dict] = []
    expected_total: int | None = None
    last_page = 1
    complete = True
    page = 1
    while page <= last_page and page <= max_pages:
        api_status, body = post_json(endpoint, _lmc_listing_payload(config, page), headers)
        parsed_page = parse_lmc_graphql_listing(
            body,
            portal_url,
            str(source.get("detailPath") or config.get("detailPath") or "detail-pozice"),
        )
        page_okay = api_status == 200 and parsed_page is not None
        attempts.append(
            {
                "sourceId": source["id"],
                "url": endpoint,
                "status": api_status,
                "ok": page_okay,
                "kind": "listing-api",
                "page": page,
                **({} if page_okay else {"reason": "invalid-widget-listing-response"}),
            }
        )
        if not page_okay:
            complete = False
            break
        rows, paginator = parsed_page
        if paginator["currentPage"] != page:
            attempts[-1]["ok"] = False
            attempts[-1]["reason"] = "widget-page-number-mismatch"
            complete = False
            break
        last_page = paginator["lastPage"]
        expected_total = paginator["totalNumberOfItems"]
        listing_rows.extend(rows)
        page += 1
    if last_page > max_pages:
        complete = False
        attempts.append(
            {
                "sourceId": source["id"],
                "url": endpoint,
                "status": None,
                "ok": False,
                "kind": "listing-api",
                "reason": "pagination-limit-exceeded",
            }
        )

    unique_rows = {str(item["code"]): item for item in listing_rows}
    if complete and expected_total is not None and len(unique_rows) != expected_total:
        complete = False
        attempts.append(
            {
                "sourceId": source["id"],
                "url": endpoint,
                "status": 200,
                "ok": False,
                "kind": "listing-api",
                "reason": f"listing-count-mismatch:{len(unique_rows)}/{expected_total}",
            }
        )

    candidates: list[dict] = []
    for item in unique_rows.values():
        api_status, body = post_json(endpoint, _lmc_detail_payload(config, item["code"]), headers)
        valid_job = _lmc_job_ad(body)
        detail_ok = (
            api_status == 200
            and valid_job is not None
            and str(valid_job.get("id") or "") == str(item["code"])
        )
        attempts.append(
            {
                "sourceId": source["id"],
                "url": item["sourceUrl"],
                "status": api_status,
                "ok": detail_ok,
                "kind": "detail-api",
                **({} if detail_ok else {"reason": "invalid-widget-detail-response"}),
            }
        )
        if not detail_ok:
            complete = False
            continue
        parsed = parse_lmc_graphql_detail(body, item["sourceUrl"], str(item["code"]))
        if parsed is None:
            quarantined.append(
                {
                    "sourceId": source["id"],
                    "sourceUrl": item["sourceUrl"],
                    "title": item["title"],
                    "reason": "detail-not-a-supported-research-vacancy",
                }
            )
            continue
        candidates.append(parsed)
    return {
        "candidates": candidates,
        "attempts": attempts,
        "quarantined": quarantined,
        "complete": complete,
    }


def parse_czu_ajax_listing(payload_text: str, page_url: str) -> tuple[list[dict], int] | None:
    """Parse one public WP Job Manager result page and its page count."""
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    found_jobs = payload.get("found_jobs")
    max_pages = payload.get("max_num_pages")
    fragment = payload.get("html")
    if not isinstance(found_jobs, bool) or not isinstance(max_pages, int) or not isinstance(fragment, str):
        return None
    if max_pages < 0 or (found_jobs and max_pages < 1):
        return None

    starts: list[tuple[int, str]] = []
    listing_matches = list(
        re.finditer(
            r"(?is)<li\b[^>]*class=[\"']([^\"']*\bjob_listing\b[^\"']*)[\"'][^>]*>",
            fragment,
        )
    )
    if found_jobs != bool(listing_matches):
        return None
    for match in listing_matches:
        classes = match.group(1)
        code = re.search(r"\bpost-(\d+)\b", classes)
        if code is None:
            return None
        # WP Job Manager can return expired rows in the same otherwise valid
        # result fragment. They are useful for validating the response shape,
        # but are deliberately excluded from the active vacancy inventory.
        if re.search(r"(?:^|\s)status-expired(?:\s|$)", classes):
            continue
        starts.append((match.start(), code.group(1)))
    results: list[dict] = []
    seen: set[str] = set()
    public_host = urlsplit(page_url).netloc.casefold()
    for index, (start, code) in enumerate(starts):
        if code in seen:
            return None
        block = fragment[start : starts[index + 1][0] if index + 1 < len(starts) else len(fragment)]
        link = re.search(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>", block)
        heading = re.search(r"(?is)<h3\b[^>]*>(.*?)</h3>", block)
        if not link or not heading:
            return None
        source_url = urljoin(page_url, unescape(link.group(1)).strip())
        parsed_url = urlsplit(source_url)
        title = visible_text(heading.group(1))
        if (
            parsed_url.scheme not in {"http", "https"}
            or parsed_url.netloc.casefold() != public_host
            or not parsed_url.path.startswith("/job/")
            or not title
        ):
            return None
        seen.add(code)
        results.append(
            {
                "code": code,
                "title": title,
                "sourceUrl": source_url,
                "applicationUrl": source_url,
            }
        )
    if not found_jobs and max_pages != 0:
        return None
    return results, max_pages


def parse_czu_rest_listing(payload_text: str, api_url: str) -> list[dict] | None:
    """Read full vacancy bodies returned by CZU's public WordPress REST API."""
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    api_host = urlsplit(api_url).netloc.casefold()
    results: list[dict] = []
    seen: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            return None
        code = str(row.get("id") or "")
        title_value = row.get("title")
        content_value = row.get("content")
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        title_html = title_value.get("rendered") if isinstance(title_value, dict) else None
        content_html = content_value.get("rendered") if isinstance(content_value, dict) else None
        source_url = row.get("link")
        title = visible_text(title_html) if isinstance(title_html, str) else ""
        parsed_url = urlsplit(source_url) if isinstance(source_url, str) else None
        if (
            not code.isdigit()
            or code in seen
            or row.get("status") != "publish"
            or row.get("type") != "job_listing"
            or not title
            or not isinstance(content_html, str)
            or len(visible_text(content_html)) < 20
            or parsed_url is None
            or parsed_url.scheme not in {"http", "https"}
            or parsed_url.netloc.casefold() != api_host
            or not parsed_url.path.startswith("/job/")
        ):
            return None
        published = str(row.get("date") or "")[:10]
        if published and parse_date(published) is None:
            return None
        seen.add(code)
        results.append(
            {
                "code": code,
                "title": title,
                "sourceUrl": source_url,
                "applicationUrl": source_url,
                "noticePostedAt": published or None,
                "filled": meta.get("_filled") in {1, "1", True},
                "_factHtml": f"<h1>{escape(title)}</h1>{content_html}",
            }
        )
    return results


def _url_with_query(url: str, values: dict[str, object]) -> str:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in values.items():
        query[key] = [str(value)]
    return parsed._replace(query=urlencode(query, doseq=True)).geturl()


def discover_czu_wp_job_manager_source(source: dict, fetch_page) -> dict:
    """Cross-check CZU's public result pages against full REST vacancy bodies."""
    attempts: list[dict] = []
    quarantined: list[dict] = []
    complete = True
    portal_url = source["url"]
    status, landing_html = fetch_page(portal_url)
    landing_ok = (
        page_ok(status, landing_html)
        and "wp-job-manager" in landing_html
        and "job_listings" in landing_html
        and "jm-ajax/%%endpoint%%" in landing_html
    )
    attempts.append(
        {
            "sourceId": source["id"],
            "url": portal_url,
            "status": status,
            "ok": landing_ok,
            "kind": "listing-portal",
            **({} if landing_ok else {"reason": "missing-public-job-manager-listing"}),
        }
    )
    if not landing_ok:
        return {"candidates": [], "attempts": attempts, "quarantined": quarantined, "complete": False}

    per_page = max(1, min(int(source.get("perPage") or 100), 100))
    max_pages_limit = max(1, min(int(source.get("maxPages") or 20), 20))
    public_endpoint = str(source.get("publicListUrl") or urljoin(portal_url, "/jm-ajax/get_listings/"))
    public_rows: list[dict] = []
    expected_pages: int | None = None
    page = 1
    while expected_pages is None or page <= expected_pages:
        if page > max_pages_limit:
            complete = False
            attempts.append(
                {
                    "sourceId": source["id"],
                    "url": public_endpoint,
                    "status": None,
                    "ok": False,
                    "kind": "listing-public-api",
                    "reason": "pagination-limit-exceeded",
                }
            )
            break
        page_url = _url_with_query(
            public_endpoint,
            {
                "lang": "cs",
                "per_page": per_page,
                "orderby": "featured",
                "featured_first": "false",
                "order": "DESC",
                "page": page,
                "show_pagination": "false",
            },
        )
        page_status, body = fetch_page(page_url)
        parsed_page = parse_czu_ajax_listing(body, page_url) if page_status == 200 else None
        page_okay = parsed_page is not None
        attempts.append(
            {
                "sourceId": source["id"],
                "url": page_url,
                "status": page_status,
                "ok": page_okay,
                "kind": "listing-public-api",
                "page": page,
                **({} if page_okay else {"reason": "invalid-public-listing-response"}),
            }
        )
        if not page_okay:
            complete = False
            break
        rows, page_count = parsed_page
        if expected_pages is None:
            expected_pages = page_count
        elif page_count != expected_pages:
            attempts[-1]["ok"] = False
            attempts[-1]["reason"] = "inconsistent-public-page-count"
            complete = False
            break
        public_rows.extend(rows)
        if expected_pages == 0:
            break
        page += 1

    public_by_id: dict[str, dict] = {}
    for row in public_rows:
        if row["code"] in public_by_id:
            complete = False
            continue
        public_by_id[row["code"]] = row

    api_url = str(source.get("apiUrl") or urljoin(portal_url, "/wp-json/wp/v2/job-listings"))
    rest_by_id: dict[str, dict] = {}
    public_ids = list(public_by_id)
    for chunk_index in range(0, len(public_ids), 100):
        chunk = public_ids[chunk_index : chunk_index + 100]
        rest_url = _url_with_query(
            api_url,
            {
                "include": ",".join(chunk),
                "per_page": len(chunk),
                "orderby": "include",
                "context": "view",
            },
        )
        rest_status, rest_body = fetch_page(rest_url)
        rest_rows = parse_czu_rest_listing(rest_body, api_url) if rest_status == 200 else None
        ids_match = rest_rows is not None and {row["code"] for row in rest_rows} == set(chunk)
        attempts.append(
            {
                "sourceId": source["id"],
                "url": rest_url,
                "status": rest_status,
                "ok": ids_match,
                "kind": "detail-api",
                "items": len(chunk),
                **({} if ids_match else {"reason": "public-rest-item-mismatch"}),
            }
        )
        if not ids_match:
            complete = False
            continue
        rest_by_id.update({row["code"]: row for row in rest_rows})

    candidates: list[dict] = []
    for code, public_item in public_by_id.items():
        item = rest_by_id.get(code)
        if item is None:
            continue
        if item["title"] != public_item["title"] or item["sourceUrl"] != public_item["sourceUrl"]:
            complete = False
            quarantined.append(
                {
                    "sourceId": source["id"],
                    "sourceUrl": public_item["sourceUrl"],
                    "title": public_item["title"],
                    "reason": "public-rest-detail-mismatch",
                }
            )
            continue
        if item["filled"]:
            complete = False
            quarantined.append(
                {
                    "sourceId": source["id"],
                    "sourceUrl": item["sourceUrl"],
                    "title": item["title"],
                    "reason": "public-list-item-marked-filled",
                }
            )
            continue
        parsed = parse_generic_job_page(item["_factHtml"], item["sourceUrl"], item["title"])
        if parsed is None:
            quarantined.append(
                {
                    "sourceId": source["id"],
                    "sourceUrl": item["sourceUrl"],
                    "title": item["title"],
                    "reason": "detail-not-a-supported-research-vacancy",
                }
            )
            continue
        candidates.append(
            {
                **item,
                **parsed,
                "title": item["title"],
                "sourceUrl": item["sourceUrl"],
                "applicationUrl": item["sourceUrl"],
                "noticePostedAt": item["noticePostedAt"],
                "applicationMethod": "official_instructions",
                "_factHtml": item["_factHtml"],
            }
        )
    return {
        "candidates": candidates,
        "attempts": attempts,
        "quarantined": quarantined,
        "complete": complete,
    }


def parse_generic_job_page(html: str, page_url: str, title_hint: str = "") -> dict | None:
    text = visible_text(html)
    title = title_hint.strip()
    if not title:
        heading = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
        title = visible_text(heading.group(1)) if heading else ""
    if not title:
        return None
    scoped_text = entity_scope(text, title)
    # A69: read the whole scoped vacancy body. A fixed character prefix hides
    # qualification, funding and salary facts that appear further down the page.
    track = classify_track(title, scoped_text)
    if not track:
        return None
    deadline = extract_deadline(scoped_text)
    published = None
    for label in ("published", "announced", "date of publication", "zveřejněno", "zverejneno"):
        match = re.search(label + r".{0,80}", scoped_text, re.I)
        if match:
            published = parse_date(match.group(0))
            if published:
                break
    salary_facts = extract_salary_facts(scoped_text)
    paid = salary_facts["paidStatus"]
    if paid != "confirmed":
        if re.search(
            r"\b(salary|wage|employment contract|fixed[- ]term contract|contract of employment|"
            r"full-time employment|full-time position|gross|"
            r"pracovn[ií]\s+smlouva|pracovn[ií]\s+[úu]vazek|pracovn[ií]\s+pom[eě]r|pracovn[eě]pr[aá]vn[ií](?:ho| vztah)|mzda|mzdov\w*|"
            r"plat(?:ov[eéý]\s+(?:ohodnocen[ií]|podm[ií]nk[ay]))?|finan[cč]n[ií]\s+ohodnocen[ií])\b",
            scoped_text,
            re.I,
        ):
            paid = "confirmed"
        else:
            soft_paid = funding_supported_status(scoped_text)
            if soft_paid:
                paid = soft_paid
    degrees = classify_degrees(track, title, scoped_text)
    return {
        "title": WS.sub(" ", title).strip(),
        "sourceLanguage": detect_source_language(scoped_text),
        "track": track,
        "closesAt": iso_date(deadline),
        "opensAt": iso_date(published),
        "sourceUrl": page_url,
        "paidStatus": paid,
        "salaryAmount": salary_facts["amount"],
        "salaryCurrency": salary_facts["currency"],
        "salaryCycle": salary_facts["cycle"],
        "salaryTax": salary_facts["tax"],
        "salaryAmountMin": salary_facts["amountMin"],
        "salaryAmountMax": salary_facts["amountMax"],
        "salaryExtraction": salary_facts["reason"],
        "basisFte": salary_facts["basisFte"],
        # A85: multiple far-apart salary statements mean a multi-role notice;
        # job_record keeps degree/enrollment unknown for such bundles.
        "eligibilityGranularity": (
            "notice_bundle" if salary_facts.get("reason") == "multiple-salary-statements" else None
        ),
        "fundingType": extract_funding_type(scoped_text) or "unknown",
        "employmentFte": extract_employment_fte(scoped_text),
        "employmentStartsAt": iso_date(extract_employment_start(scoped_text)),
        **degrees,
    }


def parse_muni_vacancies(html: str, base_url: str = "https://www.muni.cz") -> list[dict]:
    results = []
    link_pattern = re.compile(r"""<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)
    seen: set[str] = set()
    for match in link_pattern.finditer(html):
        href, anchor_html = match.group(1), match.group(2)
        absolute = urljoin(base_url, href)
        path = urlsplit(absolute).path
        vacancy_path = re.search(
            r"/(?:en/about-us/careers/vacancies|o-univerzite/kariera/volna-mista|kariera/volna-mista)/(\d+)(?:[-/]|$)",
            path,
            re.I,
        )
        if not vacancy_path or absolute in seen:
            continue
        seen.add(absolute)
        code = vacancy_path.group(1)
        title = visible_text(anchor_html)
        if not title or len(title) < 5:
            continue
        track = classify_track(title)
        if not track:
            continue
        results.append(
            {
                "code": code,
                "title": title,
                "track": track,
                "sourceUrl": absolute,
                "applicationUrl": absolute,
                "employerId": "msmt-vs_14000",
            }
        )
    return results


def parse_generic_listing_links(
    html: str,
    page_url: str,
    path_patterns: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
) -> list[dict]:
    """Extract configured vacancy detail links without treating nav links as jobs."""
    patterns = [re.compile(value, re.I) for value in (path_patterns or [])]
    current_host = urlsplit(page_url).netloc.casefold()
    permitted_hosts = {current_host, *(host.casefold() for host in (allowed_hosts or []))}
    results: list[dict] = []
    seen: set[str] = set()
    for match in re.finditer(
        r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html
    ):
        href = unescape(match.group(1)).strip()
        absolute = urljoin(page_url, href)
        parsed = urlsplit(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.casefold() not in permitted_hosts:
            continue
        if patterns and not any(pattern.search(absolute) for pattern in patterns):
            continue
        title = visible_text(match.group(2))
        if not title or absolute in seen:
            continue
        if not patterns and classify_track(title) is None:
            continue
        seen.add(absolute)
        code_match = re.search(
            r"(?:/|[?&](?:id|procedureId|inzeratid)=)(\d{2,})(?:[-/?&#]|$)",
            absolute,
            re.I,
        )
        # Dated PDF directories and filenames are publication metadata, not
        # vacancy identifiers. A URL-and-title hash keeps PDF notices distinct.
        code = None if parsed.path.lower().endswith(".pdf") else (code_match.group(1) if code_match else None)
        results.append(
            {
                "title": title,
                "code": code,
                "sourceUrl": absolute,
                "applicationUrl": absolute,
            }
        )
    return results


def parse_ujep_open_positions(html: str, page_url: str) -> list[dict]:
    """Read only links inside UJEP's English open-position article."""
    article = extract_html_element(html, "article", element_id="post")
    if not article:
        return []
    parsed = urlsplit(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    rows = parse_generic_listing_links(
        article,
        page_url,
        [rf"^{re.escape(origin)}/[^/?#]+/$"],
    )
    return [item for item in rows if item["sourceUrl"] != page_url]


class _TulCareerListParser(HTMLParser):
    """Extract top-level TUL vacancy notices and ignore completed decisions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_root = False
        self.ul_depth = 0
        self.li_depth = 0
        self.strong_depth = 0
        self.current: dict | None = None
        self.anchor: dict | None = None
        self.rows: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if not self.in_root:
            if tag == "ul" and "ridkyseznam" in attr_map.get("class", "").split():
                self.in_root = True
                self.ul_depth = 1
            return
        if tag == "ul":
            self.ul_depth += 1
        elif tag == "li":
            self.li_depth += 1
            if self.ul_depth == 1 and self.li_depth == 1:
                self.current = {"links": []}
        elif tag == "strong" and self.current is not None:
            self.strong_depth += 1
        elif tag == "a" and self.current is not None:
            self.anchor = {
                "href": attr_map.get("href", ""),
                "text": [],
                "primary": self.strong_depth > 0 and self.ul_depth == 1,
            }

    def handle_data(self, data: str) -> None:
        if self.anchor is not None:
            self.anchor["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_root:
            return
        if tag == "a" and self.anchor is not None:
            if self.current is not None:
                self.current["links"].append(
                    {
                        **self.anchor,
                        "text": WS.sub(" ", "".join(self.anchor["text"])).strip(),
                    }
                )
            self.anchor = None
        elif tag == "strong" and self.current is not None:
            self.strong_depth = max(0, self.strong_depth - 1)
        elif tag == "li":
            if self.li_depth == 1 and self.current is not None:
                self.rows.append(self.current)
                self.current = None
                self.strong_depth = 0
                self.anchor = None
            self.li_depth = max(0, self.li_depth - 1)
        elif tag == "ul":
            self.ul_depth -= 1
            if self.ul_depth == 0:
                self.in_root = False


def parse_tul_careers(html: str, page_url: str) -> list[dict]:
    """Read unresolved TUL notices; a linked decision is authoritative closure evidence."""
    parser = _TulCareerListParser()
    parser.feed(html)
    results: list[dict] = []
    seen: set[str] = set()
    for row in parser.rows:
        links = row.get("links") or []
        if any(str(link.get("text") or "").casefold().startswith("rozhodnutí") for link in links):
            continue
        primary = next((link for link in links if link.get("primary")), None)
        if not primary:
            continue
        source_url = urljoin(page_url, str(primary.get("href") or ""))
        parsed = urlsplit(source_url)
        code_match = re.fullmatch(r"/(\d+)", parsed.path)
        title = str(primary.get("text") or "").strip()
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.netloc.casefold() != "doc.tul.cz"
            or not code_match
            or not title
            or source_url in seen
        ):
            continue
        seen.add(source_url)
        results.append(
            {
                "title": title,
                "code": code_match.group(1),
                "sourceUrl": source_url,
                "applicationUrl": source_url,
            }
        )
    return results


def parse_utb_careers(html: str, page_url: str) -> list[dict]:
    """Pair each UTB vacancy-card heading with its same-card detail URL."""
    current_host = urlsplit(page_url).netloc.casefold()
    results: list[dict] = []
    seen: set[str] = set()
    for article in re.finditer(r"(?is)<article\b[^>]*>(.*?)</article>", html):
        block = article.group(1)
        heading = re.search(r"(?is)<h5\b[^>]*>(.*?)</h5>", block)
        links = re.finditer(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>", block)
        if heading is None:
            continue
        title = visible_text(heading.group(1))
        source_url = None
        for link in links:
            candidate = urljoin(page_url, unescape(link.group(1)).strip())
            parsed = urlsplit(candidate)
            if parsed.scheme in {"http", "https"} and parsed.netloc.casefold() == current_host:
                source_url = candidate
                break
        if not title or source_url is None or source_url in seen:
            continue
        seen.add(source_url)
        results.append(
            {
                "title": title,
                "code": None,
                "sourceUrl": source_url,
                "applicationUrl": source_url,
            }
        )
    return results


def parse_recruitis_widget_urls(html: str, page_url: str) -> list[str]:
    """Read Recruitis offer widgets explicitly embedded by an official page."""
    results: list[str] = []
    for match in re.finditer(r"(?is)<iframe\b[^>]*src=[\"']([^\"']+)[\"'][^>]*>", html):
        candidate = urljoin(page_url, unescape(match.group(1)).strip())
        parsed = urlsplit(candidate)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.netloc.casefold() == "app.recruitis.io"
            and parsed.path.startswith("/zadavatel/widgets/offers/")
            and candidate not in results
        ):
            results.append(candidate)
    return results


def _table_cells(row_html: str) -> list[str]:
    return re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html)


def parse_ctu_notice_listing(html: str, page_url: str) -> list[dict]:
    """Parse personnel rows from the official CTU electronic notice board."""
    results: list[dict] = []
    seen: set[str] = set()
    for match in re.finditer(r"(?is)<tr\b[^>]*>(.*?)</tr>", html):
        cells = _table_cells(match.group(1))
        if len(cells) != 6 or visible_text(cells[1]).casefold() != "personální".casefold():
            continue
        link = re.search(
            r"(?is)<a\b[^>]*href=[\"']([^\"']*/pub/deska/36000002/ifis/\d+[^\"']*)[\"'][^>]*>(.*?)</a>",
            cells[2],
        )
        if not link:
            continue
        linked_url = urlsplit(urljoin(page_url, unescape(link.group(1)).strip()))
        source_url = urlunsplit((linked_url.scheme, linked_url.netloc, linked_url.path, "", ""))
        code_match = re.search(r"/ifis/(\d+)(?:[/?#]|$)", source_url)
        title = visible_text(link.group(2))
        if not code_match or not title or source_url in seen:
            continue
        seen.add(source_url)
        results.append(
            {
                "code": code_match.group(1),
                "title": title,
                "laboratory": visible_text(cells[0]) or None,
                "caseNumber": visible_text(cells[3]) or None,
                "noticePostedAt": iso_date(parse_date(visible_text(cells[4]))),
                "noticeRemoveAt": iso_date(parse_date(visible_text(cells[5]))),
                "sourceUrl": source_url,
                "applicationUrl": source_url,
            }
        )
    return results


def _ctu_notice_total(html: str) -> int | None:
    totals = [
        int(match.group(1))
        for match in re.finditer(r">\s*\d+\s*-\s*\d+\s+z\s+(\d+)\s*<", html, re.I)
    ]
    return max(totals) if totals else None


def _ctu_notice_pagination_urls(html: str, current_url: str) -> list[str]:
    current = urlsplit(current_url)
    offsets: set[int] = set()
    for match in re.finditer(r"(?is)\bhref=[\"']([^\"']+)[\"']", html):
        href = unescape(match.group(1)).strip()
        if not re.search(r"(?:[?&])pozice=\d+", href):
            continue
        absolute = urljoin(current_url, href)
        parsed = urlsplit(absolute)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.netloc.casefold() != current.netloc.casefold()
            or parsed.path != current.path
        ):
            continue
        values = parse_qs(parsed.query).get("pozice") or []
        if values and values[0].isdigit() and int(values[0]) > 0:
            offsets.add(int(values[0]))
    base_query = parse_qs(current.query)
    results: list[str] = []
    for offset in sorted(offsets):
        query = {**base_query, "pozice": [str(offset)]}
        results.append(
            urlunsplit(
                (
                    current.scheme,
                    current.netloc,
                    current.path,
                    urlencode(query, doseq=True),
                    "",
                )
            )
        )
    return results


def parse_ctu_notice_detail(html: str, page_url: str) -> dict | None:
    """Read notice metadata and official attachment links from one CTU detail."""
    pairs: dict[str, str] = {}
    for match in re.finditer(r"(?is)<tr\b[^>]*>(.*?)</tr>", html):
        cells = _table_cells(match.group(1))
        if len(cells) != 2:
            continue
        key = visible_text(cells[0]).strip().casefold()
        value = visible_text(cells[1]).strip()
        if key and value:
            pairs[key] = value
    attachments: list[str] = []
    for match in re.finditer(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"']", html):
        href = unescape(match.group(1)).strip()
        if not re.search(r"\.pdf(?:[?#]|$)", href, re.I):
            continue
        absolute = urljoin(page_url, href)
        if absolute not in attachments:
            attachments.append(absolute)
    title = pairs.get("název")
    category = pairs.get("kategorie")
    if not title or not category or category.casefold() != "personální".casefold():
        return None
    return {
        "title": title,
        "laboratory": pairs.get("součást"),
        "caseNumber": pairs.get("číslo jednací"),
        "noticePostedAt": iso_date(parse_date(pairs.get("vyvěšeno"))),
        "noticeRemoveAt": iso_date(parse_date(pairs.get("sejmout"))),
        "noticeStatus": pairs.get("stav vyvěšení"),
        "attachmentUrls": attachments,
    }


def discover_ctu_notice_board_source(
    source: dict,
    fetch_page,
    fetch_binary,
    pdf_text=None,
) -> dict:
    """Discover CTU vacancies only after reading every official PDF attachment."""
    pdf_text_fn = pdf_text or extract_pdf_text
    attempts: list[dict] = []
    quarantined: list[dict] = []
    listing_rows: list[dict] = []
    queue = [source["url"]]
    visited: set[str] = set()
    expected_total: int | None = None
    complete = True
    max_pages = int(source.get("maxPages") or 10)
    while queue and len(visited) < max_pages:
        listing_url = queue.pop(0)
        if listing_url in visited:
            continue
        visited.add(listing_url)
        status, html = fetch_page(listing_url)
        ok = page_ok(status, html)
        attempts.append(
            {
                "sourceId": source["id"],
                "url": listing_url,
                "status": status,
                "ok": ok,
                "kind": "listing",
            }
        )
        if not ok:
            complete = False
            continue
        page_total = _ctu_notice_total(html)
        if page_total is None:
            complete = False
            attempts[-1]["ok"] = False
            attempts[-1]["reason"] = "missing-listing-total"
        elif expected_total is None:
            expected_total = page_total
        elif expected_total != page_total:
            complete = False
            attempts[-1]["ok"] = False
            attempts[-1]["reason"] = "inconsistent-listing-total"
        listing_rows.extend(parse_ctu_notice_listing(html, listing_url))
        for next_url in _ctu_notice_pagination_urls(html, listing_url):
            if next_url not in visited and next_url not in queue:
                queue.append(next_url)
    if queue:
        complete = False
        attempts.append(
            {
                "sourceId": source["id"],
                "url": source["url"],
                "status": None,
                "ok": False,
                "kind": "listing",
                "reason": "pagination-limit-exceeded",
            }
        )
    unique_rows = {str(item["code"]): item for item in listing_rows}
    if expected_total is None or len(unique_rows) != expected_total:
        complete = False
        attempts.append(
            {
                "sourceId": source["id"],
                "url": source["url"],
                "status": 200,
                "ok": False,
                "kind": "listing",
                "reason": f"listing-count-mismatch:{len(unique_rows)}/{expected_total}",
            }
        )

    candidates: list[dict] = []
    for item in unique_rows.values():
        detail_status, detail_html = fetch_page(item["sourceUrl"])
        metadata = parse_ctu_notice_detail(detail_html, item["sourceUrl"]) if page_ok(detail_status, detail_html) else None
        detail_ok = (
            metadata is not None
            and metadata.get("title") == item["title"]
            and bool(metadata.get("attachmentUrls"))
        )
        attempts.append(
            {
                "sourceId": source["id"],
                "url": item["sourceUrl"],
                "status": detail_status,
                "ok": detail_ok,
                "kind": "detail",
                **({} if detail_ok else {"reason": "invalid-notice-detail"}),
            }
        )
        if not detail_ok:
            complete = False
            continue
        attachment_texts: list[str] = []
        for attachment_url in metadata["attachmentUrls"]:
            attachment_status, attachment_body = fetch_binary(attachment_url)
            text = pdf_text_fn(attachment_body) if attachment_status == 200 else ""
            attachment_ok = attachment_status == 200 and len(text.strip()) >= 20
            attempts.append(
                {
                    "sourceId": source["id"],
                    "url": attachment_url,
                    "status": attachment_status,
                    "ok": attachment_ok,
                    "kind": "detail-attachment",
                    **({} if attachment_ok else {"reason": "pdf-text-extraction-failed"}),
                }
            )
            if not attachment_ok:
                complete = False
                continue
            attachment_texts.append(text)
        if not attachment_texts:
            continue
        fact_text = "\n".join(attachment_texts)
        fact_html = f"<h1>{escape(item['title'])}</h1><p>{escape(fact_text)}</p>"
        parsed = parse_generic_job_page(fact_html, item["sourceUrl"], item["title"])
        if parsed is None:
            quarantined.append(
                {
                    "sourceId": source["id"],
                    "sourceUrl": item["sourceUrl"],
                    "title": item["title"],
                    "reason": "attachment-not-a-supported-research-vacancy",
                }
            )
            continue
        multi_position = bool(
            re.search(
                r"\b(?:positions|pozice\s+akademick[ýy]ch\s+pracovn[ií]k[ůu]|vedouc[ií]\s+kateder)\b",
                item["title"],
                re.I,
            )
        )
        if multi_position:
            # One notice may contain several roles with different thresholds.
            # Keep it discoverable as an official bundle, but do not collapse
            # mixed qualifications into one applicant-eligibility claim.
            parsed["minimumDegree"] = "unknown"
            parsed["doctorateRequired"] = None
            parsed["doctoralEnrollment"] = "unspecified"
        candidates.append(
            {
                **item,
                **parsed,
                "title": item["title"],
                "laboratory": metadata.get("laboratory") or item.get("laboratory"),
                "caseNumber": metadata.get("caseNumber") or item.get("caseNumber"),
                "noticePostedAt": metadata.get("noticePostedAt") or item.get("noticePostedAt"),
                "noticeRemoveAt": metadata.get("noticeRemoveAt") or item.get("noticeRemoveAt"),
                "applicationUrl": item["sourceUrl"],
                "applicationMethod": "official_instructions",
                "eligibilityGranularity": "notice_bundle" if multi_position else "vacancy",
                "_factHtml": fact_html,
            }
        )
    return {
        "candidates": candidates,
        "attempts": attempts,
        "quarantined": quarantined,
        "complete": complete,
    }


def parse_vsb_listing(html: str, page_url: str) -> list[dict]:
    """Parse active VŠB-TUO vacancy cards and exclude the completed section."""
    active_html = re.split(r"Výsledky\s+ukončených\s+výběrových\s+řízení", html, maxsplit=1, flags=re.I)[0]
    starts = [
        match.start()
        for match in re.finditer(
            r"(?is)<div\b[^>]*class=[\"'][^\"']*(?<!-)\bcard\b(?!-)[^\"']*[\"'][^>]*>",
            active_html,
        )
    ]
    results: list[dict] = []
    for index, start in enumerate(starts):
        fragment = active_html[start : starts[index + 1] if index + 1 < len(starts) else len(active_html)]
        heading = re.search(
            r"(?is)<h4\b[^>]*class=[\"'][^\"']*\bcard-title\b[^\"']*[\"'][^>]*>(.*?)</h4>",
            fragment,
        )
        detail = re.search(
            r"(?is)<a\b[^>]*href=[\"']([^\"']*(?:procedureId=|pracovni-prilezitosti/inzerat)[^\"']*)[\"'][^>]*>",
            fragment,
        )
        if not heading or not detail:
            continue
        title = visible_text(heading.group(1))
        card_text = visible_text(fragment)
        # The official page labels academic posts explicitly.  Detail parsing
        # still decides whether the duties are research-related and whether a
        # master's graduate can apply.
        if not re.search(r"akademick[aá]\s+pozice", card_text, re.I) and classify_track(title, card_text) is None:
            continue
        absolute = urljoin(page_url, unescape(detail.group(1)))
        query_code = parse_qs(urlsplit(absolute).query).get("procedureId", [None])[0]
        subtitle = re.search(
            r"(?is)<h5\b[^>]*class=[\"'][^\"']*\bcard-subtitle\b[^\"']*[\"'][^>]*>(.*?)</h5>",
            fragment,
        )
        results.append(
            {
                "title": title,
                "code": query_code,
                "laboratory": visible_text(subtitle.group(1)) if subtitle else None,
                "closesAt": iso_date(extract_deadline(card_text)),
                "sourceUrl": absolute,
                "applicationUrl": absolute,
            }
        )
    return results


def parse_inline_heading_jobs(html: str, page_url: str) -> list[dict]:
    """Parse official pages where multiple complete vacancies are inline."""
    headings = list(re.finditer(r"(?is)<h2\b[^>]*>(.*?)</h2>", html))
    results: list[dict] = []
    for index, heading in enumerate(headings):
        title = visible_text(heading.group(1))
        if not title:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(html)
        next_intro = re.search(r"(?is)<h3\b", html[heading.end() : end])
        if next_intro:
            end = heading.end() + next_intro.start()
        fragment = html[heading.start() : end]
        parsed = parse_generic_job_page(fragment, page_url, title)
        if parsed is None:
            continue
        code_match = re.search(r"(?:[-–—]\s*|\()(\d{3,})\)?\s*$", title)
        parsed["code"] = code_match.group(1) if code_match else None
        parsed["applicationUrl"] = page_url
        parsed["applicationMethod"] = "official_instructions"
        parsed["_factText"] = visible_text(fragment)
        results.append(parsed)
    return results


def _pagination_urls(html: str, current_url: str) -> list[str]:
    current = urlsplit(current_url)
    results: list[str] = []
    for match in re.finditer(r"(?is)<a\b([^>]*)href=[\"']([^\"']+)[\"']([^>]*)>(.*?)</a>", html):
        attrs = f"{match.group(1)} {match.group(3)}".lower()
        href = unescape(match.group(2)).strip()
        label = visible_text(match.group(4)).lower()
        if not (
            re.search(r"\brel\s*=\s*[\"']?next\b", attrs)
            or re.search(r"\bclass\s*=\s*[\"'][^\"']*\b(?:next|pagination|pager)\b", attrs)
            or re.search(r"(?:[?&](?:page|p)=\d+)", href, re.I)
            or label in {"next", "next ›", "další", "dalsi", ">", "›"}
        ):
            continue
        absolute = urljoin(current_url, href)
        parsed = urlsplit(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.casefold() != current.netloc.casefold():
            continue
        if absolute not in results:
            results.append(absolute)
    return results


def detect_source_language(text: str) -> str:
    lowered = text.lower()
    czech_markers = (
        "výzkumn",
        "vyzkumn",
        "přihláš",
        "prihlas",
        "požadujeme",
        "pozadujeme",
        "pracovní poměr",
        "pracovni pomer",
        "termín",
        "termin",
        "doktorské studium",
        "doktorske studium",
    )
    return "cs" if any(marker in lowered for marker in czech_markers) else "en"


def parse_avcr_vacancies(html: str, base_url: str = "https://www.avcr.cz") -> list[dict]:
    results = []
    link_pattern = re.compile(
        r"""href=["'](/en/about-us/career/selection-procedures/[^"']+)["'][^>]*>(.*?)</a>""",
        re.I | re.S,
    )
    for match in link_pattern.finditer(html):
        path, anchor_html = match.group(1), match.group(2)
        title = visible_text(anchor_html)
        if not title or len(title) < 5:
            continue
        track = classify_track(title)
        if not track:
            continue
        results.append(
            {
                "title": title,
                "track": track,
                "sourceUrl": f"{base_url.rstrip('/')}{path}",
                "applicationUrl": f"{base_url.rstrip('/')}{path}",
                # The Academy portal is an index, not the legal employer.  A
                # later registry mapping must resolve the actual institute.
                "employerId": None,
                "employerIdentityStatus": "unresolved",
            }
        )
    return results


def parse_zcu_document_feed(payload: str) -> list[dict]:
    """Read the same recursive public document tree used by ZCU's career page."""
    root = json.loads(payload)
    found = []
    seen = set()
    def visit(folder):
        if not isinstance(folder, dict) or not isinstance(folder.get("documents"), list) or not isinstance(folder.get("folders"), list):
            raise ValueError("Incomplete ZCU document folder")
        for item in folder["documents"]:
            ident = str(item.get("cmisId") or "")
            title = item.get("title") or item.get("nameNice")
            if not ident or not title or item.get("mimeType", {}).get("subtype") != "pdf":
                raise ValueError("Unsupported ZCU vacancy document")
            if ident not in seen:
                seen.add(ident)
                found.append({"title": title, "code": ident.split(";")[0],
                              "sourceUrl": "https://xdoc.zcu.cz/api/alfresco?id=" + ident + "&download=0"})
        for child in folder["folders"]:
            visit(child)
    visit(root)
    return found


def load_registered_job_sources(path: Path = SOURCE_REGISTRY) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [
        item
        for item in payload
        if isinstance(item, dict)
        and item.get("sourceType") in JOB_LISTING_SOURCE_TYPES
        and item.get("enabled", True) is not False
        and isinstance(item.get("url"), str)
        and isinstance(item.get("parser"), str)
    ]


def _stable_discovered_id(item: dict) -> str:
    employer_id = str(item["employerId"])
    code = re.sub(r"[^a-z0-9]+", "-", str(item.get("code") or "").lower()).strip("-")
    if code:
        return f"job-{employer_id.removeprefix('msmt-vs_')}-{code}"
    return slug_id(employer_id, str(item["title"]), str(item["sourceUrl"]))


def _merge_seed_and_discovered(seeds: list[dict], discovered: list[dict]) -> list[dict]:
    """Preserve reviewed stable IDs while allowing newly listed jobs through."""
    merged = [dict(item) for item in seeds]
    for candidate in discovered:
        match_index = None
        for index, existing in enumerate(merged):
            same_employer = existing.get("employerId") == candidate.get("employerId")
            same_code = candidate.get("code") and existing.get("code") == candidate.get("code")
            same_url = existing.get("sourceUrl") == candidate.get("sourceUrl")
            if same_employer and (same_code or same_url):
                match_index = index
                break
        if match_index is None:
            merged.append(candidate)
        else:
            stable_id = merged[match_index]["id"]
            merged[match_index] = {**merged[match_index], **candidate, "id": stable_id}
    return merged


def discover_registered_candidates(
    fetch_page,
    employer_ids: set[str] | None = None,
    registry: list[dict] | None = None,
    post_json=None,
    fetch_attachment=None,
    pdf_text=None,
    now: datetime | None = None,
) -> dict:
    """Discover current vacancies through the production source registry.

    Linked detail pages are parsed before becoming source candidates.  Entries
    whose legal employer cannot be resolved are quarantined and never flow into
    the catalogue candidate file.
    """
    sources = registry if registry is not None else load_registered_job_sources()
    selected = set(employer_ids) if employer_ids is not None else None
    candidates: list[dict] = []
    attempts: list[dict] = []
    quarantined: list[dict] = []
    complete_source_ids: list[str] = []
    deferred_source_ids: list[str] = []
    expected_source_ids: list[str] = []
    post_json_fn = post_json or request_json
    fetch_attachment_fn = fetch_attachment or request_binary
    pdf_text_fn = pdf_text or extract_pdf_text

    for source in sources:
        source_employer = source.get("employerId")
        if selected is not None and source_employer not in selected:
            continue
        expected_source_ids.append(source["id"])
        cooldown = host_cooldown_until(str(source.get("url") or ""), now)
        if cooldown is not None:
            deferred_source_ids.append(source["id"])
            attempts.append(
                {
                    "sourceId": source["id"],
                    "url": source.get("url"),
                    "status": 429,
                    "ok": False,
                    "kind": "listing",
                    "reason": "retry-after-deferred",
                    "retryAt": cooldown.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
            continue
        parser = source["parser"]
        if parser not in {
            "mff_listing",
            "cuni_ajax",
            "muni_vacancies",
            "avcr_vacancies",
            "generic_listing_links",
            "vsb_listing",
            "inline_heading_jobs",
            "lmc_graphql",
            "ctu_notice_board",
            "czu_wp_job_manager",
            "utb_careers",
            "recruitis_widget",
            "ujep_open_positions",
            "tul_careers",
            "zcu_document_feed",
        }:
            attempts.append(
                {
                    "sourceId": source["id"],
                    "url": source["url"],
                    "status": None,
                    "ok": False,
                    "kind": "listing",
                    "reason": f"unsupported-parser:{parser}",
                }
            )
            continue

        found: list[dict] = []
        source_complete = True
        if parser == "zcu_document_feed":
            status, payload = fetch_page(source["url"])
            try:
                if status != 200:
                    raise ValueError(f"HTTP {status}")
                found.extend(parse_zcu_document_feed(payload))
            except (ValueError, TypeError, KeyError) as exc:
                source_complete = False
                attempts.append({"sourceId": source["id"], "url": source["url"], "status": status,
                                 "ok": False, "kind": "listing", "reason": str(exc)})
            else:
                attempts.append({"sourceId": source["id"], "url": source["url"], "status": status,
                                 "ok": True, "kind": "listing"})
        elif parser == "lmc_graphql":
            lmc_result = discover_lmc_graphql_source(source, fetch_page, post_json_fn)
            found.extend(lmc_result["candidates"])
            attempts.extend(lmc_result["attempts"])
            quarantined.extend(lmc_result["quarantined"])
            source_complete = bool(lmc_result["complete"])
        elif parser == "ctu_notice_board":
            ctu_result = discover_ctu_notice_board_source(
                source,
                fetch_page,
                fetch_attachment_fn,
                pdf_text,
            )
            found.extend(ctu_result["candidates"])
            attempts.extend(ctu_result["attempts"])
            quarantined.extend(ctu_result["quarantined"])
            source_complete = bool(ctu_result["complete"])
        elif parser == "czu_wp_job_manager":
            czu_result = discover_czu_wp_job_manager_source(source, fetch_page)
            found.extend(czu_result["candidates"])
            attempts.extend(czu_result["attempts"])
            quarantined.extend(czu_result["quarantined"])
            source_complete = bool(czu_result["complete"])
        else:
            queue = [source["url"], *(source.get("pages") or [])]
            visited: set[str] = set()
            while queue and len(visited) < 20:
                listing_url = urljoin(source["url"], str(queue.pop(0)))
                if listing_url in visited:
                    continue
                visited.add(listing_url)
                status, html = fetch_page(listing_url)
                ok = page_ok(status, html)
                attempts.append({"sourceId": source["id"], "url": listing_url, "status": status, "ok": ok, "kind": "listing"})
                if not ok:
                    source_complete = False
                    continue
                if parser == "mff_listing":
                    found.extend(parse_mff_listing(html, listing_url))
                elif parser == "cuni_ajax":
                    found.extend(
                        parse_cuni_ajax_listing(
                            html,
                            source.get("detailBaseUrl") or "https://cuni.cz/UKEN-1573.html",
                        )
                    )
                elif parser == "muni_vacancies":
                    found.extend(parse_muni_vacancies(html, source.get("baseUrl") or listing_url))
                elif parser == "avcr_vacancies":
                    found.extend(parse_avcr_vacancies(html, source.get("baseUrl") or listing_url))
                elif parser == "generic_listing_links":
                    found.extend(
                        parse_generic_listing_links(
                            html,
                            listing_url,
                            source.get("pathPatterns")
                            if isinstance(source.get("pathPatterns"), list)
                            else None,
                            source.get("allowedHosts")
                            if isinstance(source.get("allowedHosts"), list)
                            else None,
                        )
                    )
                elif parser == "utb_careers":
                    found.extend(parse_utb_careers(html, listing_url))
                elif parser == "recruitis_widget":
                    if listing_url == source["url"]:
                        widget_urls = parse_recruitis_widget_urls(html, listing_url)
                        if not widget_urls:
                            source_complete = False
                            attempts.append(
                                {
                                    "sourceId": source["id"],
                                    "url": listing_url,
                                    "status": status,
                                    "ok": False,
                                    "kind": "widget-config",
                                    "reason": "missing-official-recruitis-widget",
                                }
                            )
                        for widget_url in widget_urls:
                            if widget_url not in visited and widget_url not in queue:
                                queue.append(widget_url)
                        continue
                    found.extend(
                        parse_generic_listing_links(
                            html,
                            listing_url,
                            source.get("pathPatterns")
                            if isinstance(source.get("pathPatterns"), list)
                            else [r"/zadavatel/widgets/offers-detail/"],
                        )
                    )
                elif parser == "ujep_open_positions":
                    found.extend(parse_ujep_open_positions(html, listing_url))
                elif parser == "tul_careers":
                    found.extend(parse_tul_careers(html, listing_url))
                elif parser == "vsb_listing":
                    found.extend(parse_vsb_listing(html, listing_url))
                else:
                    found.extend(parse_inline_heading_jobs(html, listing_url))
                pagination_urls = (
                    _cuni_ajax_pagination_urls(html, listing_url)
                    if parser == "cuni_ajax"
                    else _pagination_urls(html, listing_url)
                )
                for pagination_url in pagination_urls:
                    if pagination_url not in visited and pagination_url not in queue:
                        queue.append(pagination_url)
            if queue:
                source_complete = False
                attempts.append(
                    {
                        "sourceId": source["id"],
                        "url": source["url"],
                        "status": None,
                        "ok": False,
                        "kind": "listing",
                        "reason": "pagination-limit-exceeded",
                    }
                )

        unique_found: list[dict] = []
        seen_found: set[tuple[str, str]] = set()
        for listing_item in found:
            identity = (
                str(listing_item.get("code") or ""),
                str(listing_item.get("sourceUrl") or ""),
            )
            if identity in seen_found:
                continue
            seen_found.add(identity)
            unique_found.append(listing_item)

        for listing_item in unique_found:
            item = {**listing_item}
            item["employerId"] = item.get("employerId") or source_employer
            if parser == "avcr_vacancies" and not item.get("employerId"):
                mappings = source.get("employersByUrlPrefix") if isinstance(source.get("employersByUrlPrefix"), dict) else {}
                item["employerId"] = next(
                    (employer for prefix, employer in mappings.items() if str(item.get("sourceUrl") or "").startswith(prefix)),
                    None,
                )
            if not item.get("employerId"):
                quarantined.append(
                    {
                        "sourceId": source["id"],
                        "sourceUrl": item.get("sourceUrl"),
                        "title": item.get("title"),
                        "reason": "unresolved-legal-employer",
                    }
                )
                continue
            if selected is not None and item["employerId"] not in selected:
                continue

            candidate_items = [item]
            if source.get("followDetails", True) and parser != "lmc_graphql":
                is_pdf = source.get("detailFormat") == "pdf" or urlsplit(
                    item["sourceUrl"]
                ).path.lower().endswith(".pdf")
                detail_reason = None
                if is_pdf:
                    detail_status, detail_body = fetch_attachment_fn(item["sourceUrl"])
                    detail_text = pdf_text_fn(detail_body) if detail_status == 200 else ""
                    detail_ok = detail_status == 200 and len(detail_text.strip()) >= 20
                    detail_html = (
                        f"<h1>{escape(str(item.get('title') or ''))}</h1>"
                        f"<p>{escape(detail_text)}</p>"
                        if detail_ok
                        else ""
                    )
                else:
                    detail_status, detail_html = fetch_page(item["sourceUrl"])
                    detail_ok = page_ok(detail_status, detail_html)
                    if detail_ok:
                        detail_html = configured_detail_html(detail_html, source)
                        if not detail_html:
                            detail_ok = False
                            detail_reason = "missing-configured-detail-container"
                attempts.append(
                    {
                        "sourceId": source["id"],
                        "url": item["sourceUrl"],
                        "status": detail_status,
                        "ok": detail_ok,
                        "kind": "detail-attachment" if is_pdf else "detail",
                        **(
                            {"reason": "pdf-text-extraction-failed"}
                            if is_pdf and not detail_ok
                            else ({"reason": detail_reason} if detail_reason else {})
                        ),
                    }
                )
                if not detail_ok:
                    source_complete = False
                    continue
                attachment_patterns = (
                    source.get("detailAttachmentPatterns")
                    if not is_pdf and isinstance(source.get("detailAttachmentPatterns"), list)
                    else []
                )
                attachment_items = (
                    parse_generic_listing_links(detail_html, item["sourceUrl"], attachment_patterns)
                    if attachment_patterns
                    else []
                )
                if attachment_items:
                    candidate_items = []
                    for attachment_item in attachment_items:
                        attachment_status, attachment_body = fetch_attachment_fn(attachment_item["sourceUrl"])
                        attachment_text = pdf_text_fn(attachment_body) if attachment_status == 200 else ""
                        attachment_ok = attachment_status == 200 and len(attachment_text.strip()) >= 20
                        attempts.append(
                            {
                                "sourceId": source["id"],
                                "url": attachment_item["sourceUrl"],
                                "status": attachment_status,
                                "ok": attachment_ok,
                                "kind": "detail-attachment",
                                **(
                                    {}
                                    if attachment_ok
                                    else {"reason": "pdf-text-extraction-failed"}
                                ),
                            }
                        )
                        if not attachment_ok:
                            source_complete = False
                            continue
                        attachment_title = re.sub(
                            r"\s*[-–]\s*pdf\s*$",
                            "",
                            str(attachment_item.get("title") or ""),
                            flags=re.I,
                        ).strip()
                        attachment_html = (
                            f"<h1>{escape(attachment_title)}</h1>"
                            f"<p>{escape(attachment_text)}</p>"
                        )
                        parsed_attachment = parse_generic_job_page(
                            attachment_html,
                            attachment_item["sourceUrl"],
                            attachment_title,
                        )
                        if parsed_attachment is None:
                            quarantined.append(
                                {
                                    "sourceId": source["id"],
                                    "sourceUrl": attachment_item["sourceUrl"],
                                    "title": attachment_title,
                                    "reason": "attachment-not-a-supported-research-vacancy",
                                }
                            )
                            continue
                        candidate_items.append(
                            {
                                **item,
                                **attachment_item,
                                **parsed_attachment,
                                "title": attachment_title,
                                "employerId": item["employerId"],
                                "applicationUrl": attachment_item["sourceUrl"],
                                "applicationMethod": "official_instructions",
                                "_factHtml": attachment_html,
                            }
                        )
                else:
                    parsed = parse_generic_job_page(detail_html, item["sourceUrl"], str(item.get("title") or ""))
                    if parsed is None:
                        quarantined.append(
                            {
                                "sourceId": source["id"],
                                "sourceUrl": item.get("sourceUrl"),
                                "title": item.get("title"),
                                "reason": "detail-not-a-supported-research-vacancy",
                            }
                        )
                        continue
                    multi_position = parser == "utb_careers" and bool(
                        re.search(
                            r"\bobsazen[ií]\s+(?:celkem\s+)?\d+\s+"
                            r"(?:voln(?:[ýy]ch|ych)\s+)?(?:pracovn\w*\s+)?pozic",
                            visible_text(detail_html),
                            re.I,
                        )
                    )
                    if multi_position:
                        parsed.update(
                            {
                                "minimumDegree": "unknown",
                                "doctorateRequired": None,
                                "doctoralEnrollment": "unspecified",
                                "salaryAmount": None,
                                "salaryCurrency": None,
                                "basisFte": None,
                            }
                        )
                    item = {
                        **item,
                        **parsed,
                        "title": item["title"],
                        "_factHtml": detail_html,
                    }
                    if multi_position:
                        item["eligibilityGranularity"] = "notice_bundle"
                    candidate_items = [item]

            for candidate_item in candidate_items:
                candidate_item.setdefault("applicationUrl", candidate_item["sourceUrl"])
                candidate_item.setdefault("roundType", "regular")
                candidate_item.setdefault("workingLanguages", [])
                candidate_item.setdefault("paidStatus", "unconfirmed")
                candidate_item["discoverySourceId"] = source["id"]
                candidate_item["id"] = _stable_discovered_id(candidate_item)
                candidates.append(candidate_item)

        if source_complete:
            complete_source_ids.append(source["id"])

    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in candidates:
        key = (str(item["employerId"]), str(item.get("code") or ""), str(item["sourceUrl"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return {
        "candidates": deduped,
        "attempts": attempts,
        "quarantined": quarantined,
        "completeSourceIds": complete_source_ids,
        "expectedSourceIds": expected_source_ids,
        "deferredSourceIds": deferred_source_ids,
        "runKind": "selected_sources" if selected is not None else "all_registered_sources",
    }


def harvest_with_registered_discovery(
    seed_candidates: list[dict],
    fetch_page,
    previous: dict | None = None,
    as_of: date | None = None,
    employer_ids: set[str] | None = None,
    registry: list[dict] | None = None,
    post_json=None,
    fetch_attachment=None,
    pdf_text=None,
    now: datetime | None = None,
) -> dict:
    cache: dict[str, tuple[int, str]] = {}
    post_cache: dict[str, tuple[int, str]] = {}
    attachment_cache: dict[str, tuple[int, bytes]] = {}
    post_json_fn = post_json or request_json
    fetch_attachment_fn = fetch_attachment or request_binary

    def cached_fetch(url: str) -> tuple[int, str]:
        if url not in cache:
            if cache and SLEEP and fetch_page is request:
                time.sleep(SLEEP)
            cache[url] = fetch_page(url)
        return cache[url]

    def cached_post(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, str]:
        key = json.dumps([url, payload, headers], ensure_ascii=False, sort_keys=True)
        if key not in post_cache:
            if post_cache and SLEEP and post_json is None:
                time.sleep(SLEEP)
            post_cache[key] = post_json_fn(url, payload, headers)
        return post_cache[key]

    def cached_attachment(url: str) -> tuple[int, bytes]:
        if url not in attachment_cache:
            if attachment_cache and SLEEP and fetch_attachment is None:
                time.sleep(SLEEP)
            attachment_cache[url] = fetch_attachment_fn(url)
        return attachment_cache[url]

    previous = previous or {}
    discovery = discover_registered_candidates(
        cached_fetch,
        employer_ids,
        registry,
        post_json=cached_post,
        fetch_attachment=cached_attachment,
        pdf_text=pdf_text,
        now=now,
    )
    previous_jobs = [item for item in previous.get("jobs") or [] if isinstance(item, dict)]
    superseded_ids: list[str] = []
    for candidate in discovery["candidates"]:
        title_key = str(candidate.get("title") or "").casefold()
        matches = []
        for prior in previous_jobs:
            prior_title = prior.get("title")
            if isinstance(prior_title, dict):
                prior_title = prior_title.get("en") or prior_title.get("cs") or prior_title.get("zh-CN")
            if (
                prior.get("employerId") == candidate.get("employerId")
                and prior.get("sourceUrl") == candidate.get("sourceUrl")
                and str(prior_title or "").casefold() == title_key
            ):
                matches.append(prior)
        if matches:
            matches.sort(
                key=lambda item: (
                    item.get("publicationStatus") == "approved",
                    item.get("translationStatus") == "reviewed",
                ),
                reverse=True,
            )
            generated_id = candidate["id"]
            candidate["id"] = matches[0]["id"]
            superseded_ids.extend(
                item["id"] for item in matches[1:] if item.get("id") != candidate["id"]
            )
            if generated_id != candidate["id"]:
                superseded_ids.append(generated_id)

    candidates = _merge_seed_and_discovered(seed_candidates, discovery["candidates"])
    payload = harvest_candidates(candidates, cached_fetch, previous, as_of, sleep_seconds=0)
    candidate_ids = {item["id"] for item in candidates}
    disappeared_ids: list[str] = []
    complete_sources = set(discovery["completeSourceIds"])
    prior_windows: dict[str, list[dict]] = {}
    for item in previous.get("windows") or []:
        if isinstance(item, dict) and item.get("ownerId"):
            prior_windows.setdefault(item["ownerId"], []).append(item)
    prior_evidence = {
        item.get("id"): item
        for item in previous.get("evidence") or []
        if isinstance(item, dict) and item.get("id")
    }
    quarantined_urls = {
        str(item.get("sourceUrl")): str(item.get("reason") or "unsupported-catalogue-scope")
        for item in discovery.get("quarantined") or []
        if isinstance(item, dict) and item.get("sourceUrl")
    }
    for prior in previous.get("jobs") or []:
        if not isinstance(prior, dict) or not prior.get("id"):
            continue
        source_id = prior.get("discoverySourceId")
        if source_id not in complete_sources or prior["id"] in candidate_ids:
            continue
        archived = dict(prior)
        quarantine_reason = quarantined_urls.get(str(prior.get("sourceUrl") or ""))
        if quarantine_reason:
            archived["lifecycleStatus"] = "unknown"
            archived["catalogueScopeStatus"] = "excluded"
            attempt_reason = f"no-longer-meets-supported-scope:{quarantine_reason}"
        else:
            archived["lifecycleStatus"] = "unavailable"
            archived["catalogueScopeStatus"] = "included"
            attempt_reason = "missing-from-complete-official-listing"
        archived["visibility"] = "archived"
        archived["wholeOpportunityClosed"] = False
        archived["lastAttemptAt"] = payload["generatedAt"]
        archived["lastAttemptReason"] = attempt_reason
        payload["jobs"].append(archived)
        payload["windows"].extend(dict(item) for item in prior_windows.get(prior["id"], []))
        evidence_id = f"ev-{prior['id']}"
        if evidence_id in prior_evidence:
            payload["evidence"].append(dict(prior_evidence[evidence_id]))
        payload["skipped"].append({"id": prior["id"], "reason": attempt_reason})
        disappeared_ids.append(prior["id"])

    payload["counts"] = {"jobs": len(payload["jobs"]), "skipped": len(payload["skipped"])}
    payload["discovery"] = {
        "attempts": discovery["attempts"],
        "quarantined": discovery["quarantined"],
        "discoveredCount": len(discovery["candidates"]),
        "disappearedCount": len(disappeared_ids),
        "completeSourceIds": discovery["completeSourceIds"],
        "expectedSourceIds": discovery.get("expectedSourceIds") or [],
        "deferredSourceIds": discovery.get("deferredSourceIds") or [],
        "runKind": discovery.get("runKind") or "all_registered_sources",
        "hostCooldowns": export_host_cooldowns(),
    }
    payload["processedCandidateIds"] = sorted(
        set([item["id"] for item in candidates] + disappeared_ids + superseded_ids)
    )
    return payload


VERIFIED_CANDIDATES: list[dict] = [
    {
        "id": "job-cuni-cenmas-asia-postdoc",
        "employerId": "msmt-vs_11000",
        "title": "Researcher in Comparative Area Studies, with a Focus on Asia (Postdoctoral level)",
        "laboratory": "Center for Multidisciplinary Area Studies (CenMAS), Faculty of Arts",
        "sourceUrl": "https://cenmas.ff.cuni.cz/2026/06/09/we-are-hiring-researcher-in-comparative-area-studies-with-a-focus-on-asia-postdoctoral-level/",
        "applicationUrl": "https://cenmas.ff.cuni.cz/2026/06/09/we-are-hiring-researcher-in-comparative-area-studies-with-a-focus-on-asia-postdoctoral-level/",
        "applicationMethod": "official_instructions",
        "opensAt": "2026-06-09",
        "closesAt": "2026-09-14",
        "track": "postdoc",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "regular",
    },
    {
        "id": "job-cuni-d3s-postdoc",
        "employerId": "msmt-vs_11000",
        "title": "Postdoctoral Research Positions in software architectures for dependable and trustworthy systems",
        "laboratory": "Department of Distributed and Dependable Systems (D3S), Faculty of Mathematics and Physics",
        "sourceUrl": "https://www.d3s.mff.cuni.cz/positions/2026-1/",
        "officialDetailUrl": "https://www.d3s.mff.cuni.cz/positions/2026-1/",
        "listingUrl": "https://www.d3s.mff.cuni.cz/positions/",
        "applicationUrl": "https://www.d3s.mff.cuni.cz/positions/2026-1/",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": None,
        "track": "postdoc",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": 2900,
        "salaryCurrency": "EUR",
        "basisFte": 1.0,
        "roundType": "rolling",
        "note": "Page says applications after 31 August 2026 are still considered until positions are filled. No start date is published, so the window is not auto-opened.",
    },
    {
        "id": "job-cuni-mff-academic-researcher-ksvi",
        "employerId": "msmt-vs_11000",
        "title": "Academic Researcher at the Department of Software and Computer Science Education",
        "laboratory": "Department of Software and Computer Science Education, Faculty of Mathematics and Physics",
        "sourceUrl": "https://www.mff.cuni.cz/en/faculty/job-opportunities",
        "applicationUrl": "https://www.mff.cuni.cz/en/faculty/job-opportunities",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-24",
        "track": "post_master",
        "workingLanguages": ["en", "cs"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": None,
        "roundType": "regular",
        "code": "202609-VP2-MFF-KSVI-081",
    },
    {
        "id": "job-cuni-mff-research-fellow-ucjf",
        "employerId": "msmt-vs_11000",
        "title": "Research Fellow at the Institute of Particle and Nuclear Physics",
        "laboratory": "Institute of Particle and Nuclear Physics, Faculty of Mathematics and Physics",
        "sourceUrl": "https://www.mff.cuni.cz/en/faculty/job-opportunities",
        "applicationUrl": "https://www.mff.cuni.cz/en/faculty/job-opportunities",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-15",
        "track": "post_master",
        "workingLanguages": ["en", "cs"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": None,
        "roundType": "regular",
        "code": "202609-VP2-MFF-UCJF-092",
    },
    {
        "id": "job-ctu-roboprox-postdoc-babuska",
        "employerId": "msmt-vs_21000",
        "title": "Postdoc position in Physics-aware symbolic regression for dynamic systems modeling",
        "laboratory": "CIIRC ROBOPROX",
        "sourceUrl": "https://www.ciirc.cvut.cz/roboprox/job-positions/",
        "applicationUrl": "https://www.ciirc.cvut.cz/roboprox/job-positions/",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": None,
        "track": "postdoc",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "rolling",
        "code": "04-Postdoc-Babuska",
    },
    {
        "id": "job-ctu-aic-postdoc-cybersecurity",
        "employerId": "msmt-vs_21000",
        "title": "Postdoc in AI and Cybersecurity",
        "laboratory": "Artificial Intelligence Center, Faculty of Electrical Engineering",
        "sourceUrl": "https://www.aic.fel.cvut.cz/careers",
        "applicationUrl": "https://www.aic.fel.cvut.cz/careers",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": None,
        "track": "postdoc",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": None,
        "roundType": "rolling",
    },
    {
        "id": "job-ctu-aic-phd-energy-opt",
        "employerId": "msmt-vs_21000",
        "title": "PhD student: near real-time optimization of non-linear problems with discrete decision variables",
        "laboratory": "Artificial Intelligence Center, Faculty of Electrical Engineering",
        "sourceUrl": "https://www.aic.fel.cvut.cz/careers",
        "applicationUrl": "https://www.aic.fel.cvut.cz/careers",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": None,
        "track": "assistant",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "rolling",
        "doctoralEnrollment": "required",
    },
    {
        "id": "job-ctu-roboprox-phd-hri",
        "employerId": "msmt-vs_21000",
        "title": "PhD position in Human-robot aware planning and acting",
        "laboratory": "CIIRC ROBOPROX",
        "sourceUrl": "https://www.ciirc.cvut.cz/roboprox/job-positions/",
        "applicationUrl": "https://www.ciirc.cvut.cz/roboprox/job-positions/",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": None,
        "track": "assistant",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "rolling",
        "doctoralEnrollment": "required",
        "code": "01-PhD-Babuska",
    },
    {
        "id": "job-uct-msca-pf-2026",
        "employerId": "msmt-vs_22000",
        "title": "Marie Skłodowska-Curie Postdoctoral Fellowships hosted at UCT Prague",
        "laboratory": "University of Chemistry and Technology Prague",
        "sourceUrl": "https://www.vscht.cz/research/postdocs/msca-pf-en?jazyk=en",
        "applicationUrl": "https://www.vscht.cz/research/postdocs/msca-pf-en?jazyk=en",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-09",
        "track": "postdoc",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": 5153.14,
        "salaryCurrency": "EUR",
        "basisFte": 1.0,
        "roundType": "regular",
    },
    {
        "id": "job-uct-phd-chemistry",
        "employerId": "msmt-vs_22000",
        "title": "PhD researcher position in Chemistry",
        "laboratory": "Department of Inorganic Chemistry",
        "sourceUrl": "https://www.vscht.cz/uredni-deska/vyberova-rizeni/akademicke-pozice",
        "applicationUrl": "https://www.vscht.cz/uredni-deska/vyberova-rizeni/akademicke-pozice",
        "applicationMethod": "official_instructions",
        "opensAt": "2026-01-22",
        "closesAt": None,
        "track": "assistant",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "rolling",
        "doctoralEnrollment": "required",
    },
    {
        "id": "job-uct-lab-analyst",
        "employerId": "msmt-vs_22000",
        "title": "Odborný pracovník v analytické laboratoři",
        "laboratory": "Laboratoř forenzní analýzy biologicky aktivních látek",
        "sourceUrl": "https://www.vscht.cz/uredni-deska/vyberova-rizeni/akademicke-pozice",
        "applicationUrl": "https://www.vscht.cz/uredni-deska/vyberova-rizeni/akademicke-pozice",
        "applicationMethod": "official_instructions",
        "opensAt": "2026-08-28",
        "closesAt": None,
        "track": "assistant",
        "workingLanguages": ["cs", "en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "rolling",
        "doctoralEnrollment": "not_required",
    },
    {
        "id": "job-upol-msca-pf-law-2026",
        "employerId": "msmt-vs_15000",
        "title": "MSCA Postdoctoral Fellowships 2026 in Law",
        "laboratory": "Faculty of Law, Palacký University Olomouc",
        "sourceUrl": "https://www.pf.upol.cz/veda-a-vyzkum/msca-postdoctoral-fellowships-2026-in-law/",
        "applicationUrl": "https://www.pf.upol.cz/veda-a-vyzkum/msca-postdoctoral-fellowships-2026-in-law/",
        "applicationMethod": "official_instructions",
        "opensAt": "2026-04-09",
        "closesAt": "2026-09-09",
        "track": "postdoc",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": "EUR",
        "basisFte": 1.0,
        "roundType": "regular",
    },
    {
        "id": "job-upol-msca-pf-2026",
        "employerId": "msmt-vs_15000",
        "title": "MSCA Postdoctoral Fellowships 2026 hosted at Palacký University Olomouc",
        "laboratory": None,
        "sourceUrl": "https://www.upol.cz/nc/ps/zprava/clanek/the-msca-call-for-postdoctoral-fellowships-for-2026-is-now-open/",
        "applicationUrl": "https://www.upol.cz/nc/ps/zprava/clanek/the-msca-call-for-postdoctoral-fellowships-for-2026-is-now-open/",
        "applicationMethod": "official_instructions",
        "opensAt": "2026-04-10",
        "closesAt": "2026-09-09",
        "track": "postdoc",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "regular",
    },
    {
        "id": "job-vsb-nanotech-researcher",
        "employerId": "msmt-vs_27000",
        "title": "Vědecko-výzkumný pracovník pro materiálové a nanotechnologické aplikace",
        "laboratory": "Centrum nanotechnologií",
        "sourceUrl": "https://www.vsb.cz/cs/univerzita/informacni-deska/pracovni-prilezitosti/",
        "applicationUrl": "https://www.vsb.cz/cs/univerzita/informacni-deska/pracovni-prilezitosti/",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-08",
        "track": "post_master",
        "workingLanguages": ["cs"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": None,
        "roundType": "regular",
    },
    {
        "id": "job-vsb-cnt-researcher",
        "employerId": "msmt-vs_27000",
        "title": "Researcher",
        "laboratory": "CNT - Nanotechnology Centre",
        "sourceUrl": "https://www.vsb.cz/en/university/informational-board/job-opportunities/",
        "applicationUrl": "https://www.vsb.cz/en/university/informational-board/job-opportunities/",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-29",
        "track": "post_master",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": None,
        "roundType": "regular",
    },
    {
        "id": "job-vsb-cnt-phd",
        "employerId": "msmt-vs_27000",
        "title": "PhD student",
        "laboratory": "CNT - Nanotechnology Centre",
        "sourceUrl": "https://www.vsb.cz/en/university/informational-board/job-opportunities/",
        "applicationUrl": "https://www.vsb.cz/en/university/informational-board/job-opportunities/",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-20",
        "track": "assistant",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": None,
        "roundType": "regular",
        "doctoralEnrollment": "required",
    },
    {
        "id": "job-vsb-msca-dc8",
        "employerId": "msmt-vs_27000",
        "title": "Marie Skłodowska-Curie Doctoral Candidate (DC8)",
        "laboratory": "Advanced Nanorobots and Multiscale Robotics Lab",
        "sourceUrl": "https://www.vsb.cz/en/university/informational-board/job-opportunities/",
        "applicationUrl": "https://www.vsb.cz/en/university/informational-board/job-opportunities/",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-17",
        "track": "assistant",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "regular",
        "doctoralEnrollment": "required",
    },
    {
        "id": "job-vsb-quantum-phd",
        "employerId": "msmt-vs_27000",
        "title": "PhD Position in Quantum Networks (MSCA Doctoral Network QUESTING)",
        "laboratory": "Faculty of Electrical Engineering and Computer Science",
        "sourceUrl": "https://www.vsb.cz/veda/en/news-detail/?reportId=52419",
        "applicationUrl": "https://www.vsb.cz/veda/en/news-detail/?reportId=52419",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-15",
        "track": "assistant",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "regular",
        "doctoralEnrollment": "required",
    },
    {
        "id": "job-jcu-msca-pf-2026",
        "employerId": "msmt-vs_12000",
        "title": "MSCA Postdoctoral Fellowship 2026",
        "laboratory": None,
        "sourceUrl": "https://www.jcu.cz/en/science-and-research/eu-desk/open-calls/msca-postdoctoral-fellowship-2026",
        "applicationUrl": "https://www.jcu.cz/en/science-and-research/eu-desk/open-calls/msca-postdoctoral-fellowship-2026",
        "applicationMethod": "official_instructions",
        "opensAt": "2026-04-09",
        "closesAt": "2026-09-09",
        "track": "postdoc",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": None,
        "basisFte": 1.0,
        "roundType": "regular",
    },
    {
        "id": "job-muni-fellowship-81652",
        "employerId": "msmt-vs_14000",
        "title": "Ph.D. Fellowship",
        "laboratory": "Faculty of Science / Department of Theoretical Physics and Astrophysics",
        "sourceUrl": "https://www.muni.cz/en/about-us/careers/vacancies/81652",
        "applicationUrl": "https://www.muni.cz/en/about-us/careers/vacancies/81652",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-20",
        "track": "assistant",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": "CZK",
        "basisFte": 0.5,
        "roundType": "regular",
        "doctoralEnrollment": "required",
    },
    {
        "id": "job-muni-astrophysics-postdoc-81445",
        "employerId": "msmt-vs_14000",
        "title": "Postdoctoral position in Astrophysics",
        "laboratory": "Department of Theoretical Physics and Astrophysics, Faculty of Science",
        "sourceUrl": "https://www.muni.cz/en/about-us/careers/vacancies/81445",
        "applicationUrl": "https://www.muni.cz/en/about-us/careers/vacancies/81445",
        "applicationMethod": "official_instructions",
        "opensAt": None,
        "closesAt": "2026-09-30",
        "track": "postdoc",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
        "salaryAmount": None,
        "salaryCurrency": "CZK",
        "basisFte": 1.0,
        "roundType": "regular",
    },
]


JOB_TITLES_ZH: dict[str, str] = {
    "job-cuni-cenmas-asia-postdoc": "亚洲比较区域研究博士后研究员",
    "job-cuni-d3s-postdoc": "高可靠可信系统软件架构博士后研究员",
    "job-cuni-mff-academic-researcher-ksvi": "软件与计算机科学教育系学术研究员",
    "job-cuni-mff-research-fellow-ucjf": "粒子与核物理研究所研究员",
    "job-cuni-mff-postdoc-ksi": "软件工程系博士后研究员",
    "job-cvut-ciirc-roboprox-postdoc": "机器人与机器智能中心 (CIIRC) RoboProX 博士后研究员",
    "job-cvut-fel-aic-phd-assistant": "人工智能中心 (AIC) 博士生助理研究员",
    "job-cvut-fel-comms-phd": "通信工程系博士生研究助理",
    "job-vut-ceitec-smart-nanodevices-postdoc": "CEITEC 智能纳米器件博士后研究员",
    "job-vut-fme-thermo-postdoc": "机械工程学院热力学与流体力学博士后研究员",
    "job-vscht-biochem-fellow": "生物化学与微生物学系研究员",
    "job-vse-econ-assistant": "应用经济学与计量经济学助理研究员",
    "job-czu-ftz-tropical-agri-phd": "热带农业科学学院博士生研究助理",
    "job-osu-science-biodiversity-fellow": "理学院生物多样性与生态学研究员",
    "job-upol-catrin-nanomaterials-postdoc": "先进技术与材料研究所 (CATRIN) 纳米材料博士后研究员",
    "job-jcu-msca-pf-2026": "玛丽居里博士后奖学金项目候选研究员",
    "job-muni-sci-fellowship-81652": "自然科学学院四年制博士带薪研究岗位 (0.5 FTE)",
    "job-muni-sci-postdoc-81445": "理论物理与天体物理系天体物理学博士后研究员",
}


def localized(title: str, zh_title: str | None = None, cs_title: str | None = None) -> dict:
    return {"zh-CN": zh_title or title, "en": title, "cs": cs_title or title}


def job_record(candidate: dict, verified_at: str, host_verified: bool, page_text: str = "", as_of: date | None = None) -> tuple[dict, dict | None]:
    cur_today = as_of or date.today()
    track = candidate["track"]
    title = candidate["title"]
    fact_text = candidate.get("_factText") or (entity_scope(page_text, title) if page_text else title)
    degrees = extract_qualifications(title, fact_text)
    if candidate.get("qualificationFactsAuthoritative") is True:
        degrees["minimumDegree"] = candidate.get("minimumDegree", "unknown")
        degrees["doctorateRequired"] = candidate.get("doctorateRequired")
    if candidate.get("eligibilityGranularity") == "notice_bundle":
        degrees = {
            "minimumDegree": "unknown",
            "doctorateRequired": None,
            "doctoralEnrollment": "unspecified",
        }
    cid = candidate.get("id", "")
    zh_title = candidate.get("titleZh") or JOB_TITLES_ZH.get(cid)
    lab = candidate.get("laboratory")
    page_close = extract_deadline(fact_text) if page_text else None
    closes = page_close or parse_date(candidate.get("closesAt"))
    opens = parse_date(candidate.get("opensAt"))
    closed = page_is_closed(fact_text, title) if page_text else False
    if closes and closes < cur_today and not closed:
        return {}, None
    langs = candidate.get("workingLanguages")
    if not langs and fact_text:
        detected = []
        low_text = fact_text.lower()
        if re.search(r"\b(?:english|angličtin|anglictin)\b", low_text):
            detected.append("en")
        if re.search(r"\b(?:czech|češtin|cestin)\b", low_text):
            detected.append("cs")
        langs = detected if detected else None
    # A67: cycle and tax are evidence-based. An amount without a stated payroll
    # period stays "unspecified"; a net figure is never relabelled gross.
    salary_amount = candidate.get("salaryAmount")
    salary_cycle = candidate.get("salaryCycle")
    salary_tax = candidate.get("salaryTax")
    job = {
        "id": candidate["id"],
        "employerId": candidate["employerId"],
        "title": localized(title, zh_title=zh_title),
        "laboratory": localized(lab) if lab else None,
        "originalText": title,
        "sourceLanguage": candidate.get("sourceLanguage") or "en",
        "translationStatus": "unreviewed",
        "reviewedAt": None,
        "minimumDegree": degrees["minimumDegree"],
        "doctorateRequired": degrees["doctorateRequired"],
        "doctoralEnrollment": degrees["doctoralEnrollment"],
        "paidStatus": candidate.get("paidStatus") or "unconfirmed",
        "salary": {
            "amount": salary_amount,
            "currency": candidate.get("salaryCurrency"),
            "cycle": salary_cycle
            or ("unspecified" if salary_amount is not None else None),
            "tax": salary_tax
            or ("unknown" if salary_amount is not None else "unknown"),
            "basisFte": candidate.get("basisFte"),
        },
        "salaryAmountMin": candidate.get("salaryAmountMin"),
        "salaryAmountMax": candidate.get("salaryAmountMax"),
        "fundingType": candidate.get("fundingType") or "unknown",
        "employmentFte": candidate.get("employmentFte"),
        "employmentStartsAt": candidate.get("employmentStartsAt"),
        # BCP 47 ``und`` keeps an omitted working-language condition explicit.
        # It must never be inferred from the language used to write the advert.
        "workingLanguages": langs if langs else ["und"],
        "sourceUrl": candidate["sourceUrl"],
        "applicationUrl": candidate.get("applicationUrl") or candidate["sourceUrl"],
        "applicationMethod": candidate.get("applicationMethod") or "official_instructions",
        "applicationHostVerified": host_verified,
        "lifecycleStatus": "closed" if closed else ("unknown" if not opens else "open"),
        "visibility": "review_pending",
        "catalogueScopeStatus": "included",
        "isPostdoc": track == "postdoc",
        "track": track,
        "city": CITY.get(candidate["employerId"]),
        "verifiedAt": verified_at[:10],
        "parserVersion": PARSER_VERSION,
        "sourceFetchedAt": verified_at,
        "factsExtractedAt": verified_at,
        "dataClass": "official_career_extract",
        "wholeOpportunityClosed": closed,
        "discoverySourceId": candidate.get("discoverySourceId"),
        "sourceItemId": candidate.get("code"),
        "caseNumber": candidate.get("caseNumber"),
        "noticePostedAt": candidate.get("noticePostedAt"),
        "noticeRemoveAt": candidate.get("noticeRemoveAt"),
        "eligibilityGranularity": candidate.get("eligibilityGranularity") or "vacancy",
    }
    window = None
    if opens or closes or candidate.get("roundType") == "rolling":
        precision = "date" if (opens or closes) else "unknown"
        status = "closed" if closed else "unknown"
        window = {
            "id": f"win-{candidate['id']}",
            "ownerType": "research_job",
            "ownerId": candidate["id"],
            "academicYear": None,
            "roundNumber": None,
            "roundLabelOriginal": candidate.get("code"),
            "roundType": candidate.get("roundType") or "unspecified",
            "applicantScope": None,
            "opensAt": iso_date(opens),
            "closesAt": iso_date(closes),
            "timezone": "Europe/Prague",
            "datePrecision": precision,
            "status": status,
            "conditionalOnVacancies": candidate.get("roundType") == "rolling",
            "applicationUrl": candidate.get("applicationUrl") or candidate["sourceUrl"],
            "sourceEvidenceId": f"ev-{candidate['id']}",
        }
    apply_translation_review(job, source_text_hash(fact_text or title), windows=[window] if window else [])
    return job, window


def harvest_candidates(
    candidates: list[dict],
    fetch_page,
    previous: dict | None = None,
    as_of: date | None = None,
    *,
    sleep_seconds: float = SLEEP,
) -> dict:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    previous = previous or {}
    prev_jobs = {item["id"]: item for item in previous.get("jobs") or []}
    prev_windows: dict[str, list[dict]] = {}
    for item in previous.get("windows") or []:
        if item.get("ownerId"):
            prev_windows.setdefault(item["ownerId"], []).append(item)
    prev_evidence = {item["id"]: item for item in previous.get("evidence") or []}
    jobs = []
    windows = []
    evidence = []
    skipped = []

    def keep_previous(candidate_id: str, reason: str) -> None:
        prior = prev_jobs.get(candidate_id)
        if not prior:
            return
        kept = dict(prior)
        kept["lastAttemptAt"] = generated
        kept["lastAttemptReason"] = reason
        jobs.append(kept)
        if candidate_id in prev_windows:
            windows.extend(prev_windows[candidate_id])
        ev_id = f"ev-{candidate_id}"
        if ev_id in prev_evidence:
            evidence.append(prev_evidence[ev_id])

    live_fetch_count = 0
    for candidate in candidates:
        url = candidate["sourceUrl"]
        embedded_html = candidate.get("_factHtml")
        if isinstance(embedded_html, str) and embedded_html.strip():
            status, html = 200, embedded_html
        else:
            if live_fetch_count and sleep_seconds:
                time.sleep(sleep_seconds)
            status, html = fetch_page(url)
            live_fetch_count += 1
        RAW.mkdir(parents=True, exist_ok=True)
        slug = candidate["id"]
        (RAW / f"{slug}.html").write_text(html, encoding="utf-8")
        if not page_ok(status, html):
            reason = f"http-{status}"
            skipped.append({"id": candidate["id"], "reason": reason})
            keep_previous(candidate["id"], reason)
            continue
        text = visible_text(html)
        lowered = text.lower()
        if candidate["title"].split("(")[0].strip().lower() not in lowered and candidate["title"].lower() not in lowered:
            tokens = [token for token in re.split(r"\W+", candidate["title"].lower()) if len(token) > 4]
            if sum(token in lowered for token in tokens[:4]) < 2:
                reason = "title-not-found"
                skipped.append({"id": candidate["id"], "reason": reason})
                keep_previous(candidate["id"], reason)
                continue
        job, window = job_record(candidate, generated, True, text, as_of=as_of)
        if not job:
            if candidate["id"] in prev_jobs:
                prior = dict(prev_jobs[candidate["id"]])
                prior["lifecycleStatus"] = "expired"
                prior["wholeOpportunityClosed"] = False
                prior["visibility"] = "archived"
                prior["lastAttemptAt"] = generated
                prior["lastAttemptReason"] = "past-deadline-archived"
                jobs.append(prior)
                for w in prev_windows.get(candidate["id"], []):
                    w_copy = dict(w)
                    w_copy["status"] = "closed"
                    windows.append(w_copy)
                ev_id = f"ev-{candidate['id']}"
                if ev_id in prev_evidence:
                    evidence.append(prev_evidence[ev_id])
            skipped.append({"id": candidate["id"], "reason": "past-deadline"})
            continue
        jobs.append(job)
        if window:
            windows.append(window)
        evidence.append(
            {
                "id": f"ev-{candidate['id']}",
                "url": url,
                "sourceHash": job["sourceHash"],
                "note": {
                    "zh-CN": "学校官方招聘页采集，缺开始日期不视为开放。",
                    "en": "Harvested from an official career page. A missing start date is not treated as open.",
                    "cs": "Sebráno z oficiální kariérní stránky. Chybějící datum zahájení se nepovažuje za otevřené.",
                },
            }
        )
    return {
        "generatedAt": generated,
        "dataClass": "official_career_extract",
        "catalogKind": "jobs_not_published",
        "note": (
            "Research vacancies harvested from official university career pages "
            "registered in the source inventory. EURAXESS is not stored as the apply URL. "
            "A reachable page is not an open window. Past deadlines are omitted. "
            "Not written to data/published/."
        ),
        "counts": {"jobs": len(jobs), "skipped": len(skipped)},
        "skipped": skipped,
        "jobs": jobs,
        "windows": windows,
        "evidence": evidence,
    }


def _fact_diff(before: dict, after: dict) -> dict:
    changes: dict = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes[key] = {"from": before.get(key), "to": after.get(key)}
    return changes


def replay_stored_candidates(
    payload: dict,
    raw_dir: Path = RAW,
    source_ids: set[str] | None = None,
    generated_at: str | None = None,
) -> tuple[dict, dict]:
    """A69: replay immutable raw responses through the current parser.

    Offline replay never fetches and never claims a live check. Fetched
    timestamps stay untouched; extracted facts get a new ``factsExtractedAt``
    and the current parser version; any normalized-fact change demotes the
    record to review-pending through the normal review binding. Raw input that
    is missing or no longer parses is reported instead of fabricated.
    """
    generated = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reviews = load_job_reviews()
    windows = [item for item in payload.get("windows") or [] if isinstance(item, dict)]
    jobs_out: list[dict] = []
    report: dict = {
        "generatedAt": generated,
        "parserVersion": PARSER_VERSION,
        "changed": [],
        "unchanged": [],
        "missingRaw": [],
        "unparseable": [],
        "skippedArchived": [],
    }
    for job in payload.get("jobs") or []:
        if not isinstance(job, dict) or not job.get("id"):
            continue
        if source_ids is not None and job.get("discoverySourceId") not in source_ids:
            jobs_out.append(job)
            continue
        if job.get("visibility") == "archived":
            report["skippedArchived"].append(job["id"])
            jobs_out.append(job)
            continue
        raw_path = Path(raw_dir) / f"{job['id']}.html"
        if not raw_path.is_file():
            report["missingRaw"].append(job["id"])
            jobs_out.append(job)
            continue
        raw_html = raw_path.read_text(encoding="utf-8")
        title = job.get("originalText") or ""
        if not isinstance(title, str) or not title:
            stored_title = job.get("title")
            title = stored_title.get("en") if isinstance(stored_title, dict) else ""
        parsed = parse_generic_job_page(raw_html, job.get("sourceUrl") or "", title_hint=title)
        if parsed is None:
            report["unparseable"].append(job["id"])
            jobs_out.append(job)
            continue
        before_facts = canonical_job_facts_public(job, windows)
        new_job = dict(job)
        salary_amount = parsed["salaryAmount"]
        new_job.update(
            {
                "minimumDegree": parsed["minimumDegree"],
                "doctorateRequired": parsed["doctorateRequired"],
                "doctoralEnrollment": parsed["doctoralEnrollment"],
                "paidStatus": parsed["paidStatus"],
                "salary": {
                    "amount": salary_amount,
                    "currency": parsed["salaryCurrency"],
                    "cycle": parsed["salaryCycle"]
                    or ("unspecified" if salary_amount is not None else None),
                    "tax": parsed["salaryTax"]
                    or ("unknown" if salary_amount is not None else "unknown"),
                    "basisFte": parsed["basisFte"],
                },
                "salaryAmountMin": parsed["salaryAmountMin"],
                "salaryAmountMax": parsed["salaryAmountMax"],
                "fundingType": parsed["fundingType"],
                "employmentFte": parsed["employmentFte"],
                "employmentStartsAt": parsed["employmentStartsAt"],
                "parserVersion": PARSER_VERSION,
                "factsExtractedAt": generated,
            }
        )
        if not job.get("sourceFetchedAt"):
            new_job["sourceFetchedAt"] = job.get("verifiedAt")
        after_facts = canonical_job_facts_public(new_job, windows)
        changes = _fact_diff(before_facts, after_facts)
        changed = bool(changes)
        source_hash = (
            source_text_hash(visible_text(raw_html))
            if raw_html.strip()
            else (job.get("sourceHash") or source_text_hash(title))
        )
        apply_translation_review(new_job, source_hash, reviews, windows)
        jobs_out.append(new_job)
        entry = {
            "id": job["id"],
            "factChanges": changes,
            "fundingTypeChanged": job.get("fundingType") != new_job.get("fundingType"),
            "publicationStatusAfter": new_job.get("publicationStatus"),
        }
        if changed or entry["fundingTypeChanged"]:
            report["changed"].append(entry)
        else:
            report["unchanged"].append(job["id"])
    result = dict(payload)
    result["jobs"] = jobs_out
    return result, report


def canonical_job_facts_public(job: dict, windows: list[dict] | None = None) -> dict:
    """Public normalized facts used for replay diffs (job_fact_hash payload)."""
    from publication_rules import canonical_job_facts

    return canonical_job_facts(job, windows)


def reconcile_stored_reviews(payload: dict, raw_dir: Path = RAW) -> dict:
    """Re-evaluate stored candidates against explicit review records without fetching."""
    reviews = load_job_reviews()
    jobs = []
    source_hashes: dict[str, str] = {}
    windows = [item for item in payload.get("windows") or [] if isinstance(item, dict)]
    for item in payload.get("jobs") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        job = dict(item)
        # ``sourceHash`` was calculated from the vacancy's scoped fact text at
        # collection time.  A stored raw file can contain a whole listing page
        # with neighbouring adverts, navigation and dynamic content, so hashing
        # that file here creates a different evidence identity and incorrectly
        # invalidates an otherwise matching review.  Reconciliation does not
        # re-parse evidence; it must preserve the collector-bound hash.
        source_hash = job.get("sourceHash") or source_text_hash(str(job.get("originalText") or ""))
        apply_translation_review(job, source_hash, reviews, windows)
        source_hashes[job["id"]] = source_hash
        jobs.append(job)
    evidence = []
    for item in payload.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        ident = str(copied.get("id") or "")
        if ident.startswith("ev-") and ident[3:] in source_hashes:
            copied["sourceHash"] = source_hashes[ident[3:]]
        evidence.append(copied)
    result = dict(payload)
    result["jobs"] = jobs
    result["evidence"] = evidence
    result["counts"] = {
        "jobs": len(jobs),
        "skipped": len(result.get("skipped") or []),
    }
    return result


def bind_review_payloads(
    reviews_path: Path = REVIEWS,
    jobs_path: Path = OUT,
    *,
    legacy_source_hashes: dict[str, str] | None = None,
    expected_prior_generated_at: str | None = None,
) -> dict:
    """Bind fact/translation hashes for legacy review entries; never bless changed facts.

    A75: entries already bound under fact-v1 are read-only here.  If the stored
    record's fact/evidence hash no longer matches the review entry, the helper
    reports a pending re-review request with the hash diff instead of silently
    replacing the stored hash and inheriting the old approval.  Pre-fact-v1
    legacy entries may be bound only when the caller explicitly passes the
    exact per-job legacy source hash and the expected prior generation of the
    candidate file, and both still match the stored record.
    """
    reviews_doc = json.loads(reviews_path.read_text(encoding="utf-8"))
    payload = json.loads(jobs_path.read_text(encoding="utf-8")) if jobs_path.is_file() else {}
    if expected_prior_generated_at is not None and payload.get("generatedAt") != expected_prior_generated_at:
        raise ValueError(
            "candidate generation mismatch: pass the exact generatedAt of the "
            f"records being migrated (expected {expected_prior_generated_at!r}, found {payload.get('generatedAt')!r})"
        )
    reviews = reviews_doc.get("reviews") if isinstance(reviews_doc.get("reviews"), dict) else {}
    windows = [item for item in payload.get("windows") or [] if isinstance(item, dict)]
    jobs_by_id = {
        item["id"]: item
        for item in payload.get("jobs") or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    bound = 0
    conflicts: list[dict] = []
    for job_id, entry in reviews.items():
        if not isinstance(entry, dict):
            continue
        job = jobs_by_id.get(job_id)
        if not isinstance(job, dict):
            continue
        current_fact = job_fact_hash(job, windows)
        current_evidence = job.get("sourceHash") or entry.get("sourceHash")
        already_bound = (
            entry.get("normalizationVersion") == FACT_NORMALIZATION_VERSION
            and isinstance(entry.get("factHash"), str)
            and entry["factHash"]
        )
        if already_bound:
            changed = []
            if entry.get("factHash") != current_fact:
                changed.append("facts")
            if entry.get("evidenceHash") != current_evidence:
                changed.append("evidence")
            if changed:
                # A fact-bound record must fail loudly instead of silently
                # inheriting its old approval; a new review record with the
                # changed evidence is the only path back to approved.
                conflicts.append(
                    {
                        "jobId": job_id,
                        "reason": "+".join(changed) + "-changed-since-review",
                        "storedFactHash": entry.get("factHash"),
                        "currentFactHash": current_fact,
                        "storedEvidenceHash": entry.get("evidenceHash"),
                        "currentEvidenceHash": current_evidence,
                    }
                )
            continue
        locales = entry.get("locales") if isinstance(entry.get("locales"), dict) else {}
        if not all(
            isinstance(locales.get(locale), dict) and locales[locale].get("status") == "reviewed"
            for locale in ("zh-CN", "en", "cs")
        ):
            continue
        title = entry.get("title") if isinstance(entry.get("title"), dict) else job.get("title")
        if not isinstance(title, dict) or not all(isinstance(title.get(locale), str) and title[locale].strip() for locale in ("zh-CN", "en", "cs")):
            continue
        legacy_hash = (legacy_source_hashes or {}).get(job_id)
        if (
            legacy_hash is None
            or entry.get("sourceHash") != legacy_hash
            or current_evidence != legacy_hash
        ):
            conflicts.append(
                {
                    "jobId": job_id,
                    "reason": "legacy-binding-unverified",
                    "storedFactHash": entry.get("factHash"),
                    "currentFactHash": current_fact,
                    "storedEvidenceHash": entry.get("evidenceHash"),
                    "currentEvidenceHash": current_evidence,
                }
            )
            continue
        entry["normalizationVersion"] = FACT_NORMALIZATION_VERSION
        entry["factHash"] = current_fact
        entry["evidenceHash"] = current_evidence
        entry["reviewer"] = {"role": "operator_source_review"}
        entry["title"] = {locale: title[locale] for locale in ("zh-CN", "en", "cs")}
        for locale in ("zh-CN", "en", "cs"):
            locales[locale]["contentHash"] = translation_content_hash(title[locale])
        entry["locales"] = locales
        bound += 1
    result = {"bound": bound, "conflicts": conflicts, "reviews": len(reviews)}
    if bound or not conflicts:
        if bound:
            reviews_doc["reviews"] = reviews
            reviews_doc["note"] = (
                "Explicit per-locale editorial review records bound to canonical fact and "
                "translation hashes (fact-v1). The reviewer role is operator_source_review: "
                "an internal source-and-language review, not an external human certification. "
                "Changing salary, eligibility, original text, or translated titles invalidates approval. "
                "This helper never rebinds a fact-bound entry whose facts or evidence changed; "
                "such records need a new review."
            )
            reviews_path.write_text(json.dumps(reviews_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    # Conflicts without any binding: report only, leave the review file untouched.
    return result


def main() -> None:
    if "--bind-review-payloads" in sys.argv[1:]:
        result = bind_review_payloads()
        print(json.dumps(result, ensure_ascii=False))
        return
    if "--replay-candidates" in sys.argv[1:]:
        args = sys.argv[1:]
        source_ids_arg: set[str] | None = None
        if "--source-ids" in args:
            raw_value = args[args.index("--source-ids") + 1]
            source_ids_arg = {part.strip() for part in raw_value.split(",") if part.strip()}
        raw_dir_arg = RAW
        if "--raw-dir" in args:
            raw_dir_arg = Path(args[args.index("--raw-dir") + 1])
        previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
        merged, report = replay_stored_candidates(
            previous, raw_dir=raw_dir_arg, source_ids=source_ids_arg
        )
        from file_lock import FileMutex, LockUnavailable

        lock_path = ROOT / "services" / "ingestion" / "runs" / "refresh.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            mutex = FileMutex(lock_path, {"operation": "candidate-replay-write"})
            with mutex:
                tmp = OUT.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                tmp.replace(OUT)
        except LockUnavailable as exc:
            raise SystemExit(f"refresh already running: {exc}") from exc
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if "--reconcile-reviews" in sys.argv[1:]:
        previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
        payload = reconcile_stored_reviews(previous)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(OUT)
        approved = sum(job.get("publicationStatus") == "approved" for job in payload.get("jobs") or [])
        print(f"Reconciled {len(payload.get('jobs') or [])} stored jobs; {approved} approved for publication")
        return
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
    payload = harvest_with_registered_discovery(VERIFIED_CANDIDATES, request, previous)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {payload['counts']['jobs']} jobs ({payload['counts']['skipped']} skipped) to {OUT}")


if __name__ == "__main__":
    main()

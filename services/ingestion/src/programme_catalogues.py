"""School programme catalogues read page by page (owner decision 2026-10-03).

The generic resolver (resolve_programme_links.py) binds a register row to a
school page by its title, and leaves a row unresolved when the catalogue does
not say which level or faculty a same-titled page belongs to. Some schools
publish a structured page per programme that states those facts itself:
Masaryk University's pages say "Zajišťuje <faculty> · Typ studia <level> ·
Vyučovací jazyk <language>". This module reads such catalogues completely and
writes one record per programme page; the resolver uses the records as
harvested candidates (config/programme-page-sources.json) and binds a row only
when title, level, language and, where the register has several, faculty all
agree. Nothing here is inferred: a page that does not state a field leaves it
empty.

Usage:
    python resolve_programme_links.py ... (reads the outputs)
    python programme_catalogues.py --school muni --live
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "sources" / "admissions"
FetchPage = Callable[[str], "tuple[int, str]"]


def page_text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def _between(text: str, label: str, stops: tuple[str, ...]) -> str | None:
    match = re.search(rf"\b{label}\s+(.+?)\s+(?:{'|'.join(stops)})\b", text)
    return match.group(1).strip() if match else None


# --------------------------------------------------------------------------- #
# Masaryk University
# --------------------------------------------------------------------------- #

MUNI_BASE = "https://www.muni.cz"
MUNI_SEEDS = (
    "/bakalarske-a-magisterske-studijni-programy",
    "/en/bachelors-and-masters-study-programmes",
    # Follow-up master's programmes have their own catalogue.
    "/uchazeci/navazujici-magisterske-studium/nabidka-studia",
    "/en/admissions/follow-up-masters-degree/nabidka-studia",
    "/uchazeci/doktorske-studium/vyberte-si-program",
    "/en/admissions/phd-studies/choose-programme",
)
MUNI_LEVELS = {
    "bakalářský": "bachelor",
    "navazující magisterský": "master",
    "magisterský navazující na bakalářský": "master",
    "magisterský": "master",
    "doktorský": "doctorate",
    "bachelor's": "bachelor",
    "follow-up master's": "master",
    "master's": "master",
    "doctoral": "doctorate",
}
MUNI_LANGUAGES = {"čeština": "cs", "angličtina": "en", "czech": "cs", "english": "en", "němčina": "de", "german": "de"}
# The faculties' English names on MUNI's own English pages; the register
# names them in Czech.
MUNI_FACULTIES_EN = {
    "Faculty of Law": "Právnická fakulta",
    "Faculty of Medicine": "Lékařská fakulta",
    "Faculty of Science": "Přírodovědecká fakulta",
    "Faculty of Arts": "Filozofická fakulta",
    "Faculty of Education": "Pedagogická fakulta",
    "Faculty of Pharmacy": "Farmaceutická fakulta",
    "Faculty of Economics and Administration": "Ekonomicko-správní fakulta",
    "Faculty of Informatics": "Fakulta informatiky",
    "Faculty of Social Studies": "Fakulta sociálních studií",
    "Faculty of Sports Studies": "Fakulta sportovních studií",
}
_MUNI_PROGRAMME_RE = re.compile(r"/\d{4,6}-[a-z0-9-]+$")


def muni_listing_links(html: str, page_url: str) -> tuple[list[str], list[str]]:
    """(programme page URLs, category page URLs) linked from one listing page."""
    seed = next((s for s in MUNI_SEEDS if urlsplit(page_url).path.startswith(s)), None)
    programmes: list[str] = []
    categories: list[str] = []
    for href in re.findall(r'href="([^"#]+)"', html):
        url = urljoin(page_url, unescape(href))
        parts = urlsplit(url)
        if parts.netloc != "www.muni.cz" or seed is None or not parts.path.startswith(seed + "/"):
            continue
        if _MUNI_PROGRAMME_RE.search(parts.path):
            clean = f"{parts.scheme}://{parts.netloc}{parts.path}"
            if clean not in programmes:
                programmes.append(clean)
        elif parts.path.count("/") == seed.count("/") + 1 and url not in categories:
            categories.append(url)
    return programmes, categories


def parse_muni_programme(html: str, url: str) -> dict | None:
    """The facts one MUNI programme page states about itself."""
    title_tag = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    head = unescape(re.sub(r"\s+", " ", title_tag.group(1))).strip() if title_tag else ""
    title = head.split(" | ")[0]
    title = re.split(r"\s+[–-]\s+(?=[^–-]*(?:studium|studies)$)", title)[0].strip()
    if not title or title.lower() in {"study programme", "studijní program"}:
        return None
    text = page_text(html)
    english = "/en/" in urlsplit(url).path
    if english:
        faculty_en = _between(text, "Provided by", ("Type of studies",))
        faculty = MUNI_FACULTIES_EN.get(faculty_en or "", None)
        level_text = _between(text, "Type of studies", ("Mode",))
        language_text = (re.search(r"\bLanguage of instruction\s+(\w+)", text) or [None, None])[1]
        years = re.search(r"\bStandard length of studies\s+(\d+(?:[.,]\d)?)\s+year", text)
        tuition = re.search(r"\bTuition fees\s+(.{0,160}?\d[\d,. ]*\s?(?:EUR|CZK|€|Kč))", text)
    else:
        faculty = _between(text, "Zajišťuje", ("Typ studia",))
        level_text = _between(text, "Typ studia", ("Forma",))
        language_text = (re.search(r"\bVyučovací jazyk\s+(\w+)", text) or [None, None])[1]
        years = re.search(r"\bDoba studia\s+(\d+(?:[.,]\d)?)\s+(?:rok|let)", text)
        tuition = re.search(r"\bŠkolné\s+(.{0,160}?\d[\d,. ]*\s?(?:EUR|CZK|€|Kč))", text)
    level = MUNI_LEVELS.get((level_text or "").strip().lower())
    language = MUNI_LANGUAGES.get((language_text or "").strip().lower())
    forms = [
        form
        for form, pattern in (
            ("full-time", r"(?:prezenční|full-time)\s+(?:ano|Yes)"),
            ("combined", r"(?:kombinovaná|combined)\s+(?:ano|Yes)"),
            ("distance", r"(?:distanční|distance)\s+(?:ano|Yes)"),
        )
        if re.search(pattern, text)
    ]
    return {
        "officialProgrammeUrl": url,
        "titles": {"en" if english else "cs": title},
        "degree": level,
        "studyLanguage": language,
        "faculty": faculty,
        "studyForms": forms,
        "standardYears": years.group(1).replace(",", ".") if years else None,
        "tuitionText": tuition.group(1).strip() if tuition else None,
    }


def harvest_muni(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
    queue = [MUNI_BASE + seed for seed in MUNI_SEEDS]
    seen: set[str] = set()
    programme_urls: list[str] = []
    failures: list[dict] = []
    while queue:
        url = queue.pop(0)
        if url in seen or len(seen) > 120:
            continue
        seen.add(url)
        status, html = fetch(url)
        if status != 200 or not html:
            failures.append({"url": url, "status": status})
            continue
        programmes, categories = muni_listing_links(html, url)
        programme_urls.extend(item for item in programmes if item not in programme_urls)
        queue.extend(item for item in categories if item not in seen)
    log(f"muni: {len(seen)} listing page(s), {len(programme_urls)} programme page(s) listed")
    records = []
    # A listing names one page per programme, usually its bachelor's; the
    # follow-up master's and other levels are linked from that page itself.
    position = 0
    while position < len(programme_urls) and position < 2000:
        url = programme_urls[position]
        position += 1
        status, html = fetch(url)
        if status != 200 or not html:
            failures.append({"url": url, "status": status})
            continue
        record = parse_muni_programme(html, url)
        if record:
            records.append(record)
        linked, _categories = muni_listing_links(html, url)
        programme_urls.extend(item for item in linked if item not in programme_urls)
    log(f"muni: {len(records)} programme page(s) read")
    return {"programmes": records, "failures": failures, "listingPages": len(seen)}


# --------------------------------------------------------------------------- #
# Czech Technical University in Prague: Bílá kniha (official study plans)
# --------------------------------------------------------------------------- #

CVUT_BASE = "https://bilakniha.cvut.cz/cs/"
CVUT_LEVELS = {
    "bakalářské": "bachelor",
    "navazující magisterské": "master",
    "magisterské": "master",
    "doktorské": "doctorate",
}


def parse_cvut_faculty(html: str, page_url: str) -> list[dict]:
    """Programmes one Bílá kniha faculty page lists under its level headings."""
    heading = re.search(r"<h1>(.*?)</h1>", html, re.S)
    # The Děčín branches are the same faculties in the register.
    faculty = re.sub(r"\s+-\s+Děčín$", "", page_text(heading.group(1))) if heading else ""
    records = []
    for section in re.finditer(r"<em>([^<:]+):</em>\s*</p>\s*<ul>(.*?)</ul>", html, re.S):
        level = CVUT_LEVELS.get(page_text(section.group(1)).lower())
        if not level:
            continue
        for item in re.finditer(r'<li>\s*<a href="(program[^"]+\.html)">(.*?)</a>(.*?)</li>', section.group(2), re.S):
            title = page_text(item.group(2))
            records.append(
                {
                    "officialProgrammeUrl": urljoin(page_url, item.group(1)),
                    "titles": {"original": title},
                    "degree": level,
                    "studyLanguage": "en" if "angličtin" in page_text(item.group(3)) else "cs",
                    "faculty": faculty,
                }
            )
    return records


def harvest_cvut(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
    status, index = fetch(CVUT_BASE)
    failures: list[dict] = []
    if status != 200:
        return {"programmes": [], "failures": [{"url": CVUT_BASE, "status": status}], "listingPages": 1}
    pages = sorted({urljoin(CVUT_BASE, href) for href in re.findall(r'href="((?:f\d+d?|mu)\.html)"', index)})
    records: list[dict] = []
    for url in pages:
        status, html = fetch(url)
        if status != 200 or not html:
            failures.append({"url": url, "status": status})
            continue
        records.extend(parse_cvut_faculty(html, url))
    log(f"cvut: {len(pages)} faculty page(s), {len(records)} programme(s)")
    return {"programmes": records, "failures": failures, "listingPages": len(pages) + 1}


# --------------------------------------------------------------------------- #
# Silesian University in Opava: the programme finder on www.slu.cz
# --------------------------------------------------------------------------- #

SLU_FINDER = "https://www.slu.cz/slu/cz/obory?typ%5B%5D=B&typ%5B%5D=N&typ%5B%5D=D&jazyk%5B%5D={language}&_submit=Hledat&do=searchForm-submit"
SLU_LEVELS = {"B": "bachelor", "N": "master", "M": "master", "D": "doctorate"}
SLU_FACULTIES = {
    "FPF": "Filozoficko-přírodovědecká fakulta v Opavě",
    "OPF": "Obchodně podnikatelská fakulta v Karviné",
    "FVP": "Fakulta veřejných politik v Opavě",
}


def parse_slu_finder(html: str, language: str) -> list[dict]:
    """Each finder entry's title and its study variants (level, faculty, IS page)."""
    records = []
    for block in re.split(r'<div class="panel-group"', html)[1:]:
        heading = re.search(r'<div style="display: inline;" title="[^"]*">(.*?)</div>', block, re.S)
        if not heading:
            continue
        title = page_text(heading.group(1))
        for variant in re.finditer(r'<a id="issu-([A-Z])-[A-Z]"[^>]*?title="([^"]*)"[^>]*?href="([^"]+)"', block, re.S):
            level = SLU_LEVELS.get(variant.group(1))
            details = unescape(variant.group(2))
            faculty = (re.search(r"Fakulta:\s*([A-ZÚ]+)", details) or [None, ""])[1]
            url = unescape(variant.group(3))
            if not level or not url.startswith("https://"):
                continue
            records.append(
                {
                    "officialProgrammeUrl": url,
                    "titles": {language: title},
                    "degree": level,
                    "studyLanguage": language,
                    "faculty": SLU_FACULTIES.get(faculty, ""),
                }
            )
    unique = {(item["officialProgrammeUrl"], item["degree"]): item for item in records}
    return list(unique.values())


def harvest_slu(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
    records: list[dict] = []
    failures: list[dict] = []
    for language in ("cs", "en"):
        url = SLU_FINDER.format(language=language)
        status, html = fetch(url)
        if status != 200 or not html:
            failures.append({"url": url, "status": status})
            continue
        found = parse_slu_finder(html, language)
        if not found:
            # Readable here but empty on the CI runner (2026-10-03): say what came back.
            stated = re.search(r"Nalezeno záznamů:\s*\d+", page_text(html))
            failures.append(
                {"url": url, "status": status, "bytes": len(html), "stated": stated.group(0) if stated else None,
                 "panels": html.count('class="panel-group"')}
            )
        records.extend(found)
    log(f"slu: {len(records)} programme variant page(s); {failures if not records else ''}")
    return {"programmes": records, "failures": failures, "listingPages": 2}


# --------------------------------------------------------------------------- #
# IS/STAG schools: the public STAG web services list every accredited
# programme; its public ECTS catalogue has one page per programme.
# --------------------------------------------------------------------------- #

STAG_SCHOOLS = {
    # key: (institution, web-service base, public ECTS catalogue base)
    "vfu": ("msmt-vs_16000", "https://stagweb.vfu.cz", "https://stagweb.vfu.cz/ects"),
    "zcu": ("msmt-vs_23000", "https://stag-ws.zcu.cz", "https://portal.zcu.cz/ects"),
    "upce": ("msmt-vs_25000", "https://stag-ws.upce.cz", "https://portal.upce.cz/ects"),
    "ujep": ("msmt-vs_13000", "https://ws.ujep.cz", "https://portal.ujep.cz/ects"),
    "jcu": ("msmt-vs_12000", "https://stag-ws.jcu.cz", "https://wstag.jcu.cz/ects"),
    "utb": ("msmt-vs_28000", "https://stag-ws.utb.cz", "https://stag.utb.cz/ects"),
    "tul": ("msmt-vs_24000", "https://stag-ws.tul.cz", "https://stag.tul.cz/ects"),
}
STAG_LEVELS = {"bakalářský": "bachelor", "navazující": "master", "magisterský": "master", "doktorský": "doctorate"}
STAG_LANGUAGES = {
    "čeština": "cs", "angličtina": "en", "němčina": "de", "polština": "pl", "ruština": "ru",
    "slovenština": "sk", "francouzština": "fr", "španělština": "es", "italština": "it",
}


def academic_year(today: datetime | None = None) -> int:
    today = today or datetime.now(timezone.utc)
    return today.year if today.month >= 8 else today.year - 1


def stag_records(programmes: list[dict], faculties: dict[str, str], ects_base: str, year: int) -> list[dict]:
    """Programmes still accredited in ``year``, one ECTS catalogue page each."""
    records = []
    for item in programmes:
        level = STAG_LEVELS.get(str(item.get("typ") or "").strip().lower())
        language = STAG_LANGUAGES.get(str(item.get("jazyk") or "").strip().lower())
        title = str(item.get("nazev") or "").strip()
        faculty = str(item.get("fakulta") or "").strip()
        ended = str(item.get("neplatnyOd") or "9999")
        if not (level and language and title and faculty and item.get("stprIdno")):
            continue
        if ended <= str(year) or item.get("akreditaceZtracenaOdDate"):
            continue
        records.append(
            {
                "officialProgrammeUrl": f"{ects_base}/browser/{quote(faculty)}/{item['stprIdno']}?lang={'en' if language == 'en' else 'cs'}",
                "titles": {"original": title},
                "degree": level,
                "studyLanguage": language,
                "faculty": faculties.get(faculty, ""),
                "programmeCode": item.get("kod"),
                "studyForms": [str(item.get("forma") or "").strip().lower()] if item.get("forma") else [],
                "standardYears": item.get("stdDelka"),
            }
        )
    return records


def stag_page_names(html: str, title: str) -> bool:
    import unicodedata

    def fold(value: str) -> str:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", " ", value).strip()

    return bool(title) and fold(title) in fold(page_text(html))


def stag_harvester(key: str) -> Callable[..., dict]:
    _institution, ws_base, ects_base = STAG_SCHOOLS[key]

    def harvest(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
        year = academic_year()
        api = f"{ws_base}/ws/services/rest2"
        failures: list[dict] = []
        status, body = fetch(f"{api}/programy/getStudijniProgramy?rok={year}&outputFormat=JSON")
        try:
            programmes = json.loads(body).get("programInfo") or [] if status == 200 else []
        except json.JSONDecodeError:
            programmes = []
        if not programmes:
            failures.append({"url": f"{api}/programy/getStudijniProgramy", "status": status})
        faculties: dict[str, str] = {}
        status, body = fetch(f"{api}/ciselniky/getSeznamPracovist?typPracoviste=F&zkratka=%25&outputFormat=JSON")
        try:
            units = json.loads(body).get("pracoviste") or [] if status == 200 else []
        except json.JSONDecodeError:
            units = []
        # A unit renamed over time is listed once per name; the current one
        # has no end date and is read last.
        for unit in sorted(units, key=lambda item: item.get("platnostDo") is None):
            if unit.get("zkratka") and unit.get("nazev"):
                faculties[str(unit["zkratka"])] = str(unit["nazev"])
        accredited = stag_records(programmes, faculties, ects_base, year)
        # The ECTS catalogue shows a programme only while it has a study plan
        # for the year; for the others it answers 200 with an empty page (VFU
        # 103, a current bachelor's, 2026-10-03). Only a page that names the
        # programme is offered as its page.
        records = []
        for record in accredited:
            status, html = fetch(record["officialProgrammeUrl"])
            if status == 200 and len(html or "") >= 2048 and stag_page_names(html, record["titles"]["original"]):
                records.append(record)
        log(f"{key}: {len(programmes)} programme(s) in STAG, {len(accredited)} accredited in {year}, {len(records)} with a catalogue page")
        return {"programmes": records, "failures": failures, "listingPages": 2 + len(accredited)}

    return harvest


# --------------------------------------------------------------------------- #
# UIS schools: the public study-programme browser (katalog/plany.pl) lists,
# per faculty and intake period, each level's programmes with their teaching
# language and an information page per programme.
# --------------------------------------------------------------------------- #

UIS_SCHOOLS = {
    "mendelu": ("msmt-vs_43000", "https://is.mendelu.cz"),
    "vse": ("msmt-vs_31000", "https://insis.vse.cz"),
    "czu": ("msmt-vs_41000", "https://is.czu.cz"),
}
UIS_LEVELS = {
    "bakalářský": "bachelor",
    "magisterský navazující": "master",
    "navazující magisterský": "master",
    "magisterský": "master",
    "doktorský": "doctorate",
}
_UIS_PREFIX_RE = re.compile(r"^[A-Z]{1,3}-[A-Z0-9_]+\s+")


def _uis_cells(row_html: str) -> list[str]:
    return [page_text(cell) for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row_html, re.S)]


def uis_period_links(html: str, page_url: str, year: int) -> list[str]:
    """The intake periods of ``year``/``year+1`` (regular and doctoral) on a faculty page."""
    label = f"{year}/{year + 1}"
    links = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.S):
        if label in page_text(row):
            href = re.search(r'href="([^"]*poc_obdobi=\d+[^"]*)"', row)
            if href:
                links.append(urljoin(page_url, unescape(href.group(1))))
    return links


def uis_programmes(html: str, page_url: str) -> list[dict]:
    """Programme rows of one faculty / period / level page."""
    faculty = (re.search(r"Fakulta:\s*</td>\s*<td[^>]*>(.*?)</td>", html, re.S) or [None, ""])[1]
    level_text = (re.search(r"Typ studia:\s*</td>\s*<td[^>]*>(.*?)</td>", html, re.S) or [None, ""])[1]
    level = UIS_LEVELS.get(page_text(level_text).lower())
    if not level:
        return []
    table = re.search(r"Výběr studijního programu.*?<tbody\s*>(.*?)</tbody>", html, re.S)
    records = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table.group(1) if table else "", re.S):
        cells = _uis_cells(row)
        info = re.search(r'href="([^"]*program=\d+;info=1[^"]*)"', row)
        if len(cells) < 3 or not info:
            continue
        language = STAG_LANGUAGES.get(cells[2].strip().lower())
        title = _UIS_PREFIX_RE.sub("", cells[1]).strip()
        if not (language and title):
            continue
        records.append(
            {
                "officialProgrammeUrl": urljoin(page_url, unescape(info.group(1))),
                "titles": {"original": title},
                "degree": level,
                "studyLanguage": language,
                "faculty": page_text(faculty),
                "programmeCode": cells[0] or None,
            }
        )
    return records


def uis_harvester(key: str) -> Callable[..., dict]:
    _institution, base = UIS_SCHOOLS[key]

    def harvest(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
        year = academic_year()
        failures: list[dict] = []
        pages = 0

        def get(url: str) -> str:
            nonlocal pages
            pages += 1
            status, html = fetch(url)
            if status != 200 or not html:
                failures.append({"url": url, "status": status})
                return ""
            return html

        root = f"{base}/katalog/plany.pl?lang=cz"
        faculties = sorted({urljoin(root, unescape(h)) for h in re.findall(r'href="([^"]*plany\.pl\?fakulta=\d+;;lang=cz)"', get(root))})
        records: list[dict] = []
        for faculty_url in faculties:
            for period_url in uis_period_links(get(faculty_url), faculty_url, year):
                html = get(period_url)
                levels = {urljoin(period_url, unescape(h)) for h in re.findall(r'href="([^"]*typ_studia=\d+[^"]*)"', html)}
                for level_url in sorted(levels):
                    records.extend(uis_programmes(get(level_url), level_url))
        unique = {(item["officialProgrammeUrl"]): item for item in records}
        log(f"{key}: {len(faculties)} faculties, {len(unique)} programme(s) for {year}/{year + 1}")
        return {"programmes": list(unique.values()), "failures": failures, "listingPages": pages}

    return harvest


# --------------------------------------------------------------------------- #
# Academy of Performing Arts in Prague: each faculty's programme sitemap, and
# per programme page the name (h1#nazev) and level (p#typ_programu).
# --------------------------------------------------------------------------- #

AMU_FACULTIES = {
    "www.damu.cz": "Divadelní fakulta",
    "www.famu.cz": "Filmová a televizní fakulta",
    "www.hamu.cz": "Hudební a taneční fakulta",
}


def amu_level(text: str) -> str | None:
    lowered = text.strip().lower()
    if lowered.startswith("bakalář"):
        return "bachelor"
    if lowered.startswith(("magister", "navazující")):
        return "master"
    if lowered.startswith("doktor"):
        return "doctorate"
    return None


def parse_amu_programme(html: str, url: str) -> dict | None:
    name = re.search(r'<h1[^>]*id="nazev"[^>]*>(.*?)</h1>', html, re.S)
    level = re.search(r'<p[^>]*id="typ_programu"[^>]*>(.*?)</p>', html, re.S)
    if not (name and level):
        return None
    degree = amu_level(page_text(level.group(1)))
    title = page_text(name.group(1))
    if not (degree and title):
        return None
    return {
        "officialProgrammeUrl": url,
        "titles": {"original": title},
        "degree": degree,
        # The page does not state its teaching language; the title decides
        # (an English-taught programme is named in English in the register).
        "studyLanguage": "",
        "faculty": AMU_FACULTIES.get(urlsplit(url).netloc, ""),
    }


def harvest_amu(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
    records: list[dict] = []
    failures: list[dict] = []
    pages = 0
    for host in AMU_FACULTIES:
        sitemap = f"https://{host}/sitemap-programs.xml"
        status, body = fetch(sitemap)
        pages += 1
        if status != 200:
            failures.append({"url": sitemap, "status": status})
            continue
        for url in sorted({unescape(loc) for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)}):
            if "/cs/" not in url:
                continue
            status, html = fetch(url)
            pages += 1
            if status != 200 or not html:
                failures.append({"url": url, "status": status})
                continue
            record = parse_amu_programme(html, url)
            if record:
                records.append(record)
    log(f"amu: {len(records)} programme page(s) from {pages} read(s)")
    return {"programmes": records, "failures": failures, "listingPages": pages}


# --------------------------------------------------------------------------- #
# VŠB – Technical University of Ostrava: the applicants' programme list (Czech
# programmes, by level section, faculty abbreviation per entry) and the three
# English degree-study lists (by faculty heading).
# --------------------------------------------------------------------------- #

VSB_LIST_CS = "https://www.vsb.cz/cs/uchazec/studijni-programy/"
VSB_LISTS_EN = {
    "bachelor": "https://www.vsb.cz/en/study/degree-students/degree-studies/bachelor-degree/",
    "master": "https://www.vsb.cz/en/study/degree-students/degree-studies/master-degree/",
    "doctorate": "https://www.vsb.cz/en/study/degree-students/degree-studies/doctoral-degree/",
}
VSB_SECTIONS_CS = {
    "Bakalářské programy": "bachelor",
    "Navazující magisterské programy": "master",
    "Doktorské programy": "doctorate",
}
VSB_FACULTIES = {
    "FEI": "Fakulta elektrotechniky a informatiky",
    "HGF": "Hornicko-geologická fakulta",
    "FS": "Fakulta strojní",
    "FMT": "Fakulta materiálově-technologická",
    "FAST": "Fakulta stavební",
    "EKF": "Ekonomická fakulta",
    "FBI": "Fakulta bezpečnostního inženýrství",
}
VSB_FACULTIES_EN = (
    ("electrical engineering", "FEI"),
    ("mining", "HGF"),
    ("mechanical", "FS"),
    ("materials", "FMT"),
    ("civil", "FAST"),
    ("economics", "EKF"),
    ("safety", "FBI"),
)


def parse_vsb_cs(html: str, page_url: str) -> list[dict]:
    records = []
    marks = sorted(
        (match.start(), VSB_SECTIONS_CS[page_text(match.group(1))])
        for match in re.finditer(r"<h[2-4][^>]*>(.*?)</h[2-4]>", html, re.S)
        if page_text(match.group(1)) in VSB_SECTIONS_CS
    )
    for start, level in marks:
        following = [position for position, _ in marks if position > start]
        section = html[start : following[0] if following else len(html)]
        for entry in re.finditer(
            r"<a[^>]*href='([^']*programmeId=\d+[^']*)'[^>]*><span class='text'>(.*?)</span></a>\s*<span class='faculty[^']*'>(.*?)</span>",
            section,
            re.S,
        ):
            abbreviation = (re.search(r"\(([A-Z]+)\)", page_text(entry.group(3))) or [None, ""])[1]
            records.append(
                {
                    "officialProgrammeUrl": urljoin(page_url, unescape(entry.group(1))),
                    "titles": {"original": page_text(entry.group(2))},
                    "degree": level,
                    "studyLanguage": "cs",
                    "faculty": VSB_FACULTIES.get(abbreviation, ""),
                }
            )
    return records


def parse_vsb_en(html: str, page_url: str, level: str) -> list[dict]:
    records = []
    for block in re.split(r"(?=<h2\b)", html):
        heading = re.match(r"<h2[^>]*>(.*?)</h2>", block, re.S)
        if not heading:
            continue
        name = page_text(heading.group(1)).lower()
        faculty = next((VSB_FACULTIES[code] for key, code in VSB_FACULTIES_EN if key in name), "")
        if not faculty:
            continue
        for entry in re.finditer(r"<a href='([^']*programmeId=\d+[^']*)'><span class='text'>(.*?)</span>", block, re.S):
            records.append(
                {
                    "officialProgrammeUrl": urljoin(page_url, unescape(entry.group(1))),
                    "titles": {"original": re.sub(r"\s+", " ", page_text(entry.group(2)))},
                    "degree": level,
                    "studyLanguage": "en",
                    "faculty": faculty,
                }
            )
    return records


def harvest_vsb(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
    records: list[dict] = []
    failures: list[dict] = []
    status, html = fetch(VSB_LIST_CS)
    if status == 200 and html:
        records.extend(parse_vsb_cs(html, VSB_LIST_CS))
    else:
        failures.append({"url": VSB_LIST_CS, "status": status})
    for level, url in VSB_LISTS_EN.items():
        status, html = fetch(url)
        if status == 200 and html:
            records.extend(parse_vsb_en(html, url, level))
        else:
            failures.append({"url": url, "status": status})
    log(f"vsb: {len(records)} programme page(s)")
    return {"programmes": records, "failures": failures, "listingPages": 4}


# --------------------------------------------------------------------------- #
# UCT Prague (VŠCHT): Czech bachelor's and follow-up master's lists on
# studuj.vscht.cz and the English lists on study.vscht.cz. The programme code
# in each address states the level (B…/AB… bachelor, N…/AN… master); the
# page names the programme. Doctoral programmes are listed only by script.
# --------------------------------------------------------------------------- #

VSCHT_LISTS = (
    ("https://studuj.vscht.cz/studijni-programy/bakalarske/", "cs"),
    ("https://studuj.vscht.cz/studijni-programy/navazujici-magisterske", "cs"),
    ("https://study.vscht.cz/degree-programmes/bachelor", "en"),
    ("https://study.vscht.cz/degree-programmes/master", "en"),
)
_VSCHT_LINK_RE = re.compile(r'href="([^"#]*(?:/program/([A-Z]+)\d+|/degree-programmes/(?:bachelor|master)/([a-z]+)\d+))"')


def vscht_level(code: str) -> str | None:
    code = code.upper()
    if code in {"B", "AB"}:
        return "bachelor"
    if code in {"N", "AN"}:
        return "master"
    return None


def vscht_title(html: str, language: str) -> str:
    if language == "cs":
        heading = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        return page_text(heading.group(1)) if heading else ""
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
    text = page_text(title.group(1)) if title else ""
    return re.sub(r"\s+A[BN]\d+\s+-\s+Study at UCT Prague$", "", text).strip() if " - Study at UCT Prague" in text else ""


def harvest_vscht(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
    records: list[dict] = []
    failures: list[dict] = []
    pages = 0
    for list_url, language in VSCHT_LISTS:
        status, html = fetch(list_url)
        pages += 1
        if status != 200 or not html:
            failures.append({"url": list_url, "status": status})
            continue
        links = {}
        for match in _VSCHT_LINK_RE.finditer(html):
            links[urljoin(list_url, unescape(match.group(1)))] = vscht_level(match.group(2) or match.group(3) or "")
        for url, level in sorted(links.items()):
            if not level:
                continue
            status, page = fetch(url)
            pages += 1
            title = vscht_title(page, language) if status == 200 and page else ""
            if not title:
                failures.append({"url": url, "status": status})
                continue
            records.append(
                {"officialProgrammeUrl": url, "titles": {"original": title}, "degree": level, "studyLanguage": language, "faculty": ""}
            )
    log(f"vscht: {len(records)} programme page(s)")
    return {"programmes": records, "failures": failures, "listingPages": pages}


# --------------------------------------------------------------------------- #
# University of Hradec Králové: the paged applicants' programme list; each
# programme page states "Typ studia: … Vyučovací jazyk: …" and its faculty is
# the first path segment.
# --------------------------------------------------------------------------- #

UHK_LIST = "https://www.uhk.cz/cs/univerzita-hradec-kralove/prijimaci-zkousky/studijni-programy"
UHK_FACULTIES = {
    "fakulta-informatiky-a-managementu": "Fakulta informatiky a managementu",
    "filozoficka-fakulta": "Filozofická fakulta",
    "pedagogicka-fakulta": "Pedagogická fakulta",
    "prirodovedecka-fakulta": "Přírodovědecká fakulta",
}
UHK_LEVELS = {
    "bakalářské": "bachelor",
    "navazující magisterské": "master",
    "magisterské navazující": "master",
    "magisterské": "master",
    "doktorské": "doctorate",
}
_UHK_LINK_RE = re.compile(r'href="(/cs/([a-z-]+)/prijimaci-zkousky/studijni-programy/[a-z0-9-]+)"')


def parse_uhk_programme(html: str, url: str) -> dict | None:
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    text = page_text(html)
    level = UHK_LEVELS.get(((re.search(r"Typ studia:\s*(.+?)\s+Forma studia:", text) or [None, ""])[1]).strip().lower())
    language = STAG_LANGUAGES.get(((re.search(r"Vyučovací jazyk:\s*(\w+)", text) or [None, ""])[1]).strip().lower())
    title = page_text(heading.group(1)) if heading else ""
    if not (title and level and language):
        return None
    segment = urlsplit(url).path.split("/")[2]
    return {
        "officialProgrammeUrl": url,
        "titles": {"original": title},
        "degree": level,
        "studyLanguage": language,
        "faculty": UHK_FACULTIES.get(segment, ""),
    }


def harvest_uhk(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
    links: list[str] = []
    failures: list[dict] = []
    pages = 0
    for number in range(1, 40):
        url = UHK_LIST if number == 1 else f"{UHK_LIST}?rjPC22%3ApageNumber={number}&ramJetParameterContext=rjPC22"
        status, html = fetch(url)
        pages += 1
        if status != 200 or not html:
            failures.append({"url": url, "status": status})
            break
        found = [urljoin(UHK_LIST, match.group(1)) for match in _UHK_LINK_RE.finditer(html) if match.group(2) in UHK_FACULTIES]
        new = [item for item in dict.fromkeys(found) if item not in links]
        if not new:
            break
        links.extend(new)
    records = []
    for url in links:
        status, html = fetch(url)
        pages += 1
        record = parse_uhk_programme(html, url) if status == 200 and html else None
        if record:
            records.append(record)
        else:
            failures.append({"url": url, "status": status})
    log(f"uhk: {len(links)} programme page(s) listed, {len(records)} read")
    return {"programmes": records, "failures": failures, "listingPages": pages}


# --------------------------------------------------------------------------- #
# University of Ostrava: one list of every specialisation with its programme
# name, faculty, level, form and duration, each linking its detail page.
# --------------------------------------------------------------------------- #

OSU_LIST = "https://www.osu.cz/studijniobory"
OSU_LEVELS = {
    "bakalářské": "bachelor",
    "navazující magisterské": "master",
    "magisterské navazující": "master",
    "magisterské": "master",
    "doktorské": "doctorate",
}


def parse_osu_list(html: str, page_url: str = OSU_LIST) -> list[dict]:
    records = []
    for block in re.split(r'<div class="w100 bb">', html)[1:]:
        link = re.search(r'<a href="([^"]*specializaceid=\d+)"[^>]*>(.*?)</a>', block, re.S)
        programme = re.search(r'<div class="w100">\((.*?)\)', block, re.S)
        faculty = re.search(r'<div class="w20 lfloat">(.*?)</div>', block, re.S)
        level = re.search(r'<div class="w15 rfloat">(.*?)</div>', block, re.S)
        if not (link and level):
            continue
        degree = OSU_LEVELS.get(page_text(level.group(1)).lower())
        if not degree:
            continue
        titles = {"original": page_text(link.group(2))}
        if programme and page_text(programme.group(1)) != titles["original"]:
            titles["programme"] = page_text(programme.group(1))
        url = urljoin(page_url.rstrip("/") + "/", unescape(link.group(1)))
        records.append(
            {
                "officialProgrammeUrl": url,
                "titles": titles,
                "degree": degree,
                "studyLanguage": "",
                "faculty": page_text(faculty.group(1)) if faculty else "",
            }
        )
    unique = list({(item["officialProgrammeUrl"], item["degree"]): item for item in records}.values())
    # A programme taught in several specialisations has no single page of its
    # own here; its name binds only where one specialisation carries it.
    counts: dict[tuple, int] = {}
    for item in unique:
        if "programme" in item["titles"]:
            key = (item["titles"]["programme"], item["degree"], item["faculty"])
            counts[key] = counts.get(key, 0) + 1
    for item in unique:
        if "programme" in item["titles"] and counts[(item["titles"]["programme"], item["degree"], item["faculty"])] > 1:
            del item["titles"]["programme"]
    return unique


def harvest_osu(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
    status, html = fetch(OSU_LIST)
    if status != 200 or not html:
        return {"programmes": [], "failures": [{"url": OSU_LIST, "status": status}], "listingPages": 1}
    records = parse_osu_list(html)
    log(f"osu: {len(records)} specialisation page(s)")
    return {"programmes": records, "failures": [], "listingPages": 1}


# --------------------------------------------------------------------------- #
# Brno University of Technology: the students' programme list names every
# programme per faculty under its level heading, with its teaching language.
# --------------------------------------------------------------------------- #

VUT_LIST = "https://www.vut.cz/studenti/programy"
VUT_LEVELS = {"bakalářský": "bachelor", "magisterský navazující": "master", "magisterský": "master", "doktorský": "doctorate"}


def parse_vut_list(html: str, page_url: str = VUT_LIST) -> list[dict]:
    records = []
    for faculty_block in re.split(r'<li class="c-faculties-list__item">', html)[1:]:
        faculty = page_text((re.search(r'<h2 class="b-faculty-list__title[^"]*">(.*?)</h2>', faculty_block, re.S) or [None, ""])[1])
        parts = re.split(r'<h3 class="c-programmes__title[^"]*">(.*?)</h3>', faculty_block)
        for heading, section in zip(parts[1::2], parts[2::2]):
            level = VUT_LEVELS.get(page_text(heading).lower())
            if not level:
                continue  # "Mezinárodně uznávaný" (MBA-type courses) are not register programmes
            for item in re.split(r'<li class="c-programmes__item">', section)[1:]:
                link = re.search(r'<a href="(/studenti/programy/program/\d+)"[^>]*>(.*?)</a>', item, re.S)
                if not link:
                    continue
                meta = [page_text(value).lower() for value in re.findall(r'<span class="b-branch__meta-item">(.*?)</span>', item, re.S)]
                title = re.sub(r"\s*\([A-Z0-9][A-Z0-9_+-]*\)\s*$", "", page_text(link.group(2))).strip()
                records.append(
                    {
                        "officialProgrammeUrl": urljoin(page_url, link.group(1)),
                        "titles": {"original": title},
                        "degree": level,
                        "studyLanguage": "en" if "angličtina" in meta else "cs",
                        "faculty": faculty,
                    }
                )
    return records


def harvest_vut(fetch: FetchPage, log: Callable[[str], None] = print) -> dict:
    status, html = fetch(VUT_LIST)
    if status != 200 or not html:
        return {"programmes": [], "failures": [{"url": VUT_LIST, "status": status}], "listingPages": 1}
    records = parse_vut_list(html)
    log(f"vut: {len(records)} programme page(s)")
    return {"programmes": records, "failures": [], "listingPages": 1}


# --------------------------------------------------------------------------- #
# Charles University: the SIS catalogue of accredited study programmes, 50 per
# page, each row stating faculty, level, name, teaching language and form. The
# catalogue redirects in a loop without a session cookie, as browsers keep one.
# --------------------------------------------------------------------------- #

CUNI_LIST = "https://is.cuni.cz/studium/v4/{lang}/anonymous/study-programs/program"
CUNI_LEVELS = {
    "bakalářské": "bachelor", "navazující magisterské": "master", "magisterské": "master", "doktorské": "doctorate",
    "bachelor": "bachelor", "bachelor's": "bachelor", "follow-up master": "master", "follow-up master's": "master",
    "master": "master", "master's": "master", "doctoral": "doctorate",
}
CUNI_LANGUAGES = {**STAG_LANGUAGES, "czech": "cs", "english": "en", "german": "de", "russian": "ru", "french": "fr", "spanish": "es"}


def parse_cuni_page(html: str, page_url: str) -> list[dict]:
    records = []
    for row in re.findall(r'<tr class="js_table-row table__row">(.*?)</tr>', html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 4:
            continue
        link = re.search(r'<a href="([^"]*accreditation/\d+)"[^>]*>(.*?)</a>', cells[2], re.S)
        level = CUNI_LEVELS.get(page_text(cells[1]).lower())
        language = CUNI_LANGUAGES.get(page_text(cells[3]).lower())
        if not (link and level and language):
            continue
        records.append(
            {
                "officialProgrammeUrl": urljoin(page_url, unescape(link.group(1))),
                "titles": {"original": page_text(link.group(2))},
                "degree": level,
                "studyLanguage": language,
                "faculty": page_text(cells[0]),
            }
        )
    return records


def _session_fetch() -> FetchPage:
    import http.cookiejar
    import urllib.request

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CzechUniApplyBot; +https://czech-uni-application.com/contact)"}

    def fetch(url: str) -> tuple[int, str]:
        try:
            with opener.open(urllib.request.Request(url, headers=headers), timeout=60) as response:
                return int(response.status), response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return int(getattr(exc, "code", 0) or 0), ""

    return fetch


def harvest_cuni(fetch: FetchPage, log: Callable[[str], None] = print, session: FetchPage | None = None) -> dict:
    session = throttled(session or _session_fetch())
    records: dict[str, dict] = {}
    failures: list[dict] = []
    pages = 0
    for lang in ("cs", "en"):
        base = CUNI_LIST.format(lang=lang)
        for number in range(1, 80):
            url = base if number == 1 else f"{base}?page={number}"
            status, html = session(url)
            pages += 1
            if status != 200 or not html:
                failures.append({"url": url, "status": status})
                break
            found = parse_cuni_page(html, url)
            new = [item for item in found if item["officialProgrammeUrl"] not in records]
            for item in new:
                records[item["officialProgrammeUrl"]] = item
            if not new:
                break
    log(f"cuni: {len(records)} accreditation page(s) from {pages} listing page(s)")
    return {"programmes": list(records.values()), "failures": failures, "listingPages": pages}


ADAPTERS = {
    "cuni": ("msmt-vs_11000", "catalogue-cuni.json", harvest_cuni),
    "vut": ("msmt-vs_26000", "catalogue-vut.json", harvest_vut),
    "osu": ("msmt-vs_17000", "catalogue-osu.json", harvest_osu),
    "uhk": ("msmt-vs_18000", "catalogue-uhk.json", harvest_uhk),
    "vscht": ("msmt-vs_22000", "catalogue-vscht.json", harvest_vscht),
    "vsb": ("msmt-vs_27000", "catalogue-vsb.json", harvest_vsb),
    "amu": ("msmt-vs_51000", "catalogue-amu.json", harvest_amu),
    **{key: (value[0], f"catalogue-{key}.json", stag_harvester(key)) for key, value in STAG_SCHOOLS.items()},
    **{key: (value[0], f"catalogue-{key}.json", uis_harvester(key)) for key, value in UIS_SCHOOLS.items()},
    "muni": ("msmt-vs_14000", "catalogue-muni.json", harvest_muni),
    "slu": ("msmt-vs_19000", "catalogue-slu.json", harvest_slu),
    "cvut": ("msmt-vs_21000", "catalogue-cvut.json", harvest_cvut),
}


def throttled(fetch: FetchPage, spacing: float = 1.0) -> FetchPage:
    last: dict[str, float] = {}

    def call(url: str) -> tuple[int, str]:
        host = urlsplit(url).netloc
        wait = spacing - (time.monotonic() - last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        last[host] = time.monotonic()
        return fetch(url)

    return call


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--school", action="append", choices=sorted(ADAPTERS), help="default: every school")
    parser.add_argument("--live", action="store_true", required=True)
    args = parser.parse_args(argv)
    from engine.transport import fetch_official_page

    def fetch(url: str) -> tuple[int, str]:
        result = fetch_official_page(url, allow_browser=False)
        return result.status, result.body

    from concurrent.futures import ThreadPoolExecutor

    def read(key: str):
        try:
            return key, ADAPTERS[key][2](throttled(fetch)), None
        except Exception as exc:  # one school's outage must not stop the others
            return key, None, exc

    # Schools are different hosts, each spaced on its own, so they are read
    # side by side; one school's pages are still read one at a time.
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(read, args.school or sorted(ADAPTERS)))
    for key, result, error in outcomes:
        institution_id, filename, _harvest = ADAPTERS[key]
        if error is not None:
            print(f"::warning title=Programme catalogue::{key}: {type(error).__name__}: {error}")
            continue
        path = OUT_DIR / filename
        previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        records = result["programmes"]
        # A catalogue read that lost most of its pages is not written over a
        # complete one; the next run tries again (A100: coverage only rises).
        if len(records) < 0.8 * len(previous.get("programmes") or []):
            print(
                f"::warning title=Programme catalogue::{key}: read {len(records)} programme page(s), "
                f"previously {len(previous['programmes'])}; kept the previous catalogue"
            )
            continue
        payload = {
            "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dataClass": "school_programme_catalogue",
            "institutionId": institution_id,
            "note": (
                "One record per programme page of the school's own catalogue, with the facts that page "
                "states. Read by resolve_programme_links.py as harvested candidates."
            ),
            "listingPages": result["listingPages"],
            "failures": result["failures"],
            "programmes": sorted(records, key=lambda item: (item["officialProgrammeUrl"], str(item.get("degree")))),
        }
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"school": key, "programmes": len(records), "failures": len(result["failures"])}), flush=True)
    return 0


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())

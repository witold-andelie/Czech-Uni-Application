"""EURAXESS as a discovery source for Czech research vacancies (owner decision 2026-10-03).

EURAXESS carries vacancies that Czech universities post nowhere else we read:
doctoral studentship topics (ČVUT faculties, VŠCHT), faculty and research-centre
postdocs (CUNI Law, MUNI Medicine, CEITEC). Facts come from the EURAXESS notice;
the employer is the "Organisation/Company" it names, resolved to an MŠMT
university; the application target is an address on that university's own
domains found in the notice. EURAXESS itself is never the application target
(a record without an official address is kept but not published), and a
vacancy that a direct university source already carries is not published twice
(auto_review.py). Non-university employers (CAS institutes, ELI, CDV) are kept
out until the catalogue models research employers.
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
    "silesian university": "msmt-vs_16000",
    "prague university of economics and business": "msmt-vs_31000",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", unescape(str(text or ""))).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


@lru_cache(maxsize=1)
def name_index() -> dict[str, str]:
    """Normalised university names (register, studyin cs/en, aliases) -> employer id."""
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

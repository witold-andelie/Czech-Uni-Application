"""Public research institutions as research-job employers (owner decision 2026-10-03).

The official MŠMT register of public research institutions (Rejstřík
veřejných výzkumných institucí, Act No. 341/2005 Coll.) lists every v. v. i.
with its name, website, IČO, seat, founder and the day it was registered; a
deleted institution is marked "VYMAZÁNA" and is not kept. The Czech Academy of
Sciences' English list of its institutes supplies their official English names,
matched by website host. Nothing else is inferred: an institute without an
English name on that list keeps its Czech name in every locale, as a
university without a recorded translation does.

Usage:
    python harvest_research_institutions.py --live
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sources" / "research-institutions.json"
REGISTER_URL = "https://rvvi.msmt.cz/"
REGISTER_LIST = "https://rvvi.msmt.cz/select.php"
REGISTER_FORM = "nazev_vvi=&ic=&reditel=&kraj=&hlavni_cinnost=&dalsi_cinnost=&zrizovatel=&rok_zapisu="
AVCR_INSTITUTES_EN = "https://www.avcr.cz/en/about-us/cas-structure/research-institutes/"
FetchPage = Callable[[str], "tuple[int, str]"]
PostForm = Callable[[str, str], "tuple[int, str]"]


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def web_host(url: str) -> str:
    host = urlsplit(url if "://" in url else f"http://{url}").netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def city_of(seat: str) -> str:
    """The town of a register seat 'Street 1, Town 2, 123 45' ('Praha 1' -> 'Praha')."""
    parts = [part.strip() for part in seat.split(",") if part.strip()]
    town = next((part for part in reversed(parts) if not re.fullmatch(r"\d{3}\s?\d{2}", part)), "")
    return re.sub(r"\s+\d+$", "", re.sub(r"\s*-\s*.*$", "", town)).strip()


def parse_register(html: str) -> list[dict]:
    records = []
    for block in re.split(r"<hr\s*/?>", html):
        name = re.search(r'<h2><a href="(detail\.php\?ic=(\d+))"[^>]*>(.*?)</a></h2>', block, re.S)
        if not name:
            continue
        status = _text((re.search(r'<div class="important">(.*?)</div>', block, re.S) or [None, ""])[1])
        if status:
            continue  # "VYMAZÁNA": deleted from the register
        website = re.search(r"<td>Webové stránky</td>\s*<td[^>]*>\s*<a href=\"([^\"]+)\"", block, re.S)
        seat = _text((re.search(r"<td>Sídlo</td>\s*<td[^>]*>(.*?)</td>", block, re.S) or [None, ""])[1])
        founder = _text((re.search(r"<td>Zřizovatel</td>\s*<td[^>]*>(.*?)</td>", block, re.S) or [None, ""])[1])
        registered = re.search(r"zápis:\s*(\d{2})\.\s*(\d{2})\.\s*(\d{4})", _text(block))
        ico = name.group(2)
        url = unescape(website.group(1)).strip() if website else ""
        records.append(
            {
                "id": f"rvvi-{ico}",
                "officialName": _text(name.group(3)),
                "officialNameEn": None,
                "legalType": "research_institute",
                "ownership": "public",
                "ownershipOriginal": "veřejná výzkumná instituce",
                "ico": ico,
                "officialUrl": url or None,
                "webHost": web_host(url) if url else None,
                "seat": seat,
                "city": city_of(seat),
                "founder": founder.split(",")[0].strip() if founder else None,
                "registeredOn": f"{registered.group(3)}-{registered.group(2)}-{registered.group(1)}" if registered else None,
                "source": {"registryUrl": REGISTER_URL, "detailUrl": f"{REGISTER_URL}{name.group(1)}", "law": "zákon č. 341/2005 Sb."},
            }
        )
    return records


def _street(address: str) -> str:
    import unicodedata

    first = address.split(",")[0]
    first = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", first).strip()


def avcr_english_names(html: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """The Academy's institute list: (website host -> names, street -> names).

    Each row reads "<a href=site>Name of the CAS</a>, Street 1, 123 45 Town"; a
    few rows link another host than the register records (or a malformed one),
    and then the street address, which both lists state, identifies the row.
    """
    by_host: dict[str, list[str]] = {}
    by_street: dict[str, list[str]] = {}
    for href, label, after in re.findall(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>([^<]*)', html, re.S):
        name = _text(label)
        if not (" of the CAS" in name or name.endswith(" CAS")):
            continue
        by_host.setdefault(web_host(href), []).append(name)
        street = _street(_text(after).lstrip(", "))
        if street:
            by_street.setdefault(street, []).append(name)
    return by_host, by_street


def english_name(record: dict, records: list[dict], by_host: dict, by_street: dict) -> str | None:
    """The one English name a register entry's host or street identifies.

    Institutes share hosts (biomed.cas.cz) and campuses (Vídeňská 1083, Krč):
    a key that more than one entry of either list carries names nobody.
    """
    host = record.get("webHost") or ""
    street = _street(record.get("seat") or "")
    same_host = sum(1 for other in records if (other.get("webHost") or "") == host)
    same_street = sum(1 for other in records if _street(other.get("seat") or "") == street)
    if host and same_host == 1 and len(set(by_host.get(host, []))) == 1:
        return by_host[host][0]
    if street and same_street == 1 and len(set(by_street.get(street, []))) == 1:
        return by_street[street][0]
    return None


def harvest(fetch: FetchPage, post: PostForm, log: Callable[[str], None] = print) -> dict:
    status, html = post(REGISTER_LIST, REGISTER_FORM)
    if status != 200 or "detail.php?ic=" not in (html or ""):
        raise RuntimeError(f"register list unreadable (HTTP {status})")
    records = parse_register(html)
    status, english = fetch(AVCR_INSTITUTES_EN)
    by_host, by_street = avcr_english_names(english) if status == 200 else ({}, {})
    for record in records:
        record["officialNameEn"] = english_name(record, records, by_host, by_street)
        if record["officialNameEn"]:
            record["officialNameEnSource"] = AVCR_INSTITUTES_EN
    log(f"research institutions: {len(records)} in the register, {sum(1 for r in records if r['officialNameEn'])} with an English name")
    return {"institutions": records}


def _request(url: str, data: str | None = None) -> tuple[int, str]:
    import urllib.request

    request = urllib.request.Request(
        url,
        data=data.encode("utf-8") if data is not None else None,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; CzechUniApplyBot; +https://czech-uni-application.com/contact)",
            **({"Content-Type": "application/x-www-form-urlencoded"} if data is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return int(getattr(exc, "code", 0) or 0), ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args(argv)
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
    result = harvest(lambda url: _request(url), lambda url, form: _request(url, form))
    if len(result["institutions"]) < 0.8 * len(previous.get("institutions") or []):
        print("::warning title=Research institutions::the register returned far fewer institutions; kept the previous list")
        return 0
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_register_extract",
        "sourceUrl": REGISTER_URL,
        "note": (
            "Public research institutions (v. v. i.) from the MŠMT register, Act No. 341/2005 Coll.; "
            "deleted institutions are left out. English names are the Czech Academy of Sciences' own, "
            "matched by website host. Research-job employers that are not universities."
        ),
        "counts": {"institutions": len(result["institutions"])},
        "institutions": sorted(result["institutions"], key=lambda item: item["id"]),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload["counts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Attach public-HEI websites from the archived MŠMT list. Do not guess private/state URLs."""
from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
HTML = ROOT / "work" / "raw" / "2026-09-06" / "msmt-public-websites.html"
SOURCE_URL = "https://archiv.msmt.gov.cz/areas-of-work/tertiary-education/public-higher-education-institutions-websites"

LINK = re.compile(r'<a href="(https?://[^"]+)"[^>]*>(.*?)</a>', re.S)


def clean(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def czech_name(label: str) -> str:
    if "(" in label:
        return label.split("(", 1)[0].strip()
    return label.strip()


def normalize(name: str) -> str:
    return re.sub(r"[^a-záčďéěíňóřšťúůýž]", "", name.casefold())


def parse_links(html: str) -> list[tuple[str, str]]:
    pairs = []
    for href, inner in LINK.findall(html):
        if "archiv.msmt" in href or "facebook.com" in href or "twitter.com" in href:
            continue
        if "msmt.gov.cz" in href or "termsfeed" in href:
            continue
        label = clean(inner)
        czech = czech_name(label)
        if len(czech) < 8:
            continue
        if "univerzit" not in czech.casefold() and "akademi" not in czech.casefold() and "vysok" not in czech.casefold() and "učení" not in czech.casefold():
            continue
        pairs.append((czech, href.rstrip("/")))
    return pairs


ALIASES = {
    "Mendelova univerzita v Brně": "Mendelova zemědělská universita v Brně",
}


def score(official: str, listed: str) -> int:
    a, b = normalize(official), normalize(listed)
    alias = ALIASES.get(official)
    if alias:
        a = normalize(alias)
    if not a or not b:
        return 0
    if a == b or a in b or b in a:
        return min(len(a), len(b))
    return 0


def main() -> None:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    links = parse_links(HTML.read_text(encoding="utf-8"))
    matched = 0
    for item in payload["institutions"]:
        best = None
        best_score = 0
        for czech, href in links:
            current = score(item["officialName"], czech)
            if current > best_score:
                best_score = current
                best = href
        if best and best_score >= 12 and item["ownership"] == "public" and not item.get("officialUrl"):
            item["officialUrl"] = best
            item["officialUrlSource"] = SOURCE_URL
            item["officialUrlNote"] = "URL copied from the archived MŠMT public-HEI websites page because the live CSV had no host. Not re-checked as the current homepage."
            matched += 1
    payload["websiteMerge"] = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceUrl": SOURCE_URL,
        "matchedPublicWebsites": matched,
        "extraction": "Scrapling 0.4.9 GET of archived MŠMT page; name match to register list",
    }
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matchedPublicWebsites": matched, "total": payload["counts"]["total"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

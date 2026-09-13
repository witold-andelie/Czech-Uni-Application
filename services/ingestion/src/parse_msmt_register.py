"""Parse the MŠMT Registr VŠ HTML list into a structured baseline."""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "work" / "raw" / "2026-09-06" / "msmt-cvslist.html"
OUT = ROOT / "data" / "sources" / "msmt-hei-baseline.json"

OWNERSHIP = {
    "veřejná": "public",
    "státní": "state",
    "soukromá": "private",
}
LEGAL = {
    "univerzitní": "university",
    "neuniverzitní": "non_university",
}

ROW = re.compile(
    r'<tr><td class="td_border">(.*?)</td>'
    r'<td class="td_border">(.*?)</td>'
    r'<td class="td_border">(.*?)</td>'
    r'<td class="td_border">(.*?)</td>'
    r'<td class="td_border"><input type="submit" name="[^"]+" value="Detail" '
    r'id="ContentPlaceHolder1_(VS_[^"]+)"',
    re.S,
)


def clean(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse(html: str) -> list[dict]:
    records = []
    for name, legal, forma, kraj, code in ROW.findall(html):
        records.append(
            {
                "id": f"msmt-{code.lower()}",
                "msmtCode": code,
                "officialName": clean(name),
                "legalType": LEGAL.get(clean(legal), "unknown"),
                "legalTypeOriginal": clean(legal),
                "ownership": OWNERSHIP.get(clean(forma), "unknown"),
                "ownershipOriginal": clean(forma),
                "region": clean(kraj),
                "country": "CZ",
                "cscseLookupStatus": "unverified",
                "officialUrl": None,
                "source": {
                    "registryUrl": "https://regvssp.msmt.cz/registrvssp/cvslist.aspx",
                    "law": "zákon č. 111/1998 Sb., § 87",
                },
            }
        )
    records.sort(key=lambda item: item["officialName"].casefold())
    return records


def main() -> None:
    html = RAW.read_text(encoding="utf-8")
    records = parse(html)
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_register_extract",
        "catalogKind": "baseline_not_published",
        "sourceUrl": "https://regvssp.msmt.cz/registrvssp/cvslist.aspx",
        "sourceTitle": "Registr vysokých škol a uskutečňovaných studijních programů",
        "httpStatus": 200,
        "extraction": "Scrapling 0.4.9 GET; HTML table parse",
        "sourceSha256": digest,
        "note": "Names, legal type, ownership and region come from the official MŠMT register list. Websites, programmes, tuition, deadlines and CSCSE status are not on this page and are not invented.",
        "counts": {
            "total": len(records),
            "public": sum(item["ownership"] == "public" for item in records),
            "private": sum(item["ownership"] == "private" for item in records),
            "state": sum(item["ownership"] == "state" for item in records),
            "university": sum(item["legalType"] == "university" for item in records),
            "nonUniversity": sum(item["legalType"] == "non_university" for item in records),
        },
        "institutions": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["counts"], ensure_ascii=False))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

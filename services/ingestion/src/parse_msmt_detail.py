"""Parse MŠMT institution detail HTML for official English names and websites."""
from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "work" / "raw" / "2026-09-06"
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"

ROW = re.compile(
    r'<td class="td_bolder5">([^<]+)</td><td class="td_border2">(.*?)</td>',
    re.S,
)


def clean(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def href(value: str) -> str | None:
    match = re.search(r"href=['\"](https?://[^'\"]+)['\"]", value, re.I)
    return match.group(1).rstrip("/") if match else None


def parse_detail(html: str) -> dict[str, str | None]:
    cut = html.find("Fakulty vysoké školy")
    if cut == -1:
        cut = html.find("Studijní programy a studijní obory")
    chunk = html[:cut] if cut != -1 else html
    fields: dict[str, str] = {}
    for label, value in ROW.findall(chunk):
        key = clean(label)
        if key not in fields:
            fields[key] = value
    rid = clean(fields.get("RID školy:", "") or fields.get("RID školy", ""))
    return {
        "rid": rid,
        "msmtCode": f"VS_{rid}" if rid else None,
        "officialName": clean(fields.get("Název školy:", "")),
        "officialNameEn": clean(fields.get("Název školy (EN):", "")) or None,
        "officialUrl": href(fields.get("Webové stránky:", "") or ""),
        "ico": clean(fields.get("IČ:", "")) or None,
        "seat": clean(fields.get("Sídlo školy:", "")) or None,
    }


def main() -> None:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    by_code = {item["msmtCode"].upper(): item for item in payload["institutions"]}
    matched = 0
    for path in sorted(RAW.glob("msmt-detail-*.html")):
        parsed = parse_detail(path.read_text(encoding="utf-8", errors="replace"))
        code = (parsed.get("msmtCode") or "").upper()
        item = by_code.get(code)
        if not item:
            continue
        matched += 1
        if parsed.get("officialNameEn"):
            item["officialNameEn"] = parsed["officialNameEn"]
        item["detailSource"] = "https://regvssp.msmt.cz/registrvssp/cvsdet.aspx"
        item["detailEvidence"] = str(path.relative_to(ROOT)).replace("\\", "/")
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"detailsMerged": matched}, ensure_ascii=False))


if __name__ == "__main__":
    main()

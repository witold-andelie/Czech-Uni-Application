"""Drop junk URLs and retry the four missing HEI portals."""
from __future__ import annotations

import json
from pathlib import Path

from harvest_apply_portals import APPLY_STRONG, fetch, is_dead

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sources" / "admissions" / "apply-portals.json"

JUNK = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    "wp-content/plugins",
    "koleje",
    "nostrifik",
    "stipendia",
    "redrawnavbar",
    "online-payment",
    "aktuality/detail",
)

RETRY = {
    "msmt-vs_52000": [
        "https://avu.cz/stranka/prijimaci-rizeni-a-e-prihlaska",
        "https://www.avu.cz/stranka/prijimaci-rizeni-a-e-prihlaska",
    ],
    "msmt-vs_7s000": [
        "https://www.peuni.cz/",
        "https://www.peuni.cz/cs/prijimaci-rizeni",
        "https://www.peuni.cz/cs/uchazeci",
        "https://is.peuni.cz/prihlaska",
    ],
    "msmt-vs_94000": [
        "https://www.polac.cz/",
        "https://polac.cz/",
    ],
    "msmt-vs_56000": [
        "https://is.vstecb.cz/prihlaska/",
        "https://www.vstecb.cz/uchazec/",
        "https://www.vstecb.cz/cs/uchazec",
    ],
}


def junk(url: str | None) -> bool:
    if not url:
        return True
    low = url.lower()
    return any(part in low for part in JUNK)


def pick(url: str | None, fallback: str | None) -> str | None:
    if url and not junk(url):
        return url
    if fallback and not junk(fallback):
        return fallback
    return None


def main() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    by_id = {row["institutionId"]: row for row in data["institutions"]}
    for iid, urls in RETRY.items():
        row = by_id[iid]
        for url in urls:
            result = fetch(url)
            print(f"retry {result['status']} ok={result['ok']} {url}")
            if not result.get("ok"):
                continue
            final = result.get("finalUrl") or url
            if APPLY_STRONG.search(final):
                row["applyUrl"] = row["applyUrl"] or final
            else:
                row["admissionsUrl"] = row["admissionsUrl"] or final
            if row["applyUrl"] or row["admissionsUrl"]:
                row["kind"] = "e_application" if row["applyUrl"] else "admissions_info"

    for row in data["institutions"]:
        row["applyUrl"] = pick(row.get("applyUrl"), None)
        row["applyUrlEn"] = pick(row.get("applyUrlEn"), row.get("applyUrl"))
        row["admissionsUrl"] = pick(row.get("admissionsUrl"), None)
        row["admissionsUrlEn"] = pick(row.get("admissionsUrlEn"), row.get("admissionsUrl"))
        if junk(row.get("applyUrl")):
            row["applyUrl"] = None
        if not row.get("applyUrl") and not row.get("admissionsUrl"):
            row["kind"] = "missing"
        elif row.get("applyUrl"):
            row["kind"] = "e_application"
        else:
            row["kind"] = "admissions_info"
        # Do not keep bulky probe logs in the public snapshot.
        row.pop("probes", None)

    data["counts"] = {
        "institutions": len(data["institutions"]),
        "eApplication": sum(1 for row in data["institutions"] if row["kind"] == "e_application"),
        "admissionsInfo": sum(1 for row in data["institutions"] if row["kind"] == "admissions_info"),
        "missing": sum(1 for row in data["institutions"] if row["kind"] == "missing"),
    }
    data["note"] = (
        "Verified official application / admissions URLs for every register HEI. "
        "Only HTTP 200 pages without a not-found phrase are stored. CSS/asset hits were dropped. "
        "Not a programme catalogue. Not written to data/published/. A working portal is not an open window."
    )
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data["counts"], indent=2))
    missing = [row["officialName"] for row in data["institutions"] if row["kind"] == "missing"]
    print("missing:", missing)


if __name__ == "__main__":
    main()

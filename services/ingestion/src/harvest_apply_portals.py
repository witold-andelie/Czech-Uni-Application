"""Discover and verify official application / admissions URLs for every HEI.

Only HTTP 200 pages without a not-found phrase are kept. Broken links are not
written as apply URLs. Does not invent programmes or windows, and does not
write data/published/.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "work" / "raw" / "2026-09-06"
OUT = ROOT / "data" / "sources" / "admissions" / "apply-portals.json"
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
UA = "CzechUniApplyHarvest/0.1 (offline ingestion; contact via local operator)"
SLEEP = 3
CTX = ssl.create_default_context()
HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
DEAD = (
    "we couldn’t find this page",
    "we couldn't find this page",
    "we couldn&rsquo;t find this page",
    "page not found",
    "stránka nenalezena",
    "stranka nenalezena",
    "404 not found",
    "this page doesn't exist",
    "this page does not exist",
)

SEEDS: dict[str, list[str]] = {
    "msmt-vs_11000": [
        "https://is.cuni.cz/studium/prihlaska/",
        "https://is.cuni.cz/studium/eng/prihlaska/",
        "https://cuni.cz/UK-36.html",
    ],
    "msmt-vs_14000": [
        "https://is.muni.cz/prihlaska/",
        "https://is.muni.cz/prihlaska/?lang=en",
        "https://www.muni.cz/en/admissions/bachelors-and-masters-studies/how-to-apply",
    ],
    "msmt-vs_21000": [
        "https://prihlaska.cvut.cz/",
        "https://prihlaska.cvut.cz/en",
        "https://www.cvut.cz/uchazeci",
        "https://www.cvut.cz/en/applicants",
    ],
    "msmt-vs_26000": [
        "https://www.vut.cz/eprihlaska",
        "https://www.vut.cz/eprihlaska/en",
        "https://www.vutbr.cz/eprihlaska",
        "https://www.vut.cz/en/study-options",
    ],
    "msmt-vs_15000": [
        "https://prihlaska.upol.cz",
        "https://www.upol.cz/uchazeci/",
        "https://www.upol.cz/en/admissions/",
    ],
    "msmt-vs_41000": [
        "https://is.czu.cz/prihlaska/",
        "https://is.czu.cz/prihlaska/?lang=en",
        "https://study.czu.cz/admission/",
        "https://www.czu.cz/cs/r-7210-uchazeci",
        "https://www.czu.cz/en/r-10414-study",
    ],
    "msmt-vs_31000": [
        "https://insis.vse.cz/prihlaska",
        "https://www.vse.cz/uchazeci/",
        "https://www.vse.cz/english/admissions/",
    ],
    "msmt-vs_43000": [
        "https://is.mendelu.cz/prihlaska",
        "https://mendelu.cz/pro-uchazece/",
        "https://mendelu.cz/en/admissions/",
    ],
    "msmt-vs_22000": [
        "https://student.vscht.cz/predregistrace.php",
        "https://www.vscht.cz/uchazeci",
        "https://www.vscht.cz/prijimacky",
        "https://www.vscht.cz/en/admission",
    ],
    "msmt-vs_27000": [
        "https://www.vsb.cz/cs/uchazeci/",
        "https://www.vsb.cz/en/admissions/",
        "https://uchazeci.vsb.cz/",
    ],
    "msmt-vs_23000": [
        "https://www.zcu.cz/cs/Admission/",
        "https://www.zcu.cz/en/Admission/",
        "https://portal.zcu.cz/",
    ],
    "msmt-vs_12000": [
        "https://www.jcu.cz/cz/prijimaci-rizeni",
        "https://www.jcu.cz/en/admissions",
        "https://wstag.jcu.cz/portal/studium/uchazec/eprihlaska.html",
    ],
    "msmt-vs_24000": [
        "https://www.tul.cz/uchazeci/",
        "https://www.tul.cz/en/admissions/",
        "https://stag.tul.cz/portal/studium/uchazec/eprihlaska.html",
    ],
    "msmt-vs_17000": [
        "https://www.osu.cz/uchazec/",
        "https://www.osu.cz/en/admissions/",
        "https://stag.osu.cz/portal/studium/uchazec/eprihlaska.html",
    ],
    "msmt-vs_19000": [
        "https://www.slu.cz/slu/cz/uchazeci",
        "https://www.slu.cz/slu/en/admissions",
        "https://is.slu.cz/prihlaska",
    ],
    "msmt-vs_25000": [
        "https://www.upce.cz/uchazeci",
        "https://www.upce.cz/en/admissions",
        "https://portal.upce.cz/portal/studium/uchazec/eprihlaska.html",
    ],
    "msmt-vs_51000": [
        "https://www.amu.cz/cs/prijimaci-rizeni/",
        "https://www.amu.cz/en/admissions/",
    ],
    "msmt-vs_54000": [
        "https://www.jamu.cz/uchazeci/",
        "https://www.jamu.cz/en/admissions/",
    ],
    "msmt-vs_61000": [
        "https://www.ambis.cz/prihlaska",
        "https://www.ambis.cz/en/admissions",
        "https://prihlaska.ambis.cz/",
    ],
    "msmt-vs_75000": [
        "https://www.mup.cz/uchazeci/",
        "https://www.mup.cz/en/admissions/",
        "https://prihlaska.mup.cz/",
    ],
    "msmt-vs_7s000": [
        "https://www.peuni.cz/prihlaska",
        "https://www.peuni.cz/en/admissions",
    ],
    "msmt-vs_7u000": [
        "https://www.vsfs.cz/prihlaska",
        "https://www.vsfs.cz/en/admissions",
        "https://is.vsfs.cz/prihlaska",
    ],
    "msmt-vs_6d000": [
        "https://www.unyp.cz/admissions/how-to-apply/",
        "https://www.unyp.cz/admissions/",
    ],
    "msmt-vs_7p000": [
        "https://www.savs.cz/uchazeci",
        "https://www.savs.cz/en/admissions",
        "https://is.savs.cz/prihlaska",
    ],
    "msmt-vs_52000": ["https://www.avu.cz/prijimaci-rizeni", "https://www.avu.cz/en/admissions"],
    "msmt-vs_6u000": ["https://www.aauni.edu/admissions/", "https://www.aauni.edu/apply/"],
    "msmt-vs_7m000": ["https://www.archip.eu/admissions/", "https://www.archip.eu/apply/"],
    "msmt-vs_7r000": ["https://www.artdesigninstitut.cz/prihlaska", "https://www.artdesigninstitut.cz/en/admissions"],
    "msmt-vs_7d000": ["https://www.cevro.cz/prihlaska", "https://www.cevro.cz/en/admissions"],
    "msmt-vs_7j000": ["https://www.vs-prigo.cz/prihlaska", "https://www.vs-prigo.cz/en/admissions"],
    "msmt-vs_6n000": ["https://www.filmovka.cz/prihlaska", "https://www.filmovka.cz/en/admissions"],
    "msmt-vs_7c000": ["https://www.mvso.cz/prihlaska", "https://www.mvso.cz/uchazeci"],
    "msmt-vs_94000": ["https://www.polac.cz/g2/html/prijimaci_rizeni.html", "https://www.polac.cz/g2/"],
    "msmt-vs_7l000": ["https://www.praguecityuniversity.cz/admissions", "https://www.praguecityuniversity.cz/apply"],
    "msmt-vs_79000": ["https://www.pvsps.cz/prihlaska", "https://www.pvsps.cz/uchazeci"],
    "msmt-vs_7e000": ["https://www.unicornuniversity.net/cs/prihlaska", "https://www.unicornuniversity.net/en/admissions"],
    "msmt-vs_63000": ["https://www.ucp.cz/prihlaska", "https://www.ucp.cz/en/admissions"],
    "msmt-vs_18000": ["https://www.uhk.cz/cs/uchazeci", "https://www.uhk.cz/en/admissions", "https://stag.uhk.cz/portal/studium/uchazec/eprihlaska.html"],
    "msmt-vs_13000": ["https://www.ujep.cz/cs/prijimaci-rizeni", "https://www.ujep.cz/en/admissions"],
    "msmt-vs_95000": ["https://www.unob.cz/uchazeci", "https://www.unob.cz/en/admissions"],
    "msmt-vs_28000": ["https://www.utb.cz/univerzita/uchazeci/", "https://www.utb.cz/en/admissions/", "https://apply.utb.cz/"],
    "msmt-vs_16000": ["https://www.vfu.cz/uchazeci", "https://www.vfu.cz/en/admissions"],
    "msmt-vs_7n000": ["https://www.vsaps.cz/prihlaska", "https://www.vsaps.cz/uchazeci"],
    "msmt-vs_7v000": ["https://www.vsem.cz/prihlaska.html", "https://www.vsem.cz/en/admissions.html"],
    "msmt-vs_6k000": ["https://www.vsers.cz/prihlaska", "https://www.vsers.cz/uchazeci"],
    "msmt-vs_7t000": ["https://www.vskk.cz/prihlaska", "https://www.vskk.cz/uchazeci"],
    "msmt-vs_6r000": ["https://www.vslg.cz/prihlaska", "https://www.vslg.cz/uchazeci"],
    "msmt-vs_6q000": ["https://www.newton.university/prihlaska", "https://vysokaskolanewton.cz/prihlaska", "https://www.newton.university/en/admissions"],
    "msmt-vs_55000": ["https://www.vspj.cz/uchazeci", "https://www.vspj.cz/en/admissions"],
    "msmt-vs_73000": ["https://www.sting.cz/prihlaska", "https://www.sting.cz/uchazeci"],
    "msmt-vs_56000": ["https://www.vstecb.cz/uchazeci", "https://www.vstecb.cz/en/admissions"],
    "msmt-vs_6p000": ["https://www.palestra.cz/prihlaska", "https://www.palestra.cz/uchazeci"],
    "msmt-vs_53000": ["https://www.umprum.cz/cs/web/uchazeci", "https://www.vsup.cz/cs/uchazeci", "https://www.umprum.cz/en/web/admissions"],
    "msmt-vs_6s000": ["https://www.vszdrav.cz/prihlaska", "https://www.vszdrav.cz/uchazeci"],
}

APPLY_HINT = re.compile(
    r"prihlask|e-prihlask|eprihlask|application|apply|admission|uchaze|prijimac|applicants",
    re.I,
)
APPLY_STRONG = re.compile(r"prihlask|e-prihlask|eprihlask|/apply|application", re.I)


def fetch(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as response:
            body = response.read(120000)
            text = body.decode("utf-8", errors="replace")
            return {
                "url": url,
                "finalUrl": response.geturl(),
                "status": response.status,
                "text": text,
                "ok": response.status == 200 and not is_dead(text),
            }
    except urllib.error.HTTPError as error:
        snippet = ""
        try:
            snippet = error.read(4000).decode("utf-8", errors="replace")
        except Exception:
            snippet = ""
        return {"url": url, "finalUrl": getattr(error, "url", url), "status": error.code, "text": snippet, "ok": False}
    except Exception as error:
        return {"url": url, "finalUrl": None, "status": 0, "text": "", "ok": False, "error": f"{type(error).__name__}: {error}"[:240]}


def is_dead(text: str) -> bool:
    low = text.lower()
    return any(needle in low for needle in DEAD)


def absolutize(base: str, href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
        return None
    try:
        return urllib.parse.urljoin(base, href)
    except Exception:
        return None


def host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return ""


def classify(url: str) -> str:
    if APPLY_STRONG.search(url):
        return "e_application"
    return "admissions_info"


def extra_paths(official: str) -> list[str]:
    parsed = urllib.parse.urlparse(official)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [
        f"{origin}/prihlaska",
        f"{origin}/eprihlaska",
        f"{origin}/uchazeci",
        f"{origin}/admissions",
        f"{origin}/en/admissions",
        f"{origin}/en/apply",
        f"{origin}/en/applicants",
        f"{origin}/prijimaci-rizeni",
    ]


def harvest_rows(institutions: list[dict]) -> list[dict]:
    last_host_at: dict[str, float] = {}
    cache: dict[str, dict] = {}
    rows: list[dict] = []

    def probe(url: str) -> dict:
        if url in cache:
            return cache[url]
        h = host(url)
        wait = SLEEP - (time.time() - last_host_at.get(h, 0))
        if h and wait > 0:
            time.sleep(wait)
        result = fetch(url)
        last_host_at[h] = time.time()
        cache[url] = result
        print(f"{result['status']} ok={result['ok']} {url}")
        return result

    for item in institutions:
        iid = item["id"]
        official = item.get("officialUrl")
        candidates: list[str] = []
        for url in SEEDS.get(iid, []):
            if url not in candidates:
                candidates.append(url)
        extracted: list[str] = []
        if official:
            home = probe(official)
            if home.get("ok"):
                for href in HREF.findall(home.get("text") or ""):
                    absu = absolutize(home.get("finalUrl") or official, href)
                    if absu and APPLY_HINT.search(absu) and absu not in candidates and absu not in extracted:
                        extracted.append(absu)
            candidates.extend(extracted[:8])

        apply_cs = None
        apply_en = None
        info_cs = None
        info_en = None
        probes = []
        if not any(APPLY_STRONG.search(url) for url in candidates) and official:
            for path in extra_paths(official):
                if path not in candidates:
                    candidates.append(path)
        for url in candidates[:12]:
            result = probe(url)
            probes.append({k: result[k] for k in ("url", "finalUrl", "status", "ok") if k in result})
            if not result.get("ok"):
                continue
            final = result.get("finalUrl") or url
            kind = classify(final)
            en_like = "/en/" in final.lower() or "lang=en" in final.lower() or "/eng/" in final.lower()
            if kind == "e_application":
                if en_like and not apply_en:
                    apply_en = final
                elif not en_like and not apply_cs:
                    apply_cs = final
            else:
                if en_like and not info_en:
                    info_en = final
                elif not en_like and not info_cs:
                    info_cs = final
        if not apply_cs and apply_en:
            apply_cs = apply_en
        if not apply_en and apply_cs:
            apply_en = apply_cs
        rows.append(
            {
                "institutionId": iid,
                "msmtCode": item["msmtCode"],
                "officialName": item["officialName"],
                "officialUrl": official,
                "applyUrl": apply_cs,
                "applyUrlEn": apply_en,
                "admissionsUrl": info_cs,
                "admissionsUrlEn": info_en,
                "kind": "e_application" if apply_cs else ("admissions_info" if info_cs or info_en else "missing"),
                "checkedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "probes": probes,
            }
        )
    return rows


def write_portals_snapshot(rows: list[dict]) -> dict:
    snapshot = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_admissions_extract",
        "catalogKind": "tracer_not_published",
        "note": "Verified official application / admissions URLs for every register HEI. Only HTTP 200 pages without a not-found phrase are stored. Not a programme catalogue. Not written to data/published/. A working portal is not an open window.",
        "counts": {
            "institutions": len(rows),
            "eApplication": sum(1 for row in rows if row["kind"] == "e_application"),
            "admissionsInfo": sum(1 for row in rows if row["kind"] == "admissions_info"),
            "missing": sum(1 for row in rows if row["kind"] == "missing"),
        },
        "institutions": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RAW / "apply-portals-harvest-log.json").write_text(json.dumps(snapshot["counts"], indent=2) + "\n", encoding="utf-8")
    print(json.dumps(snapshot["counts"], indent=2))
    missing = [row["officialName"] for row in rows if row["kind"] == "missing"]
    if missing:
        print("missing:", "; ".join(missing))
    return snapshot


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    write_portals_snapshot(harvest_rows(baseline["institutions"]))


if __name__ == "__main__":
    main()

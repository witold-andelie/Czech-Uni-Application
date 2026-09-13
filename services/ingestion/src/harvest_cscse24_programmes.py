"""Harvest official programme CSVs for the 24 CSCSE-listed HEIs.

Path per school: cvslist.aspx Detail → cvsdet.aspx overview → csplist.aspx Export CSV.
Rate-limited. Does not invent tuition, deadlines, apply URLs, or publish offerings.
Skips a school when a valid CSV is already on disk unless --force is passed.
"""
from __future__ import annotations

import html as html_lib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from apply_cscse_list import LISTED

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "work" / "raw" / "2026-09-06"
LIST_URL = "https://regvssp.msmt.cz/registrvssp/cvslist.aspx"
DETAIL_URL = "https://regvssp.msmt.cz/registrvssp/cvsdet.aspx"
PROGRAMME_LIST_URL = "https://regvssp.msmt.cz/registrvssp/csplist.aspx"
UA = "CzechUniApplyHarvest/0.1 (offline ingestion; contact via local operator)"
SLEEP_SECONDS = 3
HIDDEN = re.compile(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', re.I)
SCHOOL_VALUE = re.compile(
    r'id="ContentPlaceHolder1_vysoka_skola_tb"[^>]*value="([^"]*)"',
    re.I,
)
TOTAL = re.compile(r"Celkový počet odpovídajících záznamů:\s*(\d+)")


def csv_path(code: str) -> Path:
    return RAW / f"msmt-programmes-{code.lower()}.csv.txt"


def opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def request(handle, url, data=None, timeout=90):
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with handle.open(req, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as error:
        body = error.read() if error.fp else b""
        info = {k.lower(): v for k, v in error.headers.items()} if error.headers else {}
        return error.code, info, body


def hidden_fields(html: str) -> dict[str, str]:
    return {name: html_lib.unescape(value) for name, value in HIDDEN.findall(html)}


def post(handle, url, fields):
    return request(handle, url, urllib.parse.urlencode(fields).encode("utf-8"))


def valid_csv(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 80:
        return False
    head = path.read_bytes()[:200].decode("cp1250", errors="replace")
    return "JAZYK" in head and "TYP SP" in head


def harvest_one(school: dict, force: bool) -> dict:
    code = school["msmtCode"]
    name = school["officialName"]
    out = csv_path(code)
    if valid_csv(out) and not force:
        return {"msmtCode": code, "officialName": name, "status": "skipped_existing", "bytes": out.stat().st_size}

    handle = opener()
    status, _headers, body = request(handle, LIST_URL)
    fields = hidden_fields(body.decode("utf-8", errors="replace"))
    if status != 200 or "__VIEWSTATE" not in fields:
        return {"msmtCode": code, "officialName": name, "status": "list_get_failed", "httpStatus": status}

    time.sleep(SLEEP_SECONDS)
    detail_fields = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": fields.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": fields.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": fields.get("__EVENTVALIDATION", ""),
        "ctl00$ContentPlaceHolder1$v_nazvu_tb": "",
        "ctl00$ContentPlaceHolder1$sidlo_tb": "",
        "ctl00$ContentPlaceHolder1$typ_ddl": "X",
        "ctl00$ContentPlaceHolder1$forma_ddl": "X",
        "ctl00$ContentPlaceHolder1$kraj_ddl": "X",
        "ctl00$ContentPlaceHolder1$studijni_program_tb": "",
        "ctl00$ContentPlaceHolder1$studijni_obor_tb": "",
        f"ctl00$ContentPlaceHolder1${code}": "Detail",
    }
    status, _headers, body = post(handle, LIST_URL, detail_fields)
    detail_html = body.decode("utf-8", errors="replace")
    (RAW / f"msmt-detail-{code.lower()}.html").write_bytes(body)
    detail = hidden_fields(detail_html)
    if status != 200 or "__VIEWSTATE" not in detail:
        return {"msmtCode": code, "officialName": name, "status": "detail_failed", "httpStatus": status}

    time.sleep(SLEEP_SECONDS)
    overview_fields = {
        "__VIEWSTATE": detail.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": detail.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": detail.get("__EVENTVALIDATION", ""),
        f"ctl00$ContentPlaceHolder1${code}": "Přehled studijních programů a studijních oborů",
    }
    status, _headers, body = post(handle, DETAIL_URL, overview_fields)
    overview_html = body.decode("utf-8", errors="replace")
    (RAW / f"msmt-programmes-{code.lower()}.html").write_bytes(body)
    listed = hidden_fields(overview_html)
    total_match = TOTAL.search(overview_html)
    school_match = SCHOOL_VALUE.search(overview_html)
    form_name = html_lib.unescape(school_match.group(1)) if school_match else name
    if status != 200 or "__VIEWSTATE" not in listed:
        return {
            "msmtCode": code,
            "officialName": name,
            "status": "overview_failed",
            "httpStatus": status,
            "overviewBytes": len(body),
        }

    time.sleep(SLEEP_SECONDS)
    csv_fields = {
        "__VIEWSTATE": listed.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": listed.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": listed.get("__EVENTVALIDATION", ""),
        "ctl00$ContentPlaceHolder1$v_nazvu_tb": "",
        "ctl00$ContentPlaceHolder1$vysoka_skola_tb": form_name,
        "ctl00$ContentPlaceHolder1$typ_sp_ddl": "X",
        "ctl00$ContentPlaceHolder1$forma_studia_ddl": "X",
        "ctl00$ContentPlaceHolder1$kraj_ddl": "X",
        "ctl00$ContentPlaceHolder1$studijni_program_tb": "",
        "ctl00$ContentPlaceHolder1$studijni_obor_tb": "",
        "ctl00$ContentPlaceHolder1$ddl_ov": "0",
        "ctl00$ContentPlaceHolder1$ddl_stranky": "20",
        "ctl00$ContentPlaceHolder1$csv_btn": "Export CSV",
    }
    csv_status, csv_headers, csv_body = post(handle, PROGRAMME_LIST_URL, csv_fields)
    out.write_bytes(csv_body)
    content_type = csv_headers.get("content-type", "")
    ok = csv_status == 200 and "csv" in content_type and valid_csv(out)
    meta = {
        "msmtCode": code,
        "officialName": name,
        "status": "ok" if ok else "csv_failed",
        "httpStatus": csv_status,
        "contentType": content_type,
        "contentDisposition": csv_headers.get("content-disposition"),
        "bytes": len(csv_body),
        "overviewTotalLabel": int(total_match.group(1)) if total_match else None,
        "formSchoolName": form_name,
        "head": csv_body[:180].decode("cp1250", errors="replace"),
    }
    out.with_suffix(out.suffix + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return meta


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    force = "--force" in sys.argv
    charles = RAW / "msmt-programmes-charles.csv.txt"
    target = csv_path("VS_11000")
    if valid_csv(charles) and not valid_csv(target):
        target.write_bytes(charles.read_bytes())
    log = {"source": PROGRAMME_LIST_URL, "force": force, "schools": []}
    for school in LISTED:
        result = harvest_one(school, force)
        if result["status"] not in {"ok", "skipped_existing"}:
            time.sleep(SLEEP_SECONDS)
            retry = harvest_one(school, True)
            retry["retriedFrom"] = result["status"]
            result = retry
        log["schools"].append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result["status"] != "skipped_existing":
            time.sleep(SLEEP_SECONDS)
    log["summary"] = {
        "ok": sum(item["status"] == "ok" for item in log["schools"]),
        "skipped": sum(item["status"] == "skipped_existing" for item in log["schools"]),
        "failed": sum(item["status"] not in {"ok", "skipped_existing"} for item in log["schools"]),
    }
    (RAW / "msmt-cscse24-harvest-log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(log["summary"], ensure_ascii=False))
    if log["summary"]["failed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

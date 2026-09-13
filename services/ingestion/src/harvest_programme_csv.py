"""Harvest one official programme CSV from an MŠMT institution detail page.

Path: cvslist.aspx Detail postback → cvsdet.aspx → CSV (SP/O).
Charles University (VS_11000) is the tracer. This does not invent tuition,
deadlines, teaching language, or CSCSE status, and does not crawl all 54 HEIs.
"""
from __future__ import annotations

import html as html_lib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "work" / "raw" / "2026-09-06"
LIST_URL = "https://regvssp.msmt.cz/registrvssp/cvslist.aspx"
DETAIL_URL = "https://regvssp.msmt.cz/registrvssp/cvsdet.aspx"
PROGRAMME_LIST_URL = "https://regvssp.msmt.cz/registrvssp/csplist.aspx"
UA = "CzechUniApplyHarvest/0.1 (offline ingestion; contact via local operator)"
SLEEP_SECONDS = 3
HIDDEN = re.compile(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', re.I)


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


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    handle = opener()
    status, headers, body = request(handle, LIST_URL)
    fields = hidden_fields(body.decode("utf-8", errors="replace"))
    if status != 200 or "__VIEWSTATE" not in fields:
        raise SystemExit(f"list GET failed: {status}")

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
        "ctl00$ContentPlaceHolder1$VS_11000": "Detail",
    }
    status, headers, body = post(handle, LIST_URL, detail_fields)
    (RAW / "msmt-detail-charles-session.html").write_bytes(body)
    detail = hidden_fields(body.decode("utf-8", errors="replace"))
    if status != 200 or "__VIEWSTATE" not in detail:
        raise SystemExit(f"detail POST failed: {status}")

    time.sleep(SLEEP_SECONDS)
    overview_fields = {
        "__VIEWSTATE": detail.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": detail.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": detail.get("__EVENTVALIDATION", ""),
        "ctl00$ContentPlaceHolder1$VS_11000": "Přehled studijních programů a studijních oborů",
    }
    status, headers, body = post(handle, DETAIL_URL, overview_fields)
    overview = RAW / "msmt-programmes-charles.html"
    overview.write_bytes(body)
    decoded = body.decode("utf-8", errors="replace")
    listed = hidden_fields(decoded)
    time.sleep(SLEEP_SECONDS)
    csv_fields = {
        "__VIEWSTATE": listed.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": listed.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": listed.get("__EVENTVALIDATION", ""),
        "ctl00$ContentPlaceHolder1$v_nazvu_tb": "",
        "ctl00$ContentPlaceHolder1$vysoka_skola_tb": "Univerzita Karlova",
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
    out = RAW / "msmt-programmes-charles.csv.txt"
    out.write_bytes(csv_body)
    meta = {
        "institution": "Univerzita Karlova",
        "msmtCode": "VS_11000",
        "detailUrl": DETAIL_URL,
        "programmeListUrl": PROGRAMME_LIST_URL,
        "overview": {
            "httpStatus": status,
            "contentType": headers.get("content-type"),
            "bytes": len(body),
            "hasProgrammeTable": "studijní program" in decoded.casefold(),
            "totalLabel": "925" if "925" in decoded else None,
        },
        "csv": {
            "httpStatus": csv_status,
            "contentType": csv_headers.get("content-type"),
            "contentDisposition": csv_headers.get("content-disposition"),
            "bytes": len(csv_body),
            "head": csv_body[:400].decode("cp1250", errors="replace"),
        },
        "note": "Official register tracer for one HEI. Accreditation inventory, not tuition, deadlines, or CSCSE status.",
    }
    out.with_suffix(out.suffix + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Harvest structured MŠMT register exports via ASP.NET POST.

The public register is not a REST API. The HTML list page exposes:
- CSV (VŠ)  — institutions
- CSV (F)   — faculties of the current selection
- Detail    — per-institution postback (programmes live here)
- NajdiSP   — ASP.NET autocomplete of programme names

This script does not invent tuition, deadlines, teaching language, or CSCSE
status. It does not start the 120-hour scheduler.
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
REGISTER_URL = "https://regvssp.msmt.cz/registrvssp/cvslist.aspx"
HOMEPAGE_URL = "https://regvssp.msmt.cz/registrvssp/"
INAK_URL = "https://regvssp.msmt.cz/registrvssp/inak.aspx"
UA = "CzechUniApplyHarvest/0.1 (offline ingestion; contact via local operator)"
SLEEP_SECONDS = 3

HIDDEN = re.compile(
    r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"',
    re.I,
)


def opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request(
    handle: urllib.request.OpenerDirector,
    url: str,
    data: bytes | None = None,
    content_type: str | None = None,
    timeout: int = 60,
) -> tuple[int, dict[str, str], bytes]:
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with handle.open(req, timeout=timeout) as response:
            body = response.read()
            info = {k.lower(): v for k, v in response.headers.items()}
            return response.status, info, body
    except urllib.error.HTTPError as error:
        body = error.read() if error.fp else b""
        info = {k.lower(): v for k, v in error.headers.items()} if error.headers else {}
        return error.code, info, body


def hidden_fields(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for name, value in HIDDEN.findall(html):
        fields[name] = html_lib.unescape(value)
    return fields


def save(path: Path, body: bytes, headers: dict[str, str], status: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    meta = {
        "url": REGISTER_URL,
        "httpStatus": status,
        "contentType": headers.get("content-type"),
        "contentDisposition": headers.get("content-disposition"),
        "bytes": len(body),
    }
    path.with_suffix(path.suffix + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def post_form(handle: urllib.request.OpenerDirector, fields: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    encoded = urllib.parse.urlencode(fields).encode("utf-8")
    return request(handle, REGISTER_URL, data=encoded, content_type="application/x-www-form-urlencoded")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    handle = opener()
    log: dict[str, object] = {"sourceUrl": REGISTER_URL, "steps": []}

    status, headers, body = request(handle, REGISTER_URL)
    html = body.decode("utf-8", errors="replace")
    (RAW / "msmt-cvslist-fresh.html").write_bytes(body)
    fields = hidden_fields(html)
    log["steps"].append({"step": "get_list", "httpStatus": status, "bytes": len(body), "hidden": list(fields)})
    if status != 200 or "__VIEWSTATE" not in fields:
        raise SystemExit(f"register GET failed: {status}")

    base = {
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
    }

    time.sleep(SLEEP_SECONDS)
    csv_fields = dict(base)
    csv_fields["ctl00$ContentPlaceHolder1$csv_btn"] = "CSV (VŠ)"
    status, headers, body = post_form(handle, csv_fields)
    save(RAW / "msmt-register-institutions.csv.txt", body, headers, status)
    log["steps"].append(
        {
            "step": "csv_institutions",
            "httpStatus": status,
            "contentType": headers.get("content-type"),
            "contentDisposition": headers.get("content-disposition"),
            "bytes": len(body),
            "head": body[:180].decode("utf-8", errors="replace"),
        }
    )

    time.sleep(SLEEP_SECONDS)
    faculty_fields = dict(base)
    faculty_fields["ctl00$ContentPlaceHolder1$csv_f_btn"] = "CSV (F)"
    status, headers, body = post_form(handle, faculty_fields)
    save(RAW / "msmt-register-faculties.csv.txt", body, headers, status)
    log["steps"].append(
        {
            "step": "csv_faculties",
            "httpStatus": status,
            "contentType": headers.get("content-type"),
            "contentDisposition": headers.get("content-disposition"),
            "bytes": len(body),
            "head": body[:180].decode("utf-8", errors="replace"),
        }
    )

    tracers = [
        ("VS_11000", "charles-university"),
        ("VS_61000", "ambis-private"),
        ("VS_95000", "univerzita-obrany-state"),
    ]
    for code, slug in tracers:
        time.sleep(SLEEP_SECONDS)
        detail_fields = dict(base)
        detail_fields[f"ctl00$ContentPlaceHolder1${code}"] = "Detail"
        status, headers, body = post_form(handle, detail_fields)
        out = RAW / f"msmt-detail-{slug}.html"
        save(out, body, headers, status)
        snippet = body.decode("utf-8", errors="replace")
        log["steps"].append(
            {
                "step": f"detail_{slug}",
                "msmtCode": code,
                "httpStatus": status,
                "bytes": len(body),
                "hasProgramme": "studijní program" in snippet.casefold() or "studijni program" in snippet.casefold(),
                "hasWebsite": bool(re.search(r"https?://", snippet)),
            }
        )

    time.sleep(SLEEP_SECONDS)
    ajax_body = json.dumps({"prefixText": "Informatika", "count": 20}).encode("utf-8")
    ajax_req = urllib.request.Request(
        REGISTER_URL + "/NajdiSP",
        data=ajax_body,
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": REGISTER_URL,
        },
        method="POST",
    )
    try:
        with handle.open(ajax_req, timeout=45) as response:
            ajax = response.read()
            ajax_status = response.status
            ajax_type = response.headers.get("Content-Type")
    except urllib.error.HTTPError as error:
        ajax = error.read() if error.fp else b""
        ajax_status = error.code
        ajax_type = error.headers.get("Content-Type") if error.headers else None
    (RAW / "msmt-najdisp-informatika.json.txt").write_bytes(ajax)
    log["steps"].append(
        {
            "step": "najdisp_informatika",
            "httpStatus": ajax_status,
            "contentType": ajax_type,
            "bytes": len(ajax),
            "head": ajax[:400].decode("utf-8", errors="replace"),
        }
    )

    (RAW / "msmt-register-export-log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(log, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

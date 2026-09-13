"""HEAD/GET official URLs and report status. Does not invent offerings."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CTX = ssl.create_default_context()
UA = "CzechUniApplyHarvest/0.1 (offline ingestion; contact via local operator)"


def probe(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as response:
            body = response.read(8000)
            final = response.geturl()
            status = response.status
            text = body.decode("utf-8", errors="replace").lower()
            dead = any(
                needle in text
                for needle in (
                    "we couldn’t find this page",
                    "we couldn't find this page",
                    "page not found",
                    "stránka nenalezena",
                    "stranka nenalezena",
                    "404 not found",
                )
            )
            return {"url": url, "finalUrl": final, "status": status, "bytes": len(body), "deadPhrase": dead}
    except urllib.error.HTTPError as error:
        return {"url": url, "finalUrl": error.geturl() if hasattr(error, "geturl") else url, "status": error.code, "bytes": 0, "deadPhrase": True}
    except Exception as error:
        return {"url": url, "finalUrl": None, "status": 0, "bytes": 0, "deadPhrase": True, "error": type(error).__name__ + ": " + str(error)[:200]}


def main() -> None:
    urls = [
        "https://is.cuni.cz/studium/eng/prihlaska/",
        "http://www.mff.cuni.cz/eprihlaska",
        "https://www.mff.cuni.cz/eprihlaska",
        "https://is.cuni.cz/studium/prihlaska/",
        "https://is.cuni.cz/studium/eng/prijimacky/index.php?do=detail_obor&id_obor=34738",
        "https://is.muni.cz/prihlaska/?lang=en",
        "https://is.muni.cz/prihlaska/",
        "https://is.muni.cz/application/",
        "https://is.muni.cz/prihlaska/info?filtr-typ-studia=BM&filtr-forma-studia=P&filtr-fakulta=1433&vyhledat=Vyhledat",
        "https://www.fi.muni.cz/admission/international/info-master.html.en",
    ]
    rows = [probe(url) for url in urls]
    out = ROOT / "work" / "raw" / "2026-09-06" / "apply-url-probe.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print(f"{row['status']} dead={row.get('deadPhrase')} {row['url']} -> {row.get('finalUrl')}")


if __name__ == "__main__":
    main()

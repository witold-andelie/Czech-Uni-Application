"""Fetch the official MŠMT HEI register with Scrapling, then parse it.

This is an offline harvest of the institution baseline. It does not invent
programmes, tuition, deadlines, or CSCSE status, and it does not start the
120-hour production scheduler.
"""
from __future__ import annotations

import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "work" / "raw" / "2026-09-06"
REGISTER_URL = "https://regvssp.msmt.cz/registrvssp/cvslist.aspx"
WEBSITES_URL = "https://archiv.msmt.gov.cz/areas-of-work/tertiary-education/public-higher-education-institutions-websites"
SCRAPLING = shutil.which("scrapling") or "scrapling"


def scrapling_get(url: str, output: Path, timeout: int = 45) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(SCRAPLING), "extract", "get", url, str(output), "--timeout", str(timeout)],
        check=False,
    )
    return completed.returncode


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    register_html = RAW_DIR / "msmt-cvslist.html"
    websites_html = RAW_DIR / "msmt-public-websites.html"
    code = scrapling_get(REGISTER_URL, register_html)
    if code != 0:
        raise SystemExit(f"Scrapling GET of the MŠMT register failed with {code}")
    websites = scrapling_get(WEBSITES_URL, websites_html)
    if websites != 0:
        print(f"warning: archived MŠMT website list GET failed with {websites}", file=sys.stderr)
    parse = subprocess.run([sys.executable, str(Path(__file__).with_name("parse_msmt_register.py"))], check=False)
    if parse.returncode != 0:
        raise SystemExit(parse.returncode)
    exports = subprocess.run([sys.executable, str(Path(__file__).with_name("harvest_register_exports.py"))], check=False)
    if exports.returncode != 0:
        raise SystemExit(exports.returncode)
    csv_merge = subprocess.run([sys.executable, str(Path(__file__).with_name("parse_msmt_csv.py"))], check=False)
    if csv_merge.returncode != 0:
        raise SystemExit(csv_merge.returncode)
    if websites_html.exists() and websites_html.stat().st_size > 1000:
        merge = subprocess.run([sys.executable, str(Path(__file__).with_name("merge_msmt_websites.py"))], check=False)
        if merge.returncode != 0:
            raise SystemExit(merge.returncode)
    details = subprocess.run([sys.executable, str(Path(__file__).with_name("parse_msmt_detail.py"))], check=False)
    if details.returncode != 0:
        raise SystemExit(details.returncode)
    cscse = subprocess.run([sys.executable, str(Path(__file__).with_name("apply_cscse_list.py"))], check=False)
    if cscse.returncode != 0:
        raise SystemExit(cscse.returncode)
    print("baseline harvest finished; CSCSE labels come from the operator list matched to the register")


if __name__ == "__main__":
    main()

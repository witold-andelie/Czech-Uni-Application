"""Harvest Charles University SIS / faculty admissions pages for the MFF tracer.

One English-taught and one Czech-taught bachelor Computer Science / Informatika
offering. Does not crawl other HEIs, does not start the 120-hour scheduler,
and does not write data/published/.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "work" / "raw" / "2026-09-06"
SCRAPLING = Path(r"C:\Users\Administrator\AppData\Local\Programs\Python\Python313\Scripts\scrapling.exe")
SLEEP_SECONDS = 3

PAGES = [
    {
        "id": "cuni-sis-cs-bachelor-cs",
        "url": "https://is.cuni.cz/studium/prijimacky/index.php?do=detail_obor&id_obor=34456",
        "output": "cuni-sis-cs-bachelor-cs.html",
        "note": "MFF Informatika bachelor, Czech instruction, SIS id_obor=34456",
    },
    {
        "id": "cuni-sis-mff-faculty-en",
        "url": "https://is.cuni.cz/studium/eng/prijimacky/index.php?do=info_fakulta&fak=11320",
        "output": "cuni-sis-mff-faculty-en.html",
        "note": "MFF faculty admissions conditions (English SIS)",
    },
    {
        "id": "cuni-sis-mff-faculty-cs",
        "url": "https://is.cuni.cz/studium/prijimacky/index.php?do=info_fakulta&fak=11320",
        "output": "cuni-sis-mff-faculty-cs.html",
        "note": "MFF faculty admissions conditions (Czech SIS)",
    },
]


def scrapling_get(url: str, output: Path, timeout: int = 45) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(SCRAPLING), "extract", "get", url, str(output), "--timeout", str(timeout)],
        check=False,
    )
    return completed.returncode


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    log = []
    for i, page in enumerate(PAGES):
        if i:
            time.sleep(SLEEP_SECONDS)
        dest = RAW / page["output"]
        code = scrapling_get(page["url"], dest)
        size = dest.stat().st_size if dest.exists() else 0
        log.append(
            {
                "id": page["id"],
                "url": page["url"],
                "output": str(dest.relative_to(ROOT)).replace("\\", "/"),
                "exitCode": code,
                "bytes": size,
                "ok": code == 0 and size > 1000,
                "note": page["note"],
            }
        )
        print(f"{page['id']}: exit={code} bytes={size}")
    (RAW / "cuni-admissions-harvest-log.json").write_text(
        json.dumps({"harvestedAt": "2026-09-06", "pages": log}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    failed = [item for item in log if not item["ok"]]
    if failed:
        raise SystemExit(f"harvest failed: {[item['id'] for item in failed]}")


if __name__ == "__main__":
    main()

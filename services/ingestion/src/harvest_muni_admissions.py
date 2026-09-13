"""Harvest Masaryk University FI admissions pages for the tracer.

One English-taught master's (Visual Informatics) and one Czech-taught
bachelor (Informatika). Does not crawl other HEIs, does not start the
120-hour scheduler, and does not write data/published/.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "work" / "raw" / "2026-09-06"
SCRAPLING = Path(r"C:\Users\Administrator\AppData\Local\Programs\Python\Python313\Scripts\scrapling.exe")
SLEEP_SECONDS = 3

PAGES = [
    {
        "id": "muni-how-to-apply-en",
        "url": "https://www.muni.cz/en/admissions/bachelors-and-masters-studies/how-to-apply",
        "output": "muni-how-to-apply-en.html",
    },
    {
        "id": "muni-tuition-en",
        "url": "https://www.muni.cz/en/admissions/bachelors-and-masters-studies/tuition-fees-and-financial-aid",
        "output": "muni-tuition-en.html",
    },
    {
        "id": "muni-admission-fees-en",
        "url": "https://www.muni.cz/en/about-us/official-notice-board/admission-procedure-fees",
        "output": "muni-admission-fees-en.html",
    },
    {
        "id": "muni-fi-bachelor-cs",
        "url": "https://www.fi.muni.cz/admission/info-bachelor.html.cs",
        "output": "muni-fi-bachelor-cs.html",
    },
    {
        "id": "muni-fi-bachelor-guide-cs",
        "url": "https://www.fi.muni.cz/admission/guide.html.cs",
        "output": "muni-fi-bachelor-guide-cs.html",
    },
    {
        "id": "muni-fi-timeline-cs",
        "url": "https://www.fi.muni.cz/admission/timeline.html.cs",
        "output": "muni-fi-timeline-cs.html",
    },
    {
        "id": "muni-fi-master-en",
        "url": "https://www.fi.muni.cz/admission/international/info-master.html.en",
        "output": "muni-fi-master-en.html",
    },
    {
        "id": "muni-fi-index-en",
        "url": "https://www.fi.muni.cz/admission/index.html.en",
        "output": "muni-fi-index-en.html",
    },
    {
        "id": "muni-fi-visual-informatics",
        "url": "https://www.fi.muni.cz/admission/mgr/visual-informatics.html",
        "output": "muni-fi-visual-informatics.html",
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
            }
        )
        print(f"{page['id']}: exit={code} bytes={size}")
    (RAW / "muni-admissions-harvest-log.json").write_text(
        json.dumps({"harvestedAt": "2026-09-06", "pages": log}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    failed = [item["id"] for item in log if not item["ok"]]
    if failed:
        raise SystemExit(f"harvest failed: {failed}")


if __name__ == "__main__":
    main()

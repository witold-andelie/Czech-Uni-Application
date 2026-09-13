"""Harvest official programme CSVs for register HEIs outside the CSCSE-24 set.

Same MŠMT path as the listed-school harvest. Does not invent tuition, deadlines,
or apply URLs, and does not write data/published/. Skips a school when a valid
CSV is already on disk unless --force is passed.
"""
from __future__ import annotations

import json
import sys
import time

from pathlib import Path

from apply_cscse_list import LISTED
from harvest_cscse24_programmes import (
    PROGRAMME_LIST_URL,
    RAW,
    SLEEP_SECONDS,
    csv_path,
    harvest_one,
    valid_csv,
)

BASELINE = Path(__file__).resolve().parents[3] / "data" / "sources" / "msmt-hei-baseline.json"


def remaining_schools() -> list[dict]:
    listed = {item["msmtCode"] for item in LISTED}
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    return [
        {"msmtCode": item["msmtCode"], "officialName": item["officialName"]}
        for item in baseline["institutions"]
        if item["msmtCode"] not in listed
    ]


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    force = "--force" in sys.argv
    schools = remaining_schools()
    log = {"source": PROGRAMME_LIST_URL, "force": force, "scope": "register_remaining", "schools": []}
    for school in schools:
        if valid_csv(csv_path(school["msmtCode"])) and not force:
            result = {
                "msmtCode": school["msmtCode"],
                "officialName": school["officialName"],
                "status": "skipped_existing",
                "bytes": csv_path(school["msmtCode"]).stat().st_size,
            }
        else:
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
    (RAW / "msmt-remaining-harvest-log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(log["summary"], ensure_ascii=False))
    if log["summary"]["failed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

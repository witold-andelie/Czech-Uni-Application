"""Re-bind job review entries from fact-v1 to fact-v2 (owner decision 2026-10-01).

fact-v2 binds a review to the facts a reviewer checks; it leaves out a
window's computed open/closed status and the track/isPostdoc reading. A
fact-v1 entry is re-bound only from a record whose fact-v1 hash equals the
entry's: that is exactly the record the reviewer approved, and its fact-v2
hash describes the same reviewed facts. The search covers the candidate file,
then every immutable published snapshot, newest first. An entry with no such
record is left on fact-v1 and stays in the re-review queue; nothing is guessed.

Default is a dry run; --write updates data/sources/reviews/job-translations.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from publication_rules import JOB_FACT_NORMALIZATION_VERSION, job_fact_hash  # noqa: E402

REVIEWS = ROOT / "data" / "sources" / "reviews" / "job-translations.json"
CANDIDATES = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
SNAPSHOTS = ROOT / "data" / "published" / "snapshots"
NOTE = (
    "Re-bound fact-v1 -> fact-v2 on 2026-10-01 from {where}, the record whose fact-v1 hash equals "
    "this review's: the reviewed facts are unchanged; window status and track/isPostdoc are no "
    "longer bound (owner decision)."
)


def _baselines(candidates: Path, snapshots: Path) -> list[tuple[str, dict]]:
    sources = [("the candidate file", candidates)]
    sources += [
        (f"snapshot {path.parent.parent.name}", path)
        for path in sorted(snapshots.glob("*/browse/nine-hei-jobs.json"), reverse=True)
    ]
    out = []
    for label, path in sources:
        if path.is_file():
            out.append((label, json.loads(path.read_text(encoding="utf-8"))))
    return out


def migrate(reviews_doc: dict, baselines: list[tuple[str, dict]]) -> dict:
    reviews = reviews_doc.get("reviews") or {}
    indexed = []
    for label, payload in baselines:
        windows = [item for item in payload.get("windows") or [] if isinstance(item, dict)]
        jobs = {item["id"]: item for item in payload.get("jobs") or [] if isinstance(item, dict) and item.get("id")}
        indexed.append((label, jobs, windows))
    rebound: list[str] = []
    unmatched: list[str] = []
    for job_id, entry in sorted(reviews.items()):
        if not isinstance(entry, dict) or entry.get("normalizationVersion") != "fact-v1" or not entry.get("factHash"):
            continue
        for label, jobs, windows in indexed:
            job = jobs.get(job_id)
            if job is None:
                continue
            owned = [item for item in windows if item.get("ownerId") == job_id]
            if job_fact_hash(job, owned, "fact-v1") != entry["factHash"]:
                continue
            entry["factHash"] = job_fact_hash(job, owned, JOB_FACT_NORMALIZATION_VERSION)
            entry["normalizationVersion"] = JOB_FACT_NORMALIZATION_VERSION
            note = NOTE.format(where=label)
            entry["reviewNote"] = f"{entry['reviewNote']}\n\n{note}" if entry.get("reviewNote") else note
            rebound.append(job_id)
            break
        else:
            unmatched.append(job_id)
    return {"rebound": rebound, "unmatched": unmatched}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the re-bound review file")
    args = parser.parse_args()
    reviews_doc = json.loads(REVIEWS.read_text(encoding="utf-8"))
    result = migrate(reviews_doc, _baselines(CANDIDATES, SNAPSHOTS))
    print(json.dumps({"rebound": len(result["rebound"]), "unmatched": result["unmatched"]}, ensure_ascii=False, indent=2))
    if args.write:
        REVIEWS.write_text(json.dumps(reviews_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {REVIEWS}")


if __name__ == "__main__":
    main()

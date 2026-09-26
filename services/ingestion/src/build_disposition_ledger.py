"""A83: one-decision-per-candidate disposition ledger.

Deterministically derives, for every current candidate, its publication
disposition and blockers, prioritised by near deadlines and underrepresented
institutions. The ledger never approves anything; it records state so no
candidate is silently abandoned.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CANDIDATES = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
POINTER = ROOT / "data" / "published" / "current.json"
OUT = ROOT / "data" / "sources" / "coverage" / "candidate-disposition.json"

LEDGER_SCHEMA_VERSION = 1


def read_json(path: Path, default=None):
    if not path.exists() and default is not None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def blockers_for(job: dict, is_public: bool) -> list[str]:
    blockers: list[str] = []
    if job.get("paidStatus") != "confirmed":
        blockers.append("unconfirmed_pay_evidence")
    if job.get("catalogueScopeStatus") != "included":
        blockers.append("unspecified_scope")
    # Owner direction (2026-09-13): unstated degree level / doctoral enrollment
    # is an honest "unknown" attribute shown on the record and filterable — it
    # no longer blocks publication by itself.
    if job.get("translationStatus") == "stale":
        blockers.append("evidence_changed_since_review")
    if job.get("translationStatus") in (None, "unreviewed", "draft"):
        blockers.append("trilingual_review_missing")
    if not blockers and not is_public and job.get("publicationStatus") != "approved":
        blockers.append("review_incomplete")
    return blockers


def build_ledger(
    candidates: dict,
    published_ids: set[str],
    pointer: dict,
    generated_at: str | None = None,
) -> dict:
    windows_by_owner: dict[str, list[dict]] = {}
    for window in candidates.get("windows") or []:
        if isinstance(window, dict) and window.get("ownerId"):
            windows_by_owner.setdefault(window["ownerId"], []).append(window)

    rows = []
    for job in candidates.get("jobs") or []:
        if not isinstance(job, dict) or not job.get("id"):
            continue
        if job.get("visibility") == "archived" or job.get("lifecycleStatus") in {
            "closed",
            "expired",
            "unavailable",
        }:
            continue
        job_id = job["id"]
        is_public = job_id in published_ids
        blockers = [] if is_public else blockers_for(job, is_public)
        deadlines = sorted(
            str(w.get("closesAt"))
            for w in windows_by_owner.get(job_id, [])
            if w.get("closesAt")
        )
        rows.append(
            {
                "candidateId": job_id,
                "employerId": job.get("employerId"),
                "originalText": job.get("originalText"),
                "sourceUrl": job.get("sourceUrl"),
                "track": job.get("track"),
                "isPostdoc": bool(job.get("isPostdoc")),
                "paidStatus": job.get("paidStatus"),
                "minimumDegree": job.get("minimumDegree"),
                "doctoralEnrollment": job.get("doctoralEnrollment"),
                "catalogueScopeStatus": job.get("catalogueScopeStatus"),
                "nearestDeadline": deadlines[0] if deadlines else None,
                "decision": "approved_public" if is_public else "blocked",
                "blockers": blockers,
                "unknownAttributes": {
                    "degree": job.get("minimumDegree") in (None, "unknown"),
                    "doctoralEnrollment": job.get("doctoralEnrollment") in (None, "unspecified"),
                },
                "factsExtractedAt": job.get("factsExtractedAt"),
                "parserVersion": job.get("parserVersion"),
            }
        )

    def sort_key(row: dict):
        return (
            row["nearestDeadline"] or "9999-12-31",
            str(row["employerId"]),
            str(row["candidateId"]),
        )

    rows.sort(key=sort_key)
    by_school: dict[str, dict[str, int]] = {}
    for row in rows:
        entry = by_school.setdefault(
            str(row["employerId"]), {"current": 0, "approved_public": 0, "blocked": 0}
        )
        entry["current"] += 1
        entry["approved_public" if row["decision"] == "approved_public" else "blocked"] += 1
    version = pointer.get("activeVersion") if isinstance(pointer, dict) else None
    return {
        "ledgerSchemaVersion": LEDGER_SCHEMA_VERSION,
        "generatedAt": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "publicationVersion": version,
        "candidateGenerationId": pointer.get("candidateGenerationId") if isinstance(pointer, dict) else None,
        "sourceRunSetDigest": pointer.get("sourceRunSetDigest") if isinstance(pointer, dict) else None,
        "currentCandidates": len(rows),
        "summary": {
            "approved_public": sum(1 for r in rows if r["decision"] == "approved_public"),
            "blocked": sum(1 for r in rows if r["decision"] == "blocked"),
            "blockerCounts": {
                code: sum(1 for r in rows if code in r["blockers"])
                for code in (
                    "unconfirmed_pay_evidence",
                    "unspecified_scope",
                    "evidence_changed_since_review",
                    "trilingual_review_missing",
                    "review_incomplete",
                )
            },
            "unknownAttributeCounts": {
                "degree_unstated": sum(
                    1 for r in rows if r.get("minimumDegree") in (None, "unknown")
                ),
                "doctoral_enrollment_unspecified": sum(
                    1 for r in rows if r.get("doctoralEnrollment") in (None, "unspecified")
                ),
            },
        },
        "bySchool": by_school,
        "claimBoundary": (
            "One decision per current candidate. blocked rows carry explicit "
            "blockers; nothing is approved by this ledger. Counts describe "
            "the candidate file at generation time and age with new scans."
        ),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the candidate disposition ledger")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--generated-at", type=str, default=None)
    args = parser.parse_args()
    pointer = read_json(POINTER, {})
    published_ids: set[str] = set()
    if isinstance(pointer, dict) and pointer.get("snapshotDir"):
        snapshot_jobs = read_json(ROOT / "data" / "published" / pointer["snapshotDir"] / "browse" / "nine-hei-jobs.json", {})
        for job in snapshot_jobs.get("jobs") or []:
            if isinstance(job, dict) and job.get("id"):
                published_ids.add(job["id"])
    payload = build_ledger(
        read_json(CANDIDATES, {}),
        published_ids,
        pointer if isinstance(pointer, dict) else {},
        generated_at=args.generated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.output)
    print(
        json.dumps(
            {
                "currentCandidates": payload["currentCandidates"],
                "summary": payload["summary"],
                "publicationVersion": payload["publicationVersion"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

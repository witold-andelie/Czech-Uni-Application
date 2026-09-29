"""Triage current vacancy deltas without re-reviewing unchanged approved jobs.

Reads the saved candidate and disposition files; writes operator packets under
work/ only. It neither approves translations nor publishes a snapshot.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "data" / "sources"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_queue(jobs_payload: dict, ledger: dict, reviews_payload: dict) -> dict:
    jobs = {row["id"]: row for row in jobs_payload.get("jobs") or []}
    reviews = reviews_payload.get("reviews") or {}
    packets: list[dict] = []
    carried = 0
    diagnostics: list[dict] = []
    for row in ledger.get("rows") or []:
        ident = row["candidateId"]
        job = jobs.get(ident)
        if not job:
            diagnostics.append({"candidateId": ident, "reason": "ledger_job_missing"})
            continue
        review = reviews.get(ident) or {}
        same_review = (
            job.get("translationStatus") == "verified"
            and review.get("sourceHash") == job.get("sourceHash")
            and review.get("factHash") == (job.get("translationReview") or {}).get("factHash")
            and all((review.get("locales") or {}).get(locale, {}).get("status") == "reviewed"
                    for locale in ("zh-CN", "en", "cs"))
        )
        if row.get("decision") == "approved_public" and same_review:
            carried += 1
            continue
        url = job.get("applicationUrl") or job.get("sourceUrl") or ""
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            diagnostics.append({"candidateId": ident, "reason": "invalid_official_target"})
            continue
        blockers = list(row.get("blockers") or [])
        if same_review and not blockers:
            action = "live_evidence_recheck"
        elif "evidence_changed_since_review" in blockers or job.get("translationStatus") == "stale":
            action = "source_and_fact_re_review"
        elif job.get("translationStatus") in {"draft", "unreviewed"}:
            action = "trilingual_review"
        else:
            action = "scope_or_other_review"
        packets.append({
            "candidateId": ident, "employerId": row.get("employerId"),
            "title": job.get("originalText") or job.get("title"),
            "officialTarget": url, "action": action,
            "blockers": blockers, "sourceHash": job.get("sourceHash"),
            "reviewedSourceHash": review.get("sourceHash"),
            "sourceFetchedAt": job.get("sourceFetchedAt"),
            "lastStatusCheckedAt": job.get("lastStatusCheckedAt"),
            "nearestDeadline": row.get("nearestDeadline"),
            "translationStatus": job.get("translationStatus"),
        })
    priority = {"source_and_fact_re_review": 0, "trilingual_review": 1,
                "scope_or_other_review": 2, "live_evidence_recheck": 3}
    packets.sort(key=lambda item: (priority[item["action"]], item["employerId"] or "", item["candidateId"]))
    by_school: dict[str, dict[str, int]] = defaultdict(dict)
    for school in sorted({p["employerId"] for p in packets if p["employerId"]}):
        by_school[school] = dict(sorted(Counter(p["action"] for p in packets if p["employerId"] == school).items()))
    return {
        "schemaVersion": 1,
        "purpose": "operator_triage_only; no automatic approval or publication",
        "candidateGenerationId": ledger.get("candidateGenerationId"),
        "sourceRunSetDigest": ledger.get("sourceRunSetDigest"),
        "candidateGeneratedAt": jobs_payload.get("generatedAt"),
        "ledgerGeneratedAt": ledger.get("generatedAt"),
        "summary": {"currentCandidates": len(ledger.get("rows") or []),
                    "unchangedApprovedCarriedForward": carried,
                    "pendingPackets": len(packets),
                    "actions": dict(sorted(Counter(p["action"] for p in packets).items())),
                    "diagnostics": len(diagnostics)},
        "bySchool": dict(by_school), "packets": packets, "diagnostics": diagnostics,
    }


def markdown_packets(queue: dict, *, limit: int = 25) -> str:
    lines = ["# Incremental vacancy review packets", "",
             "This is a triage aid, not an approval. Keep unchanged reviewed jobs' existing approvals.",
             "Open the official vacancy for fresh evidence before changing facts or publishing.", ""]
    for item in queue["packets"][:limit]:
        lines += [f"## {item['candidateId']}", "",
                  f"- School: `{item['employerId']}`; action: `{item['action']}`",
                  f"- Official target: {item['officialTarget']}",
                  f"- Blockers: {', '.join(item['blockers']) or 'live publication evidence needs checking'}",
                  f"- Candidate hash: `{item['sourceHash']}`; reviewed hash: `{item['reviewedSourceHash']}`",
                  f"- Source fetched: {item['sourceFetchedAt']}; last status check: {item['lastStatusCheckedAt']}; nearest deadline: {item['nearestDeadline']}",
                  "- [ ] Confirm the current official vacancy text, employer, scope, degree, doctoral registration, compensation, and application window.",
                  "- [ ] If facts or source changed, review zh-CN, en, and cs against the new source/fact hashes; preserve unknown values as unknown.",
                  "- [ ] Record per-locale review and live-evidence result in the existing source files, then run publication gates.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output", type=Path, default=ROOT / "work" / "incremental-job-review-queue.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "work" / "incremental-job-review-packets.md")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    queue = build_queue(read_json(SOURCES / "browse" / "nine-hei-jobs.json"),
                        read_json(SOURCES / "coverage" / "candidate-disposition.json"),
                        read_json(SOURCES / "reviews" / "job-translations.json"))
    for path, data in ((args.output, json.dumps(queue, ensure_ascii=False, indent=2) + "\n"),
                       (args.markdown, markdown_packets(queue, limit=args.limit) + "\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
    print(json.dumps(queue["summary"], ensure_ascii=False))
    print(f"Queue: {args.output}\nPackets: {args.markdown}")


if __name__ == "__main__":
    main()

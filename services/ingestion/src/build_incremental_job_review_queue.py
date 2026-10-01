"""Triage current vacancy deltas without re-reviewing unchanged approved jobs.

Reads the saved candidate and disposition files; writes operator packets under
work/ only. It neither approves translations nor publishes a snapshot.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "data" / "sources"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _deadlines(jobs_payload: dict) -> dict[str, str]:
    """Latest announced closing date per job, from the candidate file's windows."""
    latest: dict[str, str] = {}
    for window in jobs_payload.get("windows") or []:
        if not isinstance(window, dict) or not window.get("ownerId") or not window.get("closesAt"):
            continue
        owner, closes = str(window["ownerId"]), str(window["closesAt"])[:10]
        if closes > latest.get(owner, ""):
            latest[owner] = closes
    return latest


def _display_title(job: dict) -> str:
    title = job.get("title")
    if isinstance(title, dict):
        title = title.get("cs") or title.get("en") or title.get("zh-CN")
    return str(job.get("originalText") or title or "")


def _new_candidate_rows(jobs_payload: dict, ledger: dict, today: str) -> tuple[list[dict], list[dict], int]:
    """Ledger-shaped rows for harvested jobs the ledger has not seen yet.

    The ledger is regenerated with a publication, not with each daily harvest,
    so a queue built from it alone never showed new candidates (2026-10-01:
    225 of 350 harvested jobs were outside it). Closed or expired jobs are not
    worth a review. Jobs with no research/technical track, or that the source
    adapter marked excluded, go to a scope screen instead of review packets;
    they are listed, not dropped, because the full notice can still prove
    technical duties (A38).
    """
    known = {str(row.get("candidateId")) for row in ledger.get("rows") or []}
    deadlines = _deadlines(jobs_payload)
    rows: list[dict] = []
    screen: list[dict] = []
    closed = 0
    for job in jobs_payload.get("jobs") or []:
        ident = str(job.get("id") or "")
        if not ident or ident in known:
            continue
        deadline = deadlines.get(ident)
        if job.get("lifecycleStatus") in {"closed", "expired"} or (today and deadline and deadline < today):
            closed += 1
            continue
        if not job.get("track") or job.get("catalogueScopeStatus") == "excluded":
            screen.append({
                "candidateId": ident,
                "employerId": job.get("employerId"),
                "title": _display_title(job),
                "officialTarget": job.get("applicationUrl") or job.get("sourceUrl"),
                "reason": (
                    "excluded_by_source"
                    if job.get("catalogueScopeStatus") == "excluded"
                    else "no_research_or_technical_track"
                ),
            })
            continue
        rows.append({
            "candidateId": ident,
            "employerId": job.get("employerId"),
            "decision": "new_candidate",
            "blockers": ["not_in_disposition_ledger"],
            "nearestDeadline": deadline,
        })
    return rows, screen, closed


def build_queue(jobs_payload: dict, ledger: dict, reviews_payload: dict, *, today: str = "") -> dict:
    jobs = {row["id"]: row for row in jobs_payload.get("jobs") or []}
    reviews = reviews_payload.get("reviews") or {}
    packets: list[dict] = []
    carried = 0
    diagnostics: list[dict] = []
    new_rows, scope_screen, closed_new = _new_candidate_rows(jobs_payload, ledger, today)
    deadlines = _deadlines(jobs_payload)
    not_listed = 0
    for row in list(ledger.get("rows") or []) + new_rows:
        ident = row["candidateId"]
        job = jobs.get(ident)
        if not job:
            diagnostics.append({"candidateId": ident, "reason": "ledger_job_missing"})
            continue
        # A record no longer listed (closed, expired, gone from a complete
        # official listing, or past its stated deadline) is not shown, so it is
        # not worth a review; it keeps its identity (A101).
        deadline = deadlines.get(ident)
        if job.get("lifecycleStatus") in {"closed", "expired", "unavailable"} or (
            today and deadline and deadline < today
        ):
            not_listed += 1
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
        if row.get("decision") == "new_candidate" and job.get("publicationStatus") == "approved" and same_review:
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
            "title": _display_title(job),
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
                    "newCandidatesOutsideLedger": len(new_rows),
                    "newClosedOrExpiredSkipped": closed_new,
                    "notListedSkipped": not_listed,
                    "scopeScreen": len(scope_screen),
                    "unchangedApprovedCarriedForward": carried,
                    "pendingPackets": len(packets),
                    "actions": dict(sorted(Counter(p["action"] for p in packets).items())),
                    "diagnostics": len(diagnostics)},
        "bySchool": dict(by_school), "packets": packets,
        "scopeScreen": sorted(scope_screen, key=lambda item: (str(item["employerId"]), item["candidateId"])),
        "diagnostics": diagnostics,
    }


def markdown_packets(queue: dict, *, limit: int = 25, school: str | None = None) -> str:
    lines = ["# Incremental vacancy review packets", "",
             "This is a triage aid, not an approval. Keep unchanged reviewed jobs' existing approvals.",
             "Open the official vacancy for fresh evidence before changing facts or publishing.", ""]
    packets = [item for item in queue["packets"] if school is None or item["employerId"] == school]
    # Grouped by school so one sitting covers one employer's notices; inside a
    # school the action priority order is kept.
    packets.sort(key=lambda item: str(item["employerId"] or ""))
    current_school = None
    for item in packets[:limit]:
        if item["employerId"] != current_school:
            current_school = item["employerId"]
            counts = queue["bySchool"].get(current_school, {})
            lines += [f"# School `{current_school}`", "",
                      "Actions: " + ", ".join(f"{name} {count}" for name, count in counts.items()), ""]
        lines += [f"## {item['candidateId']}", "",
                  f"- Title: {item['title']}",
                  f"- School: `{item['employerId']}`; action: `{item['action']}`",
                  f"- Official target: {item['officialTarget']}",
                  f"- Blockers: {', '.join(item['blockers']) or 'live publication evidence needs checking'}",
                  f"- Candidate hash: `{item['sourceHash']}`; reviewed hash: `{item['reviewedSourceHash']}`",
                  f"- Source fetched: {item['sourceFetchedAt']}; last status check: {item['lastStatusCheckedAt']}; nearest deadline: {item['nearestDeadline']}",
                  "- [ ] Confirm the current official vacancy text, employer, scope, degree, doctoral registration, compensation, and application window.",
                  "- [ ] If facts or source changed, review zh-CN, en, and cs against the new source/fact hashes; preserve unknown values as unknown.",
                  "- [ ] Record per-locale review and live-evidence result in the existing source files, then run publication gates.", ""]
    screen = [item for item in queue.get("scopeScreen") or [] if school is None or item["employerId"] == school]
    if screen:
        lines += ["# Scope screen (not review packets)", "",
                  "No research/technical track was read from the title, or the source marked the row excluded.",
                  "Open the notice only to confirm scope: the full text may still prove technical duties (A38).", ""]
        lines += [
            f"- `{item['employerId']}` {item['candidateId']}: {item['title']} ({item['reason']}) {item['officialTarget']}"
            for item in screen
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--school", help="only this employer id in the Markdown packets, e.g. msmt-vs_24000")
    parser.add_argument("--jobs", type=Path, default=SOURCES / "browse" / "nine-hei-jobs.json")
    parser.add_argument("--output", type=Path, default=ROOT / "work" / "incremental-job-review-queue.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "work" / "incremental-job-review-packets.md")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    queue = build_queue(read_json(args.jobs),
                        read_json(SOURCES / "coverage" / "candidate-disposition.json"),
                        read_json(SOURCES / "reviews" / "job-translations.json"),
                        today=datetime.now(ZoneInfo("Europe/Prague")).date().isoformat())
    for path, data in ((args.output, json.dumps(queue, ensure_ascii=False, indent=2) + "\n"),
                       (args.markdown, markdown_packets(queue, limit=args.limit, school=args.school) + "\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
    print(json.dumps(queue["summary"], ensure_ascii=False))
    print(f"Queue: {args.output}\nPackets: {args.markdown}")


if __name__ == "__main__":
    main()

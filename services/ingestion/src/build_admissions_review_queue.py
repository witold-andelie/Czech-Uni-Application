"""Build a read-only, incremental admissions review queue from official candidates.

This is an operator aid, not an approval or publication step. It writes only
under work/ by default, never to Supabase or data/published/. Exact register
identity and a school-owned programme link are prerequisites for a review row.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from resolve_programme_links import normalise

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "data" / "sources"
DEFAULT_CANDIDATES = (
    SOURCES / "admissions" / "czu-english-programmes.json",
    SOURCES / "admissions" / "czu-czech-programmes.json",
)
HEX_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
MAX_SOURCE_AGE_HOURS = 48


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iso_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def clean_hash(value: object) -> str | None:
    if not isinstance(value, str) or not HEX_SHA256.fullmatch(value):
        return None
    return value.removeprefix("sha256:")


def candidate_title(candidate: dict) -> str:
    titles = candidate.get("titles") or {}
    source_language = candidate.get("sourceLanguage")
    return str(titles.get(source_language) or titles.get("en") or titles.get("cs") or "")


def official_url(candidate: dict, catalogue_url: str) -> str | None:
    url = candidate.get("officialProgrammeUrl")
    catalogue_host = urlparse(catalogue_url).hostname
    parsed = urlparse(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme != "https" or not parsed.hostname or parsed.hostname != catalogue_host:
        return None
    return url


def candidate_facts(candidate: dict) -> dict:
    windows = candidate.get("applicationWindows") or []
    return {
        "degree": candidate.get("degree"),
        "teachingLanguage": candidate.get("studyLanguage"),
        "durationYears": candidate.get("durationYears"),
        "tuition": candidate.get("tuition"),
        "tuitionEu": candidate.get("tuitionEu"),
        "applicationWindows": [
            {"start": row.get("start"), "end": row.get("end"), "roundOriginal": row.get("roundOriginal")}
            for row in windows if isinstance(row, dict)
        ],
        "applicationTarget": candidate.get("applyUrl"),
        "generalApplyPortal": candidate.get("generalApplyPortalUrl"),
    }


def build_queue(
    inventory: dict,
    link_index: dict,
    candidate_sources: list[tuple[str, dict]],
    reviewed: dict,
    *,
    as_of: datetime,
    max_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict:
    """Return only safe exact matches; ambiguity and bad evidence stay diagnostic."""
    as_of = as_of.astimezone(timezone.utc)
    rows_by_key: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    school_rows: Counter[str] = Counter()
    for school in inventory.get("schools") or []:
        school_id = school["id"]
        for values in school.get("rows") or []:
            ident, title, degree, _faculty, _duration, language, *_ = values
            row = {"id": ident, "title": title, "degree": degree, "language": language, "institutionId": school_id}
            rows_by_key[(school_id, normalise(title), degree, language)].append(row)
            school_rows[school_id] += 1

    links = link_index.get("links") or {}
    current_reviews = {item["id"]: item for item in reviewed.get("offerings") or []}
    evidence_by_url = {
        item.get("url"): clean_hash(item.get("sourceHash"))
        for item in reviewed.get("evidence") or []
        if isinstance(item, dict) and item.get("url")
    }
    grouped: dict[str, list[dict]] = defaultdict(list)
    diagnostics: list[dict] = []
    source_manifest: list[dict] = []
    source_candidate_ids: set[str] = set()
    source_id_prefixes: set[str] = set()

    for filename, payload in candidate_sources:
        source_time = iso_time(payload["generatedAt"])
        age_hours = round(max(0.0, (as_of - source_time).total_seconds() / 3600), 1)
        stale = age_hours > max_age_hours
        source_manifest.append({
            "file": filename,
            "institutionId": payload.get("institutionId"),
            "generatedAt": payload["generatedAt"],
            "ageHours": age_hours,
            "stale": stale,
            "candidateCount": len(payload.get("programmes") or []),
            "declaredComplete": payload.get("coverage", {}).get("complete"),
        })
        catalogue_url = (payload.get("sourceUrls") or {}).get("catalogue") or ""
        for candidate in payload.get("programmes") or []:
            candidate_id = candidate.get("id")
            if isinstance(candidate_id, str):
                source_candidate_ids.add(candidate_id)
                source_id_prefixes.add(re.sub(r"-\d+$", "", candidate_id))
            title = candidate_title(candidate)
            key = (candidate.get("institutionId"), normalise(title), candidate.get("degree"), candidate.get("studyLanguage"))
            matches = rows_by_key.get(key, [])
            url = official_url(candidate, catalogue_url)
            source_hash = clean_hash(candidate.get("sourceHtmlSha256"))
            reason = None
            if not title or not matches:
                reason = "no_exact_register_row"
            elif len(matches) != 1:
                reason = "ambiguous_register_rows"
            elif not url:
                reason = "invalid_official_url"
            elif not source_hash:
                reason = "missing_source_hash"
            elif matches[0]["id"] not in links:
                reason = "school_programme_link_unresolved"
            else:
                link = links[matches[0]["id"]]
                if (
                    link.get("kind") != "school_programme_page"
                    or link.get("institutionId") != key[0]
                    or link.get("degree") != key[2]
                    or link.get("language") != key[3]
                ):
                    reason = "link_identity_mismatch"
            if reason:
                diagnostics.append({
                    "candidateId": candidate.get("id"), "sourceFile": filename,
                    "institutionId": candidate.get("institutionId"), "title": title,
                    "reason": reason, "matchingRegisterIds": [row["id"] for row in matches],
                })
                continue
            grouped[matches[0]["id"]].append({
                "candidateId": candidate["id"], "sourceFile": filename,
                "sourceLanguage": candidate.get("sourceLanguage"),
                "sourceGeneratedAt": payload["generatedAt"], "sourceAgeHours": age_hours,
                "staleSource": stale, "sourceHash": f"sha256:{source_hash}",
                "officialProgrammeUrl": url, "facts": candidate_facts(candidate),
            })

    items: list[dict] = []
    for ident, candidates in grouped.items():
        candidates.sort(key=lambda row: (row["sourceFile"], row["candidateId"]))
        link = links[ident]
        reviewed_offering = current_reviews.get(ident)
        warnings: list[str] = []
        if any(item["staleSource"] for item in candidates):
            warnings.append("source_extract_older_than_limit; recheck live official pages before approval")
        if any(item["officialProgrammeUrl"] != link["url"] for item in candidates):
            warnings.append("candidate_url_differs_from_resolved_school_page; verify same programme")

        if reviewed_offering:
            approved_ids = set(reviewed_offering.get("candidateIds") or [])
            current_ids = {item["candidateId"] for item in candidates}
            if not approved_ids.issubset(current_ids):
                status = "reviewed_candidate_missing"
            elif any(
                evidence_by_url.get(item["officialProgrammeUrl"]) != clean_hash(item["sourceHash"])
                for item in candidates if item["candidateId"] in approved_ids
            ):
                status = "reviewed_source_changed"
            elif current_ids - approved_ids:
                status = "new_corrob_source"
            else:
                status = "reviewed_unchanged"
        else:
            status = "refresh_before_review" if any(item["staleSource"] for item in candidates) else "new_review"

        first = candidates[0]
        facts = first["facts"]
        priority = (
            2 * (status in {"reviewed_source_changed", "reviewed_candidate_missing"})
            + 2 * (len(candidates) > 1)
            + bool(facts["applicationWindows"])
            + bool(facts["tuition"])
            + (link.get("reachability") == "verified")
        )
        items.append({
            "inventoryId": ident, "institutionId": link["institutionId"],
            "title": link["rowTitle"], "degree": link["degree"],
            "teachingLanguage": link["language"], "schoolProgrammeUrl": link["url"],
            "linkReachability": link.get("reachability"), "status": status,
            "priority": int(priority), "warnings": warnings,
            "reviewedAt": reviewed_offering.get("factsReviewedAt") if reviewed_offering else None,
            "candidates": candidates,
        })
    for ident, offering in current_reviews.items():
        if ident in grouped or offering.get("institutionId") not in {row["institutionId"] for row in source_manifest}:
            continue
        approved_ids = offering.get("candidateIds") or []
        if not any(re.sub(r"-\d+$", "", candidate_id) in source_id_prefixes for candidate_id in approved_ids):
            continue
        link = links.get(ident) or {}
        items.append({
            "inventoryId": ident, "institutionId": offering["institutionId"],
            "title": offering.get("titleOriginal"), "degree": offering.get("degree"),
            "teachingLanguage": (offering.get("teachingLanguages") or [None])[0],
            "schoolProgrammeUrl": link.get("url") or offering.get("officialProgrammeUrl"),
            "linkReachability": link.get("reachability"),
            "status": "reviewed_candidate_missing", "priority": 10,
            "warnings": ["previously reviewed candidate is absent from the current source; do not infer programme closure"],
            "reviewedAt": offering.get("factsReviewedAt"), "candidates": [],
            "missingCandidateIds": [candidate_id for candidate_id in approved_ids if candidate_id not in source_candidate_ids],
        })
    items.sort(key=lambda row: (-row["priority"], row["institutionId"], row["title"], row["inventoryId"]))
    diagnostics.sort(key=lambda row: (row["sourceFile"], str(row["candidateId"])))
    status_counts = Counter(row["status"] for row in items)
    mapped_by_school = Counter(row["institutionId"] for row in items)
    unmatched_by_school = dict(sorted(
        (school, count - mapped_by_school[school])
        for school, count in Counter(link["institutionId"] for link in links.values()).items()
        if count > mapped_by_school[school]
    ))
    return {
        "schemaVersion": 1,
        "asOf": as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "purpose": "operator_review_queue_only; never an approval or publication",
        "maxSourceAgeHours": max_age_hours,
        "sourceManifest": source_manifest,
        "summary": {
            "registerRows": sum(school_rows.values()),
            "resolvedSchoolPages": len(links),
            "mappedReviewRows": len(items),
            "candidateRecords": sum(row["candidateCount"] for row in source_manifest),
            "diagnosticCandidates": len(diagnostics),
            "statuses": dict(sorted(status_counts.items())),
            "resolvedPagesWithoutStructuredCandidate": sum(unmatched_by_school.values()),
        },
        "unmatchedResolvedPagesBySchool": unmatched_by_school,
        "items": items,
        "diagnostics": diagnostics,
    }


def review_packet_markdown(queue: dict, *, school: str | None = None, limit: int = 25) -> str:
    pending = [row for row in queue["items"] if row["status"] != "reviewed_unchanged"]
    if school:
        pending = [row for row in pending if row["institutionId"] == school]
    lines = [
        "# Incremental admissions review packets",
        "",
        f"As of {queue['asOf']}. This file is an operator checklist, not an approval.",
        "Keep old approved records unchanged unless their source or facts changed.",
        "Never publish from a stale extract without checking the live official page.",
        "",
    ]
    for row in pending[:limit]:
        lines.extend([
            f"## {row['inventoryId']} — {row['title']}",
            "",
            f"- School: `{row['institutionId']}`; degree: `{row['degree']}`; teaching language: `{row['teachingLanguage']}`",
            f"- Queue state: `{row['status']}`; resolved school page: {row['schoolProgrammeUrl']}",
            f"- Warnings: {', '.join(row['warnings']) if row['warnings'] else 'none'}",
        ])
        for candidate in row["candidates"]:
            facts = candidate["facts"]
            lines.extend([
                f"- Candidate `{candidate['candidateId']}` ({candidate['sourceFile']}; fetched {candidate['sourceGeneratedAt']}; hash `{candidate['sourceHash']}`): {candidate['officialProgrammeUrl']}",
                f"  - Duration: {facts['durationYears']}; tuition: {facts['tuition']}; EU tuition: {facts['tuitionEu']}; windows: {facts['applicationWindows']}",
            ])
        lines.extend([
            "- [ ] Open the current official programme and faculty admissions pages; resolve identity, level, language, dates, fee scope, and any conflicting source statements.",
            "- [ ] Record the current evidence hash and exact source URL; do not treat an old candidate hash as a fresh live hash.",
            "- [ ] Review zh-CN, en, and cs titles and every published factual note against the same evidence version.",
            "- [ ] Bind the reviewed fact, source, and per-locale content hashes through the existing publisher; run source and snapshot validation.",
            "",
        ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-file", action="append", type=Path, help="Repeat to replace the default CZU candidate sources")
    parser.add_argument("--as-of", help="UTC ISO timestamp for reproducible age checks (default: now)")
    parser.add_argument("--school", help="Limit the Markdown review packets to one institution ID")
    parser.add_argument("--limit", type=int, default=25, help="Maximum Markdown packets (default 25)")
    parser.add_argument("--output", type=Path, default=ROOT / "work" / "admissions-review-queue.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "work" / "admissions-review-packets.md")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    as_of = iso_time(args.as_of) if args.as_of else datetime.now(timezone.utc)
    candidate_files = args.candidate_file or list(DEFAULT_CANDIDATES)
    queue = build_queue(
        read_json(SOURCES / "browse" / "nine-hei-inventory.json"),
        read_json(SOURCES / "admissions" / "programme-links.json"),
        [(path.name, read_json(path)) for path in candidate_files],
        read_json(SOURCES / "admissions" / "reviewed-offerings.json"),
        as_of=as_of,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(review_packet_markdown(queue, school=args.school, limit=args.limit) + "\n", encoding="utf-8")
    print(json.dumps(queue["summary"], ensure_ascii=False))
    print(f"Queue: {args.output}\nReview packets: {args.markdown}")


if __name__ == "__main__":
    main()

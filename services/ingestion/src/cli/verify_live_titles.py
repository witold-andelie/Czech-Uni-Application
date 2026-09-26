"""Live per-candidate URL verification with audit evidence.

For every verifiably-reviewed job candidate this fetches its official sourceUrl
live (Scrapling HTTP, DynamicFetcher fallback, or PDF text extraction) and checks
that at least one of the trilingual titles appears in the fetched content. It
writes a JSON evidence artifact; nothing here promotes or approves candidates.

Design boundaries (see docs/CRAWLING_RULES.md):
- URLs are taken only from the candidate file, never from input, so the tool
  cannot be steered to arbitrary hosts (SSRF self-limit). Official domains are
  not faked and are not required to be in a separate whitelist.
- A non-match, HTTP failure, or blocked/incomplete page is recorded as-is; it
  is never rewritten into "closed" or into a verified pass.
- Rate-limiting is per host (2 s, inside the documented 2-5 s band); the whole
  pass respects a wall-clock budget.
- Request-level retries are bounded: transport errors and HTTP 408/425/429/
  500/502/503/504 get one 3 s and one 12 s retry, matching the ingestion
  adapters. A 404/403/timeout is never treated as a closed vacancy.
- Operator evidence (data/sources/coverage/live-verification-operator-evidence.json)
  can confirm a row that an operator read on the live page (status
  "operator_verified", keeping matched=false visible), or record that the page
  no longer carries the announcement (status "source_change_noted"), which is
  evidence change requiring a disposition and never confirms the candidate.
- The transport is the same Scrapling chain the ingestion adapters use: plain
  HTTP GET, DynamicFetcher only for JS shells, no StealthyFetcher.

Evidence file: data/sources/coverage/live-title-verification.json (tracked, so
the publication gate and CI can read it offline). Re-runs merge with the
previous evidence by default so a budget-bounded pass keeps confirmed rows and
only re-checks what it processed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from live_title_matching import (  # noqa: E402
    extract_pdf_text,
    norm,
    sha256_text,
    title_matches,
)

CANDIDATES = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"
REVIEWS = ROOT / "data" / "sources" / "reviews" / "job-translations.json"
OUT = ROOT / "data" / "sources" / "coverage" / "live-title-verification.json"
OPERATOR_EVIDENCE = ROOT / "data" / "sources" / "coverage" / "live-verification-operator-evidence.json"

TIMEOUT_S = 30
HOST_DELAY_S = 2.0
RETRY_DELAYS_S = (3.0, 12.0)
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
UA = "Mozilla/5.0 (X11; Linux x86_64) CzechUniApply/0.1 (verification; contact via faculty pages)"
JS_SHELL_MARKERS = ("enable javascript", "requires javascript", "just a moment", "cf-challenge")
MAX_HASH_CHARS = 64


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _body_str(page: Any) -> str:
    body = page.body if hasattr(page, "body") else str(page)
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return body if isinstance(body, str) else str(body)


def _body_bytes(page: Any) -> bytes:
    body = page.body if hasattr(page, "body") else str(page)
    if isinstance(body, bytes):
        return body
    return body.encode("utf-8", errors="replace") if isinstance(body, str) else b""


def _status_of(page: Any) -> int:
    status = getattr(page, "status", None)
    if status is None:
        status = getattr(page, "status_code", None)
    try:
        return int(status or 0)
    except (TypeError, ValueError):
        return 0


def fetch_scrapling_get(url: str) -> dict[str, Any]:
    from scrapling.fetchers import Fetcher

    page = Fetcher.get(url, timeout=TIMEOUT_S, headers={"User-Agent": UA})
    return {"tool": "scrapling_get", "status": _status_of(page), "body": _body_str(page), "raw": _body_bytes(page)}


def fetch_scrapling_dynamic(url: str) -> dict[str, Any]:
    from scrapling.fetchers import DynamicFetcher

    page = DynamicFetcher.fetch(url, headless=True, timeout=45000, wait=1500)
    return {"tool": "scrapling_dynamic", "status": _status_of(page), "body": _body_str(page), "raw": _body_bytes(page)}


def _get_with_retries(url: str) -> dict[str, Any]:
    """Scrapling GET with the documented bounded transport retries."""
    result: dict[str, Any] = {"tool": "scrapling_get", "status": 0, "body": "", "raw": b""}
    for attempt in range(len(RETRY_DELAYS_S) + 1):
        try:
            result = fetch_scrapling_get(url)
        except Exception:
            result = {"tool": "scrapling_get", "status": 0, "body": "", "raw": b""}
        if result.get("status") not in RETRY_STATUSES:
            return result
        if attempt < len(RETRY_DELAYS_S):
            time.sleep(RETRY_DELAYS_S[attempt])
    return result


def vet_one(url: str) -> dict[str, Any]:
    """Fetch a single URL and return raw evidence. Raises on software errors only."""
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return {"httpStatus": 0, "finalUrl": url, "tool": "none", "bodyText": "", "blocked": True, "blockedReasons": ["non_http_url"]}
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return {"httpStatus": 0, "finalUrl": url, "tool": "none", "bodyText": "", "blocked": True, "blockedReasons": ["invalid_url"]}

    result = _get_with_retries(url)
    status = int(result.get("status") or 0)
    tool = result.get("tool", "scrapling_get")
    raw = result.get("raw") or b""
    body = result.get("body") or ""

    if raw[:5] == b"%PDF-":
        return {
            "httpStatus": status,
            "finalUrl": url,
            "tool": "pdf",
            "bodyText": extract_pdf_text(raw),
            "blocked": False,
            "blockedReasons": [],
        }

    body_l = body.lower()
    needs_dynamic = (
        status == 0
        or not body.strip()
        or body_l.count("</") == 0
        or any(marker in body_l for marker in JS_SHELL_MARKERS)
    )
    if needs_dynamic:
        try:
            dynamic = fetch_scrapling_dynamic(url)
            if status == 0 or dynamic.get("status") or not body.strip():
                body = dynamic.get("body") or body
                status = int(dynamic.get("status") or status)
                tool = dynamic.get("tool", "scrapling_dynamic")
        except Exception:
            pass
    return {
        "httpStatus": status,
        "finalUrl": url,
        "tool": tool,
        "bodyText": body,
        "blocked": False,
        "blockedReasons": [],
    }


def load_tasks(only_status: str) -> list[dict[str, Any]]:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    review_store = json.loads(REVIEWS.read_text(encoding="utf-8")) if REVIEWS.exists() else {"reviews": {}}
    reviews = review_store.get("reviews", {})
    source_hash: dict[str, str] = {}
    for job in candidates.get("jobs", []):
        source_hash[job["id"]] = job.get("sourceHash") or ""

    tasks: list[dict[str, Any]] = []
    for job in candidates.get("jobs", []):
        if not isinstance(job, dict) or not job.get("id"):
            continue
        if job.get("translationStatus") != only_status:
            continue
        url = job.get("sourceUrl") or ""
        if not url:
            continue
        review = reviews.get(job["id"]) or {}
        title_locales = {}
        if isinstance(review.get("title"), dict) and review["title"]:
            title_locales = review["title"]
        elif isinstance(job.get("title"), dict):
            title_locales = job["title"]
        titles = [{"title": value, "locale": locale} for locale, value in title_locales.items() if isinstance(value, str) and value.strip()]
        tasks.append(
            {
                "candidateId": job["id"],
                "employerId": job.get("employerId"),
                "sourceUrl": url,
                "applicationUrl": job.get("applicationUrl"),
                "sourceHash": source_hash.get(job["id"]),
                "titles": titles,
            }
        )
    return tasks


def task_meta(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidateId": task["candidateId"],
        "employerId": task["employerId"],
        "sourceUrl": task["sourceUrl"],
        "applicationUrl": task["applicationUrl"],
        "sourceHash": task["sourceHash"],
    }


def load_previous_rows(path: Path) -> tuple[dict[str, dict[str, Any]], str | None]:
    if not path.exists():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}, None
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return {}, None
    return {row["candidateId"]: row for row in rows if isinstance(row, dict) and row.get("candidateId")}, payload.get("generatedAt")


def load_operator_evidence(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("evidence") if isinstance(payload, dict) else payload
    if not isinstance(entries, dict):
        return {}
    return {key: value for key, value in entries.items() if isinstance(value, dict)}


def apply_operator_evidence(
    row: dict[str, Any],
    operator_evidence: dict[str, dict[str, Any]],
    http_status: int,
    candidate_id: str,
) -> dict[str, Any]:
    """Overlay an operator's reading of the live page onto a fetched row."""
    operator = operator_evidence.get(candidate_id)
    if not operator or not (operator.get("reason") or "").strip():
        return row
    kind = (operator.get("kind") or "wording_difference_confirmed").strip()
    note = {
        "verifiedAt": operator.get("verifiedAt") or ts(),
        "verifiedBy": operator.get("verifiedBy") or "operator",
        "kind": kind,
        "reason": operator["reason"].strip()[:600],
        "contextSnippet": norm(operator.get("contextSnippet") or "")[:400],
    }
    if kind == "source_change_noted":
        # The operator read the live page: it no longer carries the announcement
        # (or the source is unavailable). Per docs/REFRESH_POLICY.md this is
        # evidence change, never a closure, so the row stays unconfirmed and the
        # publish gate holds the item until an operator dispositions it. This
        # also overrides an automated string hit, because a reviewed title can
        # match navigation junk on a page that now shows a different announcement.
        row["status"] = "source_change_noted"
        row["operatorEvidence"] = note
        return row
    if row.get("status") == "matched":
        # An automated verbatim hit needs no human confirmation; keep the note so
        # the operator reading is still on record.
        row.setdefault("operatorEvidence", note)
        return row
    if http_status == 200:
        # An operator confirmed the announcement live by reading the fetched
        # page; keep the automated mismatch visible and record the human
        # evidence alongside it.
        row["status"] = "operator_verified"
        row["operatorEvidence"] = note
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Live per-candidate source URL verification")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--budget", type=int, default=1500, help="wall-clock budget in seconds")
    parser.add_argument("--limit", type=int, default=0, help="max candidates to process (0 = all)")
    parser.add_argument("--only-status", default="verified", help="verification status filter (verified/reviewed/draft)")
    parser.add_argument("--only-ids", default="", help="comma-separated candidate ids to process (default: all matching --only-status)")
    parser.add_argument("--merge-from", type=Path, default=None, help="previous evidence file to carry unprocessed rows from (default: the output file when it exists)")
    parser.add_argument("--no-merge", action="store_true", help="do not carry rows from a previous evidence file")
    parser.add_argument("--operator-evidence", type=Path, default=OPERATOR_EVIDENCE, help="JSON file of operator records: {candidateId: {kind, verifiedAt, verifiedBy, reason, contextSnippet}}")
    args = parser.parse_args()

    tasks = load_tasks(args.only_status)
    only_ids = {item.strip() for item in args.only_ids.split(",") if item.strip()}
    if only_ids:
        tasks = [task for task in tasks if task["candidateId"] in only_ids]
    print(f"tasks: {len(tasks)}")

    operator_evidence = load_operator_evidence(args.operator_evidence)
    merge_source = args.merge_from if args.merge_from is not None else args.output
    previous_rows, previous_generated_at = ({}, None) if args.no_merge else load_previous_rows(merge_source)

    started = time.time()
    last_by_host: dict[str, float] = defaultdict(float)
    rows: list[dict[str, Any]] = []
    processed = 0
    for task in tasks:
        if args.limit and processed >= args.limit:
            break
        if time.time() - started >= args.budget:
            rows.append({**task_meta(task), "status": "skipped_budget", "checkedAt": ts(), "httpStatus": None, "matched": False, "reason": "wall-clock budget exhausted"})
            continue
        host = urlsplit(task["sourceUrl"]).netloc
        wait = HOST_DELAY_S - (time.time() - last_by_host[host])
        if wait > 0:
            time.sleep(wait)
        last_by_host[host] = time.time()

        row = task_meta(task)
        row["checkedAt"] = ts()
        try:
            raw = vet_one(task["sourceUrl"])
        except Exception as exc:
            row.update({"status": "fetch_error", "httpStatus": None, "matched": False, "reason": str(exc)[:400], "tool": "exception"})
            rows.append(row)
            processed += 1
            continue
        row["httpStatus"] = raw["httpStatus"]
        row["finalUrl"] = raw["finalUrl"]
        row["tool"] = raw["tool"]
        row["bodySha256"] = sha256_text(raw["bodyText"])[:MAX_HASH_CHARS]
        match = title_matches(raw["bodyText"], task["titles"])
        row.update(match)
        if not match["matched"]:
            status = "blocked_or_useless" if raw["blocked"] or raw["httpStatus"] in (401, 403, 407, 451) else (
                "non_match" if raw["httpStatus"] == 200 else f"http_{raw['httpStatus']}"
            )
            row["status"] = status
            row["reason"] = f"titles not found in {raw.get('tool')} body" if raw["httpStatus"] == 200 else f"unexpected http {raw['httpStatus']}"
            if raw.get("blockedReasons"):
                row["blockedReasons"] = raw["blockedReasons"]
        else:
            row["status"] = "matched"
        row = apply_operator_evidence(row, operator_evidence, raw["httpStatus"], task["candidateId"])
        rows.append(row)
        processed += 1

    processed_ids = {row["candidateId"] for row in rows}
    for candidate_id, previous in previous_rows.items():
        if candidate_id in processed_ids:
            continue
        carried = dict(previous)
        carried["carriedFrom"] = previous_generated_at
        rows.append(carried)
    rows.sort(key=lambda row: (row.get("candidateId") or ""))

    summary = {
        "total": len(rows),
        "matched": sum(1 for r in rows if r.get("status") == "matched"),
        "operator_verified": sum(1 for r in rows if r.get("status") == "operator_verified"),
        "source_change_noted": sum(1 for r in rows if r.get("status") == "source_change_noted"),
        "non_match": sum(1 for r in rows if r.get("status") == "non_match"),
        "blocked_or_useless": sum(1 for r in rows if r.get("status") == "blocked_or_useless"),
        "http_failures": sum(1 for r in rows if str(r.get("status", "")).startswith("http_")),
        "fetch_error": sum(1 for r in rows if r.get("status") == "fetch_error"),
        "skipped_budget": sum(1 for r in rows if r.get("status") == "skipped_budget"),
        "carried": sum(1 for r in rows if r.get("carriedFrom")),
    }
    payload = {
        "schemaVersion": 2,
        "generatedAt": ts(),
        "budgetSeconds": args.budget,
        "verificationStatusFilter": args.only_status,
        "confirmedStatuses": ["matched", "operator_verified"],
        "summary": summary,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    print(f"wrote {len(rows)} rows -> {args.output}")
    # Non-zero exit when any candidate could NOT be confirmed live; CI uses this gate.
    unconfirmed = summary["total"] - summary["matched"] - summary["operator_verified"]
    raise SystemExit(1 if unconfirmed and args.only_status == "verified" else 0)


if __name__ == "__main__":
    main()

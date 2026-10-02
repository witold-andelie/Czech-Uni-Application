"""Automatic review of harvested vacancies (owner decision 2026-10-02).

A vacancy without a matching human review is approved for publication by
this pipeline when it passes every gate below. Its facts are the collector's
evidence-based extraction; its titles are the human-reviewed ones when the
official title is unchanged, otherwise an offline machine translation
(title_translation.py) marked "machine" per locale. A record that fails a gate
is not published and the reason is recorded; nothing is guessed.

Human reviews stay authoritative: an automatic entry is never written where a
human review still matches the record's facts, nor over an operator decision.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from harvest_nine_hei_jobs import AUTO_REVIEWS, AUTOMATIC_REVIEWER, REVIEWS, ROOT, _read_reviews
from publication_rules import JOB_FACT_NORMALIZATION_VERSION, job_fact_hash, translation_content_hash
from title_translation import LOCALES, cache_key, llama_translate, translate_title

TRANSLATIONS = ROOT / "data" / "sources" / "reviews" / "machine-title-translations.json"
JOBS = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"

CLOSED_LIFECYCLES = {"closed", "expired", "unavailable"}
# Page chrome that a listing parser once took for a vacancy (VŠTE, PEUNI).
_CHROME_RE = re.compile(
    r"^(?:top|menu|kontakt\w*|contacts?|home|úvod|uvod|přejít na hlavní obsah|skip to (?:main )?content|"
    r"škola základní informace|jsme panevropsk\w*|více|more|read more|detail)$",
    re.I,
)
_DATE_PREFIX_RE = re.compile(r"^\s*\d{1,2}\.\s?\d{1,2}\.\s?\d{4}\b")


EURAXESS_HOSTS = {"euraxess.ec.europa.eu", "www.euraxess.cz", "euraxess.cz"}
EURAXESS_SOURCE = "euraxess-cz-jobs"
_STOPWORDS = {
    "with", "focus", "position", "researcher", "research", "assistant", "professor", "faculty", "university",
    "department", "specializing", "specialising", "specialised", "specialized", "postdoctoral", "doctoral",
    "student", "field", "fields", "and", "the", "for", "position", "positions",
}


def _host(url: str) -> str:
    return urlsplit(str(url or "")).netloc.lower()


def _tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return {word for word in re.findall(r"[a-z0-9]{3,}", text)} - _STOPWORDS


def duplicate_of(job: dict, others: list[dict]) -> str | None:
    """A direct-source record of the same employer that announces the same vacancy."""
    mine = [_tokens(job.get("originalText"))] + [_tokens(v) for v in (job.get("title") or {}).values()]
    for other in others:
        theirs = [_tokens(other.get("originalText"))] + [_tokens(v) for v in (other.get("title") or {}).values()]
        for a in mine:
            for b in theirs:
                if a and b and len(a & b) / len(a | b) >= 0.6:
                    return str(other["id"])
    return None


def gate_blockers(job: dict, windows: list[dict], today: date, others: list[dict] | None = None) -> list[str]:
    """Why this record may not be approved automatically; empty when it may."""
    reasons: list[str] = []
    # EURAXESS finds vacancies; it is never the application target, and a
    # vacancy a university source already carries is published once, from it.
    if _host(job.get("sourceUrl")) in EURAXESS_HOSTS or job.get("discoverySourceId") == EURAXESS_SOURCE:
        target = job.get("applicationUrl")
        if not target or _host(target) in EURAXESS_HOSTS:
            reasons.append("no-official-application-target")
    if job.get("discoverySourceId") == EURAXESS_SOURCE and others:
        twin = duplicate_of(job, others)
        if twin:
            reasons.append(f"duplicate-of-direct-source:{twin}")
    title = str(job.get("originalText") or "").strip()
    if not job.get("track") or job.get("catalogueScopeStatus") not in (None, "included"):
        reasons.append("outside-research-catalogue-scope")
    if job.get("lifecycleStatus") in CLOSED_LIFECYCLES or job.get("visibility") == "archived":
        reasons.append("not-currently-listed")
    url = str(job.get("applicationUrl") or job.get("sourceUrl") or "")
    if not url.startswith("https://"):
        reasons.append("no-https-official-target")
    if not (6 <= len(title) <= 300) or len(re.findall(r"[^\W\d_]{2,}", title)) < 2:
        reasons.append("title-implausible")
    if _CHROME_RE.match(title) or _DATE_PREFIX_RE.match(title):
        reasons.append("title-is-page-chrome")
    for window in windows:
        closes = window.get("closesAt")
        if isinstance(closes, str) and closes[:10] < today.isoformat():
            reasons.append("deadline-passed")
            break
    if not str(job.get("sourceHash") or "").startswith("sha256:"):
        reasons.append("no-source-hash")
    return reasons


def _human_titles_still_apply(human: dict | None, job: dict) -> dict | None:
    """The human-reviewed titles, when the official title they translate is unchanged."""
    if not isinstance(human, dict):
        return None
    titles = human.get("title")
    if not isinstance(titles, dict) or not all(isinstance(titles.get(locale), str) and titles[locale].strip() for locale in LOCALES):
        return None
    original = str(job.get("originalText") or "").strip()
    reviewed_original = str(human.get("reviewedOriginalText") or "").strip()
    # Older human reviews do not record the title they translated; the stored
    # record's title then must still be the one reviewed (same source title).
    if reviewed_original and reviewed_original != original:
        return None
    return {locale: titles[locale] for locale in LOCALES}


def build_entry(job: dict, windows: list[dict], titles: dict, statuses: dict, now: str, note: str) -> dict:
    return {
        "sourceHash": job["sourceHash"],
        "evidenceHash": job["sourceHash"],
        "normalizationVersion": JOB_FACT_NORMALIZATION_VERSION,
        "reviewer": {"role": AUTOMATIC_REVIEWER},
        "reviewEventId": f"auto-{now[:10]}-{job['id']}",
        "reviewedAt": now,
        "reviewedOriginalText": job.get("originalText"),
        "reviewNote": note,
        "title": titles,
        "locales": {
            locale: {"status": statuses[locale], "reviewedAt": now, "contentHash": translation_content_hash(titles[locale])}
            for locale in LOCALES
        },
        "factHash": job_fact_hash(job, windows),
    }


def run(
    payload: dict,
    human_reviews: dict,
    auto_reviews: dict,
    translations: dict,
    *,
    today: date,
    now: str,
    translate: Callable[[str, str], dict] = llama_translate,
    max_translations: int | None = None,
) -> dict:
    """Update the automatic review entries in place; return a report."""
    windows_by_owner: dict[str, list[dict]] = {}
    for window in payload.get("windows") or []:
        if isinstance(window, dict) and window.get("ownerId"):
            windows_by_owner.setdefault(str(window["ownerId"]), []).append(window)
    report = {"approved": [], "kept": [], "withheld": {}, "humanMatches": 0, "translated": 0, "deferred": 0}
    direct_by_employer: dict[str, list[dict]] = {}
    for other in payload.get("jobs") or []:
        if other.get("discoverySourceId") != EURAXESS_SOURCE and other.get("visibility") != "archived":
            direct_by_employer.setdefault(str(other.get("employerId")), []).append(other)
    for job in payload.get("jobs") or []:
        ident = job.get("id")
        if not ident:
            continue
        windows = windows_by_owner.get(ident, [])
        human = human_reviews.get(ident)
        if isinstance(human, dict) and human.get("disposition"):
            auto_reviews.pop(ident, None)
            continue
        fact_hash = job_fact_hash(job, windows)
        if isinstance(human, dict) and human.get("factHash") == fact_hash:
            report["humanMatches"] += 1
            auto_reviews.pop(ident, None)
            continue
        blockers = gate_blockers(job, windows, today, direct_by_employer.get(str(job.get("employerId")), []))
        if blockers:
            report["withheld"][ident] = blockers
            auto_reviews.pop(ident, None)
            continue
        existing = auto_reviews.get(ident)
        if isinstance(existing, dict) and existing.get("factHash") == fact_hash and existing.get("sourceHash") == job.get("sourceHash") and existing.get("reviewedOriginalText") == job.get("originalText"):
            report["kept"].append(ident)
            continue
        titles = _human_titles_still_apply(human, job)
        if titles is not None:
            statuses = {locale: "reviewed" for locale in LOCALES}
            note = "Automatic review: facts re-bound to the current extraction; titles carried from the human review of the same official title."
        else:
            original = str(job.get("originalText") or "").strip()
            if cache_key(original) not in translations and max_translations is not None and report["translated"] >= max_translations:
                report["deferred"] += 1
                continue
            cached = cache_key(original) in translations
            result = translate_title(original, translations, translate)
            if not cached:
                report["translated"] += 1
            if result.get("problems"):
                report["withheld"][ident] = [f"translation:{problem}" for problem in result["problems"]]
                auto_reviews.pop(ident, None)
                continue
            titles = dict(result["titles"])
            statuses = {locale: ("reviewed" if locale == result["language"] else "machine") for locale in LOCALES}
            note = (
                "Automatic review: facts are the collector's evidence-based extraction; "
                f"titles machine-translated offline ({result.get('engine')}), the {result['language']} title is the official one."
            )
        auto_reviews[ident] = build_entry(job, windows, titles, statuses, now, note)
        report["approved"].append(ident)
    return report


def _write(path: Path, reviews: dict, purpose: str) -> None:
    path.write_text(
        json.dumps({"schemaVersion": 1, "note": purpose, "reviews": dict(sorted(reviews.items()))}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


SELF_TEST_TITLES = (
    "Odborný/ná pracovník/ce v analytické laboratoři (úvazek 1,0)",
    "Postdoktorská pozice ve fyzické geografii/arktickém výzkumu",
    "Assistant Professor Specialising in Applied Entomology",
)


def self_test() -> int:
    """Daily proof that the offline model answers and passes the checks."""
    failures = 0
    for title in SELF_TEST_TITLES:
        result = translate_title(title, {}, llama_translate)
        print(json.dumps(result, ensure_ascii=False))
        failures += bool(result.get("problems"))
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-translations", type=int, default=None, help="bound new model calls per run")
    parser.add_argument("--self-test", action="store_true", help="translate fixed titles through the server and check them")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    payload = json.loads(JOBS.read_text(encoding="utf-8"))
    human = _read_reviews(REVIEWS)
    auto = _read_reviews(AUTO_REVIEWS)
    translations: dict = {}
    if TRANSLATIONS.is_file():
        translations = json.loads(TRANSLATIONS.read_text(encoding="utf-8")).get("translations") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = run(payload, human, auto, translations, today=date.today(), now=now, max_translations=args.max_translations)
    _write(AUTO_REVIEWS, auto, "Automatic reviews (owner decision 2026-10-02); written by auto_review.py only where no human review matches.")
    TRANSLATIONS.write_text(
        json.dumps({"schemaVersion": 1, "note": "Offline machine translations of official titles, keyed by engine and title.", "translations": dict(sorted(translations.items()))}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({key: (len(value) if isinstance(value, (list, dict)) else value) for key, value in report.items()}))
    for ident, reasons in sorted(report["withheld"].items()):
        print(f"withheld {ident}: {', '.join(reasons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

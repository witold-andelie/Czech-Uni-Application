"""Validation contract for immutable public catalogue snapshots.

The validator recalculates structural and business invariants from snapshot
files. A manifest flag or a plausible record count is never accepted as proof
that a snapshot is publishable.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit

from publication_rules import (
    FACT_NORMALIZATION_VERSION,
    UNAPPROVED_PUBLICATION,
    UNAPPROVED_TRANSLATION,
    job_fact_hash,
    offering_fact_hash,
    rendered_offering_windows,
    reviewer_role,
    rule,
    translation_content_hash,
    valid_calendar_date,
    validate_cscse_reference,
    validate_salary,
    validate_window,
    window_signature,
)

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "config" / "publication-policy.json"

VERSION_RE = re.compile(r"^v\d{4}-\d{2}-\d{2}\.\d+$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schemaVersion") != 1:
        raise ValueError("Unsupported publication policy schemaVersion")
    required = policy.get("requiredFiles")
    if not isinstance(required, list) or not required:
        raise ValueError("Publication policy requiredFiles must be a non-empty list")
    for rel in required:
        if not isinstance(rel, str) or not safe_relative_path(rel):
            raise ValueError(f"Unsafe publication-policy path: {rel!r}")
    return policy


@dataclass(frozen=True)
class ValidationResult:
    errors: list[str]
    counts: dict[str, int]

    @property
    def passed(self) -> bool:
        return not self.errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def safe_relative_path(value: str) -> bool:
    if not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


POLICY = load_policy()
REQUIRED_FILES: tuple[str, ...] = tuple(POLICY["requiredFiles"])
LOCALES: tuple[str, ...] = tuple(POLICY["locales"])


def snapshot_file(root: Path, relative: str) -> Path:
    if not safe_relative_path(relative):
        raise ValueError(f"Unsafe snapshot path: {relative!r}")
    resolved_root = root.resolve()
    target = (root / PurePosixPath(relative)).resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ValueError(f"Snapshot path escapes root: {relative!r}")
    return target


def valid_web_url(value: Any, *, https_only: bool = False) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    schemes = {"https"} if https_only else {"http", "https"}
    return (
        parsed.scheme.lower() in schemes
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def valid_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _load_object(root: Path, relative: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        target = snapshot_file(root, relative)
    except ValueError as exc:
        errors.append(str(exc))
        return None
    if not target.is_file():
        errors.append(f"Missing required file: {relative}")
        return None
    if target.stat().st_size == 0:
        errors.append(f"Required file is empty: {relative}")
        return None
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Invalid JSON in {relative}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"Top-level JSON must be an object: {relative}")
        return None
    return value


def _unique_ids(items: Any, label: str, errors: list[str], *, key: str = "id") -> set[str]:
    if not isinstance(items, list):
        errors.append(f"{label} must be an array")
        return set()
    result: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        ident = item.get(key)
        if not isinstance(ident, str) or not ident or not SAFE_ID_RE.fullmatch(ident):
            errors.append(f"{label}[{index}].{key} is missing or unsafe")
            continue
        if ident in result:
            errors.append(f"Duplicate {label} {key}: {ident}")
        result.add(ident)
    return result


def _localized(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} must contain zh-CN, en and cs")
        return
    for locale in LOCALES:
        text = value.get(locale)
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{label}.{locale} must be non-empty")


def _urls(item: dict[str, Any], fields: Iterable[str], label: str, errors: list[str], *, https_only: bool = False) -> None:
    for field in fields:
        value = item.get(field)
        if value is not None and not valid_web_url(value, https_only=https_only):
            errors.append(rule("URL_INVALID", f"{label}.{field} is not an allowed web URL"))


def _require_url(
    item: dict[str, Any],
    field: str,
    label: str,
    errors: list[str],
    code: str,
    *,
    https_only: bool = False,
) -> None:
    value = item.get(field)
    if value is None or value == "":
        errors.append(rule(code, f"{label}.{field} is required"))
    elif not valid_web_url(value, https_only=https_only):
        errors.append(rule("URL_INVALID", f"{label}.{field} is not an allowed web URL"))


def _validate_baseline(data: dict[str, Any], errors: list[str]) -> set[str]:
    institutions = data.get("institutions")
    ids = _unique_ids(institutions, "institutions", errors)
    if not ids:
        errors.append("Institution baseline must not be empty")
        return ids
    for item in institutions if isinstance(institutions, list) else []:
        if not isinstance(item, dict) or item.get("id") not in ids:
            continue
        ident = item["id"]
        if not isinstance(item.get("officialName"), str) or not item["officialName"].strip():
            errors.append(f"institution {ident} has no officialName")
        if item.get("ownership") not in {"public", "private", "state", "unknown"}:
            errors.append(f"institution {ident} has invalid ownership")
        _urls(item, ("officialUrl", "officialUrlSource"), f"institution {ident}", errors)
        source = item.get("source")
        if not isinstance(source, dict) or not valid_web_url(source.get("registryUrl")):
            errors.append(f"institution {ident} has no official registry evidence URL")
        validate_cscse_reference(item, ident, errors)
    return ids


def _validate_portals(data: dict[str, Any], institution_ids: set[str], errors: list[str]) -> int:
    rows = data.get("institutions")
    ids = _unique_ids(rows, "apply portals", errors, key="institutionId")
    missing = institution_ids - ids
    unknown = ids - institution_ids
    if missing:
        errors.append(f"Apply portals missing institutions: {sorted(missing)}")
    if unknown:
        errors.append(f"Apply portals reference unknown institutions: {sorted(unknown)}")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("institutionId") not in ids:
            continue
        ident = row["institutionId"]
        if row.get("kind") not in {"e_application", "admissions_info", "missing"}:
            errors.append(f"apply portal {ident} has invalid kind")
        _urls(row, ("officialUrl", "applyUrl", "applyUrlEn", "admissionsUrl", "admissionsUrlEn"), f"apply portal {ident}", errors)
        if row.get("kind") == "e_application" and not valid_web_url(row.get("applyUrl")):
            errors.append(f"apply portal {ident} is e_application without an allowed applyUrl")
    return len(ids)


def _validate_inventory(data: dict[str, Any], institution_ids: set[str], errors: list[str]) -> tuple[int, int]:
    schools = data.get("schools")
    school_ids = _unique_ids(schools, "inventory schools", errors)
    unknown = school_ids - institution_ids
    if unknown:
        errors.append(f"Inventory references unknown institutions: {sorted(unknown)}")
    row_ids: set[str] = set()
    total = 0
    for school in schools if isinstance(schools, list) else []:
        if not isinstance(school, dict):
            continue
        rows = school.get("rows")
        if not isinstance(rows, list):
            errors.append(f"inventory school {school.get('id')} rows must be an array")
            continue
        for index, row in enumerate(rows):
            total += 1
            label = f"inventory {school.get('id')} row {index}"
            if not isinstance(row, list) or len(row) != 7:
                errors.append(f"{label} must contain exactly 7 fields")
                continue
            ident, title, degree, _faculty, _years, language, _isced = row
            if not isinstance(ident, str) or not SAFE_ID_RE.fullmatch(ident):
                errors.append(f"{label} has an unsafe id")
            elif ident in row_ids:
                errors.append(f"Duplicate inventory row id: {ident}")
            else:
                row_ids.add(ident)
            if not isinstance(title, str) or not title.strip():
                errors.append(f"{label} has an empty title")
            if degree not in {"b", "m", "d", "o", "u"}:
                errors.append(f"{label} has invalid degree code")
            if not isinstance(language, str) or not LANGUAGE_RE.fullmatch(language):
                errors.append(f"{label} has invalid teaching language")
    declared = data.get("counts")
    if not isinstance(declared, dict) or declared.get("schools") != len(school_ids) or declared.get("programmes") != total:
        errors.append("Inventory embedded counts do not match actual records")
    if not school_ids or total == 0:
        errors.append("Inventory must contain at least one school and one record")
    return len(school_ids), total


def _validate_tracer(data: dict[str, Any], name: str, institution_ids: set[str], errors: list[str]) -> tuple[set[str], set[str]]:
    institution_id = data.get("institutionId")
    if institution_id not in institution_ids:
        errors.append(f"{name} references unknown institution {institution_id!r}")
    offerings = data.get("offerings")
    offering_ids = _unique_ids(offerings, f"{name} offerings", errors)
    if not offering_ids:
        errors.append(f"{name} must contain at least one offering")
    for item in offerings if isinstance(offerings, list) else []:
        if not isinstance(item, dict) or item.get("id") not in offering_ids:
            continue
        ident = item["id"]
        if item.get("institutionId") != institution_id:
            errors.append(f"{name} offering {ident} has mismatched institutionId")
        _localized(item.get("title"), f"{name} offering {ident}.title", errors)
        languages = item.get("teachingLanguages")
        if not isinstance(languages, list) or not languages or any(not isinstance(lang, str) or not LANGUAGE_RE.fullmatch(lang) for lang in languages):
            errors.append(f"{name} offering {ident} has invalid teachingLanguages")
        _urls(item, ("applicationUrl", "languageEvidenceUrl"), f"{name} offering {ident}", errors)
        publication_status = item.get("publicationStatus")
        translation_status = item.get("translationStatus")
        if publication_status != "approved" or translation_status != "verified" or publication_status in UNAPPROVED_PUBLICATION or translation_status in UNAPPROVED_TRANSLATION:
            errors.append(rule("TRACER_NOT_APPROVED", f"{name} offering {ident} is not approved for publication"))
    evidence = data.get("evidence")
    evidence_ids = _unique_ids(evidence, f"{name} evidence", errors)
    for item in evidence if isinstance(evidence, list) else []:
        if isinstance(item, dict) and item.get("id") in evidence_ids:
            _require_url(item, "url", f"{name} evidence {item['id']}", errors, "URL_REQUIRED_EVIDENCE")
    windows = data.get("windows")
    window_ids = _unique_ids(windows, f"{name} windows", errors)
    top_level_by_id: dict[str, dict[str, Any]] = {}
    for item in windows if isinstance(windows, list) else []:
        if not isinstance(item, dict) or item.get("id") not in window_ids:
            continue
        ident = item["id"]
        top_level_by_id[ident] = item
        validate_window(
            item,
            f"{name} window",
            errors,
            owner_ids=offering_ids,
            evidence_ids=evidence_ids,
            expected_owner_type="offering",
        )
        _urls(item, ("applicationUrl",), f"{name} window {ident}", errors)
    for item in offerings if isinstance(offerings, list) else []:
        if not isinstance(item, dict) or item.get("id") not in offering_ids:
            continue
        ident = item["id"]
        rendered = rendered_offering_windows(item)
        for nested in rendered:
            validate_window(
                nested,
                f"{name} nested window",
                errors,
                owner_ids={ident},
                evidence_ids=evidence_ids,
                expected_owner_type="offering",
            )
            _urls(nested, ("applicationUrl",), f"{name} nested window {nested.get('id')}", errors)
            nested_id = nested.get("id")
            if isinstance(nested_id, str) and nested_id in top_level_by_id:
                if window_signature(nested) != window_signature(top_level_by_id[nested_id]):
                    errors.append(rule("TRACER_WINDOW_MISMATCH", f"{name} offering {ident} nested window {nested_id} does not match the top-level window"))
        titles = item.get("title") if isinstance(item.get("title"), dict) else {}
        owned = [row for row in (windows if isinstance(windows, list) else []) if isinstance(row, dict) and row.get("ownerId") == ident]
        _validate_offering_review(item, f"{name} offering {ident}", errors, windows=owned + rendered, titles=titles)
    return offering_ids, window_ids


def _validate_translation_review(
    job: dict[str, Any],
    label: str,
    errors: list[str],
    *,
    windows: list[dict[str, Any]],
    evidence_hash: str | None,
) -> None:
    source_hash = job.get("sourceHash")
    if not isinstance(source_hash, str) or not SHA256_RE.fullmatch(source_hash):
        errors.append(f"{label}.sourceHash must be a SHA256 value")
        source_hash = None
    review = job.get("translationReview")
    if not isinstance(review, dict) or (source_hash is not None and review.get("sourceHash") != source_hash):
        errors.append(f"{label}.translationReview must match sourceHash")
        return
    if review.get("normalizationVersion") != FACT_NORMALIZATION_VERSION:
        errors.append(rule("REVIEW_NORMALIZATION_INVALID", f"{label} review normalizationVersion is missing or stale"))
    if not reviewer_role(review.get("reviewer")):
        errors.append(rule("REVIEW_REVIEWER_MISSING", f"{label} review is missing reviewer identity or role"))
    expected_fact = job_fact_hash(job, windows)
    if review.get("factHash") != expected_fact:
        errors.append(rule("REVIEW_FACT_HASH_MISMATCH", f"{label} reviewed facts do not match the published record"))
    if not isinstance(review.get("evidenceHash"), str) or not SHA256_RE.fullmatch(str(review.get("evidenceHash"))):
        errors.append(rule("REVIEW_EVIDENCE_HASH_MISMATCH", f"{label} review evidenceHash is missing"))
    elif source_hash is not None and review.get("evidenceHash") != source_hash:
        errors.append(rule("REVIEW_EVIDENCE_HASH_MISMATCH", f"{label} review evidenceHash does not match sourceHash"))
    elif evidence_hash is not None and review.get("evidenceHash") != evidence_hash:
        errors.append(rule("REVIEW_EVIDENCE_HASH_MISMATCH", f"{label} evidence sourceHash does not match the review"))
    locales = review.get("locales")
    if not isinstance(locales, dict):
        errors.append(f"{label}.translationReview.locales is missing")
        return
    titles = job.get("title") if isinstance(job.get("title"), dict) else {}
    for locale in LOCALES:
        item = locales.get(locale)
        if not isinstance(item, dict):
            errors.append(f"{label} has no {locale} review")
            continue
        if item.get("status") != "reviewed":
            errors.append(f"{label} {locale} translation is not reviewed")
        if source_hash is not None and item.get("translatedFromHash") != source_hash:
            errors.append(f"{label} {locale} review is stale")
        if not valid_iso_datetime(item.get("reviewedAt")):
            errors.append(f"{label} {locale} reviewedAt is invalid")
        expected_translation = translation_content_hash(titles.get(locale))
        if item.get("contentHash") != expected_translation:
            errors.append(rule("REVIEW_TRANSLATION_HASH_MISMATCH", f"{label} {locale} translated content does not match the review"))


def _validate_offering_review(
    offering: dict[str, Any],
    label: str,
    errors: list[str],
    *,
    windows: list[dict[str, Any]],
    titles: dict[str, Any],
) -> None:
    source_hash = offering.get("sourceHash")
    if not isinstance(source_hash, str) or not SHA256_RE.fullmatch(source_hash):
        errors.append(f"{label}.sourceHash must be a SHA256 value")
        return
    review = offering.get("translationReview")
    if not isinstance(review, dict) or review.get("sourceHash") != source_hash:
        errors.append(f"{label}.translationReview must match sourceHash")
        return
    if review.get("normalizationVersion") != FACT_NORMALIZATION_VERSION:
        errors.append(rule("REVIEW_NORMALIZATION_INVALID", f"{label} review normalizationVersion is missing or stale"))
    if not reviewer_role(review.get("reviewer")):
        errors.append(rule("REVIEW_REVIEWER_MISSING", f"{label} review is missing reviewer identity or role"))
    if review.get("factHash") != offering_fact_hash(offering, windows):
        errors.append(rule("REVIEW_FACT_HASH_MISMATCH", f"{label} reviewed facts do not match the published record"))
    if review.get("evidenceHash") != source_hash:
        errors.append(rule("REVIEW_EVIDENCE_HASH_MISMATCH", f"{label} review evidenceHash does not match sourceHash"))
    locales = review.get("locales")
    if not isinstance(locales, dict):
        errors.append(f"{label}.translationReview.locales is missing")
        return
    for locale in LOCALES:
        item = locales.get(locale)
        if not isinstance(item, dict) or item.get("status") != "reviewed":
            errors.append(f"{label} {locale} translation is not reviewed")
            continue
        if item.get("translatedFromHash") != source_hash:
            errors.append(f"{label} {locale} review is stale")
        if not valid_iso_datetime(item.get("reviewedAt")):
            errors.append(f"{label} {locale} reviewedAt is invalid")
        if item.get("contentHash") != translation_content_hash(titles.get(locale)):
            errors.append(rule("REVIEW_TRANSLATION_HASH_MISMATCH", f"{label} {locale} translated content does not match the review"))


def _validate_reviewed_offerings(data: dict[str, Any], institution_ids: set[str], errors: list[str]) -> int:
    offerings = data.get("offerings")
    offering_ids = _unique_ids(offerings, "reviewed offerings", errors)
    evidence = data.get("evidence")
    evidence_ids = _unique_ids(evidence, "reviewed offering evidence", errors)
    windows = data.get("windows")
    window_ids = _unique_ids(windows, "reviewed offering windows", errors)
    for item in evidence if isinstance(evidence, list) else []:
        if isinstance(item, dict) and item.get("id") in evidence_ids:
            _require_url(item, "url", f"reviewed offering evidence {item['id']}", errors, "URL_REQUIRED_EVIDENCE")
    window_rows = [item for item in windows if isinstance(item, dict)] if isinstance(windows, list) else []
    for item in window_rows:
        if item.get("id") not in window_ids:
            continue
        validate_window(
            item,
            "reviewed offering window",
            errors,
            owner_ids=offering_ids,
            evidence_ids=evidence_ids,
            expected_owner_type="offering",
        )
        _urls(item, ("applicationUrl",), f"reviewed offering window {item.get('id')}", errors)
    for offering in offerings if isinstance(offerings, list) else []:
        if not isinstance(offering, dict) or offering.get("id") not in offering_ids:
            continue
        ident = offering["id"]
        label = f"reviewed offering {ident}"
        if offering.get("institutionId") not in institution_ids:
            errors.append(f"{label} references unknown institution")
        if offering.get("publicationStatus") != "approved" or offering.get("translationStatus") != "verified":
            errors.append(rule("TRACER_NOT_APPROVED", f"{label} is not approved for publication"))
        _localized(offering.get("title"), f"{label}.title", errors)
        languages = offering.get("teachingLanguages")
        if not isinstance(languages, list) or not languages or any(not isinstance(lang, str) or not LANGUAGE_RE.fullmatch(lang) for lang in languages):
            errors.append(f"{label} has invalid teachingLanguages")
        if offering.get("applicationTargetKind") not in {"programme_page", "general_portal", "unknown"}:
            errors.append(f"{label} has invalid applicationTargetKind")
        if offering.get("applicationTargetKind") == "general_portal":
            if offering.get("applicationUrl"):
                errors.append(f"{label} general portal must not be stored as a programme-specific applicationUrl")
            _require_url(offering, "generalApplyPortalUrl", label, errors, "URL_REQUIRED_APPLICATION")
        _require_url(offering, "officialProgrammeUrl", label, errors, "URL_REQUIRED_SOURCE")
        _validate_offering_review(
            offering,
            label,
            errors,
            windows=window_rows,
            titles=offering.get("title") if isinstance(offering.get("title"), dict) else {},
        )
    declared = data.get("counts")
    if not isinstance(declared, dict) or declared.get("offerings") != len(offering_ids):
        errors.append("Reviewed-offering embedded counts do not match actual records")
    return len(offering_ids)


def _validate_jobs(data: dict[str, Any], institution_ids: set[str], errors: list[str]) -> int:
    jobs = data.get("jobs")
    job_ids = _unique_ids(jobs, "research jobs", errors)
    evidence = data.get("evidence")
    evidence_ids = _unique_ids(evidence, "research job evidence", errors)
    windows = data.get("windows")
    window_ids = _unique_ids(windows, "research job windows", errors)

    evidence_hash_by_id: dict[str, str] = {}
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict) or item.get("id") not in evidence_ids:
            continue
        ident = item["id"]
        _require_url(item, "url", f"research job evidence {ident}", errors, "URL_REQUIRED_EVIDENCE", https_only=True)
        _localized(item.get("note"), f"research job evidence {ident}.note", errors)
        source_hash = item.get("sourceHash")
        if isinstance(source_hash, str):
            evidence_hash_by_id[ident] = source_hash

    window_rows = [item for item in windows if isinstance(item, dict)] if isinstance(windows, list) else []
    windows_by_owner: dict[str, int] = {}
    for item in window_rows:
        if item.get("id") not in window_ids:
            continue
        ident = item["id"]
        owner_id = item.get("ownerId")
        validate_window(
            item,
            "research job window",
            errors,
            owner_ids=job_ids,
            evidence_ids=evidence_ids,
            expected_owner_type="research_job",
        )
        if isinstance(owner_id, str) and owner_id in job_ids:
            windows_by_owner[owner_id] = windows_by_owner.get(owner_id, 0) + 1
        _urls(item, ("applicationUrl",), f"research job window {ident}", errors, https_only=True)

    for job in jobs if isinstance(jobs, list) else []:
        if not isinstance(job, dict) or job.get("id") not in job_ids:
            continue
        ident = job["id"]
        label = f"research job {ident}"
        if job.get("employerId") not in institution_ids:
            errors.append(f"{label} references unknown employer {job.get('employerId')!r}")
        _localized(job.get("title"), f"{label}.title", errors)
        laboratory = job.get("laboratory")
        if laboratory is not None:
            _localized(laboratory, f"{label}.laboratory", errors)
        if job.get("publicationStatus") != "approved":
            errors.append(f"{label} is not approved for publication")
        if job.get("translationStatus") != "verified":
            errors.append(f"{label} translations are not verified")
        evidence_id = f"ev-{ident}"
        if evidence_id not in evidence_ids:
            errors.append(f"{label} has no matching source evidence")
        _validate_translation_review(
            job,
            label,
            errors,
            windows=window_rows,
            evidence_hash=evidence_hash_by_id.get(evidence_id),
        )
        if job.get("minimumDegree") not in {"bachelor", "master", "doctorate", "other", "unknown"}:
            errors.append(f"{label} has invalid minimumDegree")
        if type(job.get("doctorateRequired")) is not bool:
            errors.append(f"{label}.doctorateRequired must be a strict boolean")
        if job.get("doctoralEnrollment") not in {"required", "optional", "not_required", "unspecified"}:
            errors.append(f"{label} has invalid doctoralEnrollment")
        if job.get("paidStatus") != "confirmed":
            errors.append(f"{label} lacks confirmed compensation evidence")
        # A67/A68: fundingType is optional for snapshots predating the field but
        # must use the controlled vocabulary once present.
        if job.get("fundingType") is not None and job.get("fundingType") not in {"employment", "stipend", "mixed", "unknown"}:
            errors.append(f"{label} has invalid fundingType")
        if job.get("applicationHostVerified") is not True:
            errors.append(f"{label} application host is not verified")
        if job.get("lifecycleStatus") not in {"open", "closed", "expired", "unavailable", "unknown"}:
            errors.append(f"{label} has invalid lifecycleStatus")
        if job.get("visibility") not in {"public", "archived"}:
            errors.append(f"{label} has invalid published visibility")
        if job.get("visibility") == "public" and (job.get("wholeOpportunityClosed") is True or job.get("lifecycleStatus") in {"closed", "expired"}):
            errors.append(f"{label} is closed or expired but still public")
        languages = job.get("workingLanguages")
        if not isinstance(languages, list) or not languages or any(not isinstance(lang, str) or not LANGUAGE_RE.fullmatch(lang) for lang in languages):
            errors.append(f"{label} has invalid workingLanguages")
        _require_url(job, "sourceUrl", label, errors, "URL_REQUIRED_SOURCE", https_only=True)
        if job.get("officialDetailUrl"):
            _urls(job, ("officialDetailUrl",), label, errors, https_only=True)
        if job.get("applicationMethod") == "official_instructions":
            _urls(job, ("applicationUrl",), label, errors, https_only=True)
        else:
            _require_url(job, "applicationUrl", label, errors, "URL_REQUIRED_APPLICATION", https_only=True)
        validate_salary(job.get("salary"), label, errors)
        salary = job.get("salary")
        if isinstance(salary, dict):
            salary_fte = salary.get("basisFte")
            if salary_fte is not None and (
                not isinstance(salary_fte, (int, float))
                or isinstance(salary_fte, bool)
                or not 0 < salary_fte <= 1
            ):
                errors.append(f"{label}.salary.basisFte must be null or a number in (0, 1]")
        employment_fte = job.get("employmentFte")
        if employment_fte is not None and (
            not isinstance(employment_fte, (int, float))
            or isinstance(employment_fte, bool)
            or not 0 < employment_fte <= 1
        ):
            errors.append(f"{label}.employmentFte must be null or a number in (0, 1]")
        employment_start = job.get("employmentStartsAt")
        if employment_start is not None and not valid_calendar_date(employment_start):
            errors.append(rule("EMPLOYMENT_DATE_INVALID", f"{label}.employmentStartsAt must be null or YYYY-MM-DD"))

    declared = data.get("counts")
    skipped = data.get("skipped")
    skipped_count = len(skipped) if isinstance(skipped, list) else 0
    if not isinstance(declared, dict) or declared.get("jobs") != len(job_ids) or declared.get("skipped") != skipped_count:
        errors.append("Research-job embedded counts do not match actual records")
    return len(job_ids)


def _validate_coordinates(data: dict[str, Any], institution_ids: set[str], errors: list[str]) -> int:
    rows = data.get("institutions")
    ids = _unique_ids(rows, "institution coordinates", errors, key="institutionId")
    if ids != institution_ids:
        errors.append("Coordinate institution IDs must exactly match the official baseline")
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict) or item.get("institutionId") not in ids:
            continue
        ident = item["institutionId"]
        lat = item.get("lat")
        lon = item.get("lon")
        if not isinstance(lat, (int, float)) or isinstance(lat, bool) or not -90 <= lat <= 90:
            errors.append(f"coordinates {ident} has invalid latitude")
        if not isinstance(lon, (int, float)) or isinstance(lon, bool) or not -180 <= lon <= 180:
            errors.append(f"coordinates {ident} has invalid longitude")
    return len(ids)


def validate_dataset(snapshot_root: Path) -> ValidationResult:
    errors: list[str] = []
    loaded = {rel: _load_object(snapshot_root, rel, errors) for rel in REQUIRED_FILES}
    if any(value is None for value in loaded.values()):
        return ValidationResult(errors, {})

    baseline = loaded["msmt-hei-baseline.json"] or {}
    institution_ids = _validate_baseline(baseline, errors)
    portal_count = _validate_portals(loaded["admissions/apply-portals.json"] or {}, institution_ids, errors)
    inventory_schools, inventory_offerings = _validate_inventory(
        loaded["browse/nine-hei-inventory.json"] or {}, institution_ids, errors
    )
    _validate_tracer(loaded["admissions/cuni-mff-cs-tracer.json"] or {}, "CUNI tracer", institution_ids, errors)
    _validate_tracer(loaded["admissions/muni-fi-tracer.json"] or {}, "MUNI tracer", institution_ids, errors)
    reviewed_count = _validate_reviewed_offerings(loaded["admissions/reviewed-offerings.json"] or {}, institution_ids, errors)
    job_count = _validate_jobs(loaded["browse/nine-hei-jobs.json"] or {}, institution_ids, errors)
    coordinate_count = _validate_coordinates(loaded["browse/hei-coordinates.json"] or {}, institution_ids, errors)

    outline = loaded["browse/czechia-outline.json"] or {}
    if not isinstance(outline.get("geojson"), dict):
        errors.append("Czechia outline has no GeoJSON object")
    basemap = loaded["browse/czechia-basemap.json"] or {}
    for field in ("regions", "cities"):
        if not isinstance(basemap.get(field), list) or not basemap[field]:
            errors.append(f"Czechia basemap {field} must be a non-empty array")

    counts = {
        "institutions": len(institution_ids),
        "portals": portal_count,
        "inventoryOfferings": inventory_offerings,
        "inventorySchools": inventory_schools,
        "jobs": job_count,
        "coordinates": coordinate_count,
        "reviewedOfferings": reviewed_count,
    }
    return ValidationResult(errors, counts)


def validate_snapshot(snapshot_root: Path, *, expected_version: str | None = None) -> ValidationResult:
    result = validate_dataset(snapshot_root)
    errors = list(result.errors)
    manifest = _load_object(snapshot_root, "manifest.json", errors)
    if manifest is None:
        return ValidationResult(errors, result.counts)

    version = manifest.get("version")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        errors.append("Manifest version is missing or invalid")
    if expected_version is not None and version != expected_version:
        errors.append(f"Manifest version {version!r} does not match active version {expected_version!r}")
    if snapshot_root.name != version:
        errors.append("Manifest version does not match immutable snapshot directory name")
    if manifest.get("schemaVersion") != POLICY["schemaVersion"]:
        errors.append("Manifest schemaVersion does not match publication policy")
    if manifest.get("policyVersion") != POLICY["policyVersion"]:
        errors.append("Manifest policyVersion does not match publication policy")
    if manifest.get("status") != "published":
        errors.append("Manifest status must be published")
    if not valid_iso_datetime(manifest.get("publishedAt")):
        errors.append("Manifest publishedAt is invalid")
    validation = manifest.get("validation")
    if not isinstance(validation, dict) or validation.get("passed") is not True or validation.get("errors") != []:
        errors.append("Manifest validation must be the strict successful result")
    if manifest.get("counts") != result.counts:
        errors.append(f"Manifest counts do not match actual records: {manifest.get('counts')} != {result.counts}")

    checksums = manifest.get("checksums")
    if not isinstance(checksums, dict) or set(checksums) != set(REQUIRED_FILES):
        errors.append("Manifest checksums must contain exactly the required file set")
    else:
        for relative in REQUIRED_FILES:
            expected = checksums.get(relative)
            if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
                errors.append(f"Manifest checksum is invalid for {relative}")
                continue
            try:
                actual = sha256_file(snapshot_file(snapshot_root, relative))
            except (OSError, ValueError) as exc:
                errors.append(f"Cannot hash {relative}: {exc}")
                continue
            if actual != expected:
                errors.append(f"Checksum mismatch for {relative}: {actual} != {expected}")

    return ValidationResult(errors, result.counts)

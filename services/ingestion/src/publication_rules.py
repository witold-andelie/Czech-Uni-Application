"""Stable publication business rules shared by the Python snapshot validator.

The Node implementation in apps/web/scripts/published-contract.mjs is
independent but must emit the same rule identifiers for the shared corpus.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FACT_NORMALIZATION_VERSION = "fact-v1"
LOCALES: tuple[str, ...] = ("zh-CN", "en", "cs")

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

SALARY_CURRENCIES = {"CZK", "EUR", "USD", "GBP", "CHF", "PLN", "SEK", "NOK", "DKK", "CNY", "HUF"}
SALARY_CYCLES = {"month", "year", "hour", "day", "week", "semester", "programme", "unspecified"}
SALARY_TAX = {"gross", "net", "unknown", "unspecified"}
WINDOW_STATUSES = {"open", "closed", "upcoming", "conditional", "unknown"}
DATE_PRECISIONS = {"date", "datetime", "month", "unknown"}
ROUND_TYPES = {"regular", "supplementary", "rolling", "unspecified"}
OWNER_TYPES = {"offering", "research_job"}
CSCSE_OFFICIAL = {"listed", "not_found"}
CSCSE_STATUSES = {"listed", "not_found", "unverified"}
OPERATOR_LIST_STATUSES = {"listed", "absent"}
UNAPPROVED_PUBLICATION = {"review_pending", "draft", "rejected"}
UNAPPROVED_TRANSLATION = {"unreviewed", "draft", "stale", "missing"}


def rule(code: str, message: str) -> str:
    return f"{code}: {message}"


def canonical_json(value: Any) -> str:
    return json.dumps(_canonicalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, int):
        return value
    return value


def sha256_canonical(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def translation_content_hash(text: Any) -> str:
    normalized = unicodedata.normalize("NFC", text if isinstance(text, str) else "")
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def valid_calendar_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    match = DATE_RE.fullmatch(value)
    if not match:
        return False
    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        parsed = datetime(year, month, day)
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%d") == value


def valid_month(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    match = MONTH_RE.fullmatch(value)
    if not match:
        return False
    year, month = int(match.group(1)), int(match.group(2))
    return 1 <= month <= 12 and year >= 1


def valid_datetime_with_offset(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    match = DATETIME_RE.fullmatch(value)
    if not match:
        return False
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour, minute, second = int(match.group(4)), int(match.group(5)), int(match.group(6))
    try:
        datetime(year, month, day, hour, minute, second)
    except ValueError:
        return False
    return True


def valid_iana_timezone(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    name = value.strip()
    if name in {"UTC", "Etc/UTC"}:
        return True
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return False
    return True


def valid_window_timestamp(value: Any, precision: str) -> bool:
    if value is None:
        return True
    if precision == "month":
        return valid_month(value) or valid_calendar_date(value)
    if precision == "datetime":
        return valid_datetime_with_offset(value)
    return valid_calendar_date(value) or valid_datetime_with_offset(value)


def comparable_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if DATE_RE.fullmatch(value):
        return value
    if MONTH_RE.fullmatch(value):
        return f"{value}-01"
    if DATETIME_RE.fullmatch(value):
        return value[:10]
    return None


def window_signature(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "ownerType": item.get("ownerType"),
        "ownerId": item.get("ownerId"),
        "opensAt": item.get("opensAt"),
        "closesAt": item.get("closesAt"),
        "timezone": item.get("timezone"),
        "datePrecision": item.get("datePrecision"),
        "status": item.get("status"),
        "sourceEvidenceId": item.get("sourceEvidenceId"),
        "roundType": item.get("roundType"),
        "roundNumber": item.get("roundNumber"),
        "conditionalOnVacancies": item.get("conditionalOnVacancies"),
        "applicationUrl": item.get("applicationUrl"),
    }


def rendered_offering_windows(item: dict[str, Any]) -> list[dict[str, Any]]:
    nested = item.get("windows")
    if isinstance(nested, list) and nested:
        return [row for row in nested if isinstance(row, dict)]
    single = item.get("window")
    if isinstance(single, dict):
        return [single]
    return []


def canonical_job_facts(job: dict[str, Any], windows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    salary = job.get("salary") if isinstance(job.get("salary"), dict) else {}
    languages = job.get("workingLanguages")
    owned = []
    for item in windows or []:
        if isinstance(item, dict) and item.get("ownerId") == job.get("id"):
            owned.append(
                {
                    "id": item.get("id"),
                    "opensAt": item.get("opensAt"),
                    "closesAt": item.get("closesAt"),
                    "timezone": item.get("timezone"),
                    "datePrecision": item.get("datePrecision"),
                    "status": item.get("status"),
                    "roundType": item.get("roundType"),
                    "conditionalOnVacancies": item.get("conditionalOnVacancies"),
                }
            )
    owned.sort(key=lambda row: str(row.get("id") or ""))
    return {
        "normalizationVersion": FACT_NORMALIZATION_VERSION,
        "id": job.get("id"),
        "minimumDegree": job.get("minimumDegree"),
        "doctorateRequired": job.get("doctorateRequired"),
        "doctoralEnrollment": job.get("doctoralEnrollment"),
        "paidStatus": job.get("paidStatus"),
        "salary": {
            "amount": salary.get("amount"),
            "currency": salary.get("currency"),
            "cycle": salary.get("cycle"),
            "tax": salary.get("tax"),
            "basisFte": salary.get("basisFte"),
        },
        "employmentFte": job.get("employmentFte"),
        "employmentStartsAt": job.get("employmentStartsAt"),
        "workingLanguages": sorted(languages) if isinstance(languages, list) else languages,
        "applicationMethod": job.get("applicationMethod"),
        "applicationUrl": job.get("applicationUrl"),
        "sourceUrl": job.get("sourceUrl"),
        "originalText": job.get("originalText"),
        "isPostdoc": job.get("isPostdoc"),
        "track": job.get("track"),
        "windows": owned,
    }


def job_fact_hash(job: dict[str, Any], windows: list[dict[str, Any]] | None = None) -> str:
    return sha256_canonical(canonical_job_facts(job, windows))


def canonical_offering_facts(offering: dict[str, Any], windows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    tuition = offering.get("tuition") if isinstance(offering.get("tuition"), dict) else {}
    variants = []
    for item in tuition.get("variants") or []:
        if isinstance(item, dict):
            variants.append(
                {
                    "amount": item.get("amount"),
                    "currency": item.get("currency"),
                    "cycle": item.get("cycle"),
                    "applicantScopeOriginal": item.get("applicantScopeOriginal"),
                }
            )
    variants.sort(key=lambda row: (str(row.get("currency") or ""), float(row.get("amount") or 0), str(row.get("applicantScopeOriginal") or "")))
    owned_by_id: dict[str, dict[str, Any]] = {}
    for item in windows or []:
        if not isinstance(item, dict):
            continue
        if item.get("ownerId") not in {None, offering.get("id")}:
            continue
        ident = item.get("id")
        if not isinstance(ident, str):
            continue
        owned_by_id[ident] = {
            "id": ident,
            "opensAt": item.get("opensAt"),
            "closesAt": item.get("closesAt"),
            "timezone": item.get("timezone"),
            "datePrecision": item.get("datePrecision"),
            "status": item.get("status"),
            "roundType": item.get("roundType"),
            "conditionalOnVacancies": item.get("conditionalOnVacancies"),
        }
    owned = list(owned_by_id.values())
    owned.sort(key=lambda row: str(row.get("id") or ""))
    languages = offering.get("teachingLanguages")
    return {
        "normalizationVersion": FACT_NORMALIZATION_VERSION,
        "id": offering.get("id"),
        "degree": offering.get("degree"),
        "teachingLanguages": sorted(languages) if isinstance(languages, list) else languages,
        "languageMode": offering.get("languageMode"),
        "titleOriginal": offering.get("titleOriginal"),
        "sourceLanguage": offering.get("sourceLanguage"),
        "academicYear": offering.get("academicYear"),
        "applicationTargetKind": offering.get("applicationTargetKind"),
        "applicationUrl": offering.get("applicationUrl"),
        "generalApplyPortalUrl": offering.get("generalApplyPortalUrl"),
        "officialProgrammeUrl": offering.get("officialProgrammeUrl") or offering.get("languageEvidenceUrl"),
        "tuition": {
            "published": tuition.get("published"),
            "amount": tuition.get("amount"),
            "currency": tuition.get("currency"),
            "cycle": tuition.get("cycle"),
            "variants": variants,
        },
        "windows": owned,
    }


def offering_fact_hash(offering: dict[str, Any], windows: list[dict[str, Any]] | None = None) -> str:
    return sha256_canonical(canonical_offering_facts(offering, windows))


def reviewer_role(value: Any) -> str | None:
    if isinstance(value, dict):
        role = value.get("role")
        return role.strip() if isinstance(role, str) and role.strip() else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def validate_window(
    item: dict[str, Any],
    label: str,
    errors: list[str],
    *,
    owner_ids: set[str],
    evidence_ids: set[str],
    expected_owner_type: str,
) -> None:
    ident = item.get("id")
    prefix = f"{label} {ident}" if isinstance(ident, str) else label
    if item.get("ownerType") != expected_owner_type or item.get("ownerId") not in owner_ids:
        errors.append(rule("WINDOW_OWNER_INVALID", f"{prefix} has invalid owner"))
    evidence_id = item.get("sourceEvidenceId")
    if evidence_id not in evidence_ids:
        errors.append(rule("WINDOW_EVIDENCE_MISSING", f"{prefix} references missing evidence"))
    if item.get("status") not in WINDOW_STATUSES:
        errors.append(rule("WINDOW_STATUS_INVALID", f"{prefix} has invalid status"))
    precision = item.get("datePrecision")
    if precision not in DATE_PRECISIONS:
        errors.append(rule("WINDOW_PRECISION_INVALID", f"{prefix} has invalid datePrecision"))
        precision = "unknown"
    if item.get("roundType") not in ROUND_TYPES:
        errors.append(rule("WINDOW_ROUND_INVALID", f"{prefix} has invalid roundType"))
    if not valid_iana_timezone(item.get("timezone")):
        errors.append(rule("WINDOW_TIMEZONE_INVALID", f"{prefix} has no timezone" if not item.get("timezone") else f"{prefix} timezone is not a valid IANA zone"))
    opens = item.get("opensAt")
    closes = item.get("closesAt")
    if not valid_window_timestamp(opens, str(precision)):
        errors.append(rule("WINDOW_DATE_INVALID", f"{prefix}.opensAt is not a valid calendar value"))
    if not valid_window_timestamp(closes, str(precision)):
        errors.append(rule("WINDOW_DATE_INVALID", f"{prefix}.closesAt is not a valid calendar value"))
    if precision == "datetime":
        for field, value in (("opensAt", opens), ("closesAt", closes)):
            if value is not None and not valid_datetime_with_offset(value):
                errors.append(rule("WINDOW_DATETIME_OFFSET_REQUIRED", f"{prefix}.{field} must include an explicit UTC offset"))
    start = comparable_date(opens)
    end = comparable_date(closes)
    if start and end and start > end:
        errors.append(rule("WINDOW_DATE_ORDER", f"{prefix} opens after it closes"))


def validate_salary(salary: Any, label: str, errors: list[str]) -> None:
    if not isinstance(salary, dict):
        errors.append(rule("SALARY_OBJECT_INVALID", f"{label}.salary must be an object"))
        return
    amount = salary.get("amount")
    if amount is None:
        return
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(float(amount)) or float(amount) < 0:
        errors.append(rule("SALARY_AMOUNT_INVALID", f"{label}.salary.amount must be a finite nonnegative number or null"))
    currency = salary.get("currency")
    if currency not in SALARY_CURRENCIES:
        errors.append(rule("SALARY_CURRENCY_INVALID", f"{label}.salary.currency is not a controlled currency code"))
    cycle = salary.get("cycle")
    if cycle not in SALARY_CYCLES:
        errors.append(rule("SALARY_CYCLE_INVALID", f"{label}.salary.cycle is not a controlled period code"))
    tax = salary.get("tax")
    if tax not in SALARY_TAX:
        errors.append(rule("SALARY_TAX_INVALID", f"{label}.salary.tax is not a controlled tax code"))


def validate_cscse_reference(item: dict[str, Any], ident: str, errors: list[str]) -> None:
    status = item.get("cscseLookupStatus")
    rec = item.get("cscseReference")
    if not isinstance(rec, dict):
        errors.append(rule("CSCSE_REFERENCE_INVALID", f"institution {ident} has invalid CSCSE reference status"))
        return
    lookup = rec.get("lookupStatus")
    if lookup not in CSCSE_STATUSES or status not in CSCSE_STATUSES:
        errors.append(rule("CSCSE_REFERENCE_INVALID", f"institution {ident} has invalid CSCSE reference status"))
        return
    if lookup != status:
        errors.append(rule("CSCSE_STATUS_MISMATCH", f"institution {ident} CSCSE lookupStatus does not match cscseLookupStatus"))
    kind = rec.get("evidenceKind")
    if kind == "operator_supplied_list":
        if lookup in CSCSE_OFFICIAL or status in CSCSE_OFFICIAL:
            errors.append(rule("CSCSE_OPERATOR_AS_OFFICIAL", f"institution {ident} operator list cannot be published as an official CSCSE lookup"))
        if rec.get("operatorListStatus") not in OPERATOR_LIST_STATUSES:
            errors.append(rule("CSCSE_OPERATOR_STATUS_INVALID", f"institution {ident} has invalid operatorListStatus"))
        return
    if lookup in CSCSE_OFFICIAL:
        if kind != "official_lookup" or not rec.get("evidenceId") or not rec.get("checkedAt"):
            errors.append(rule("CSCSE_OFFICIAL_WITHOUT_EVIDENCE", f"institution {ident} official CSCSE status has no retrievable lookup evidence"))

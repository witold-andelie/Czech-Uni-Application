"""Offering derivation from programme evidence payloads.

An offering is a programme delivery in a specific academic year, with a
teaching-language track. It MAY only be derived when the evidence asserts an
academic year — season labels are never invented. Sources without an asserted
year (studyin, czu-en, czu-cs catalogues) yield no offerings and a declared
reason, so nothing is written for them.

Windows with only an end date (date_precision=end_only) keep an empty opens_at:
a start is never guessed. Windows flagged conditionalOnVacancies become window
status 'conditional' instead of an invented round.

Application-status values map to offering lifecycles with a conservative
fallback of 'unknown'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

DECLINED_NO_YEAR = {"no academic year asserted in evidence; offerings require a declared season"}

_ROUND_TYPE: dict[str, str] = {
    "1. etapa": "regular",
    "2. etapa": "supplementary",
    "řádný termín": "regular",
    "náhradní termín": "supplementary",
    "regular deadline": "regular",
    "alternative deadline": "supplementary",
    "admission procedure 2026": "regular",
    "admission procedure stage 1": "regular",
    "admission procedure stage 2": "supplementary",
    "admission procedure stage 3 (may not open)": "supplementary",
    "stage 1": "regular",
    "stage 2": "supplementary",
}


def _round_type(label: str | None) -> str:
    if not label:
        return "unspecified"
    key = label.strip().lower()
    return _ROUND_TYPE.get(key, "unspecified")


def _lifecycle(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value in {"open", "closed", "upcoming"}:
        return value
    return "unknown"


def _window_status(status: str | None, conditional: bool) -> str:
    if conditional:
        return "conditional"
    value = (status or "").strip().lower()
    if value in {"open", "closed", "upcoming", "conditional"}:
        return value
    return "unknown"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _utc_iso(midnight_local: date | None, timezone_name: str) -> str | None:
    if midnight_local is None:
        return None
    try:
        local = datetime.combine(midnight_local, time(0), tzinfo=ZoneInfo(timezone_name))
        return local.astimezone(ZoneInfo("UTC")).isoformat()
    except (ValueError, KeyError, OSError):
        return None


@dataclass
class AdmissionWindowRecord:
    round_number: int
    round_label_original: str
    round_type: str
    opens_at: str | None
    closes_at: str | None
    timezone: str
    date_precision: str
    status: str
    application_url: str | None
    source_url: str | None
    source_id: str | None


@dataclass
class OfferingRecord:
    programme_external_id: str
    academic_year: str
    teaching_languages: list[str]
    campus_mode: str
    lifecycle: str
    official_detail_url: str | None
    application_url: str | None
    facts: dict = field(default_factory=dict)
    windows: list[AdmissionWindowRecord] = field(default_factory=list)


def derive_offerings(source_id: str, payload: dict) -> tuple[list[OfferingRecord], list[str]]:
    """Return (offerings, declined_reasons). Declined sources write nothing."""
    programmes = payload.get("programmes") or []
    year = programmes[0].get("academicYear") if programmes else None
    if not year:
        return [], [DECLINED_NO_YEAR]

    offerings: list[OfferingRecord] = []
    for rec in programmes:
        remote_id = rec.get("id")
        if not remote_id:
            continue
        langs = rec.get("studyLanguage")
        teaching_languages = [str(langs)] if isinstance(langs, str) and langs else []
        windows: list[AdmissionWindowRecord] = []
        for idx, win in enumerate(rec.get("applicationWindows") or [], start=1):
            opens = _parse_date(win.get("start"))
            closes = _parse_date(win.get("end"))
            tz = win.get("sourceTimezone") or "Europe/Prague"
            windows.append(
                AdmissionWindowRecord(
                    round_number=idx,
                    round_label_original=win.get("roundOriginal") or "",
                    round_type=_round_type(win.get("roundOriginal")),
                    opens_at=_utc_iso(opens, tz) if opens is not None else None,
                    closes_at=_utc_iso(closes, tz),
                    timezone=tz,
                    date_precision="date",
                    status=_window_status(win.get("statusAtFetch"), bool(win.get("conditionalOnVacancies"))),
                    application_url=rec.get("applyUrl") or rec.get("generalApplyPortalUrl"),
                    source_url=win.get("sourceUrl"),
                    source_id=win.get("sourceId"),
                )
            )
        evidence_url = rec.get("officialProgrammeEvidenceUrls") or []
        official_detail_url = evidence_url[0] if evidence_url else None
        admission_evidence = windows[0].source_url if windows else None
        facts = {
            "academicYear": rec.get("academicYear"),
            "degree": rec.get("degree"),
            "durationYears": rec.get("durationYears"),
            "faculty": rec.get("faculty"),
            "facultySlug": rec.get("facultySlug"),
            "studyLanguage": rec.get("studyLanguage"),
            "applicationStatus": rec.get("applicationStatus"),
            "campusModeNotStated": True,
            "windowCount": len(windows),
            "applicationWindows": [
                {
                    "roundOriginal": w.round_label_original,
                    "roundType": w.round_type,
                    "start": w.opens_at,
                    "end": w.closes_at,
                    "statusAtFetch": w.status,
                    "conditionalOnVacancies": win.get("conditionalOnVacancies"),
                }
                for win, w in zip((rec.get("applicationWindows") or []), windows, strict=False)
            ],
        }
        offerings.append(
            OfferingRecord(
                programme_external_id=f"{source_id}:{remote_id}",
                academic_year=str(rec.get("academicYear")),
                teaching_languages=teaching_languages,
                campus_mode="unspecified",
                lifecycle=_lifecycle(rec.get("applicationStatus")),
                official_detail_url=admission_evidence or official_detail_url,
                application_url=rec.get("applyUrl") or rec.get("generalApplyPortalUrl"),
                facts=facts,
                windows=windows,
            )
        )
    return offerings, []


def offering_external_id(programme_external_id: str, academic_year: str) -> str:
    return f"{programme_external_id}#offering/{academic_year}"
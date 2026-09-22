"""Offline evidence rows and declared-scope gates for registered programme sources.

Each registered programme source is backed by a harvested evidence file under
``data/sources/admissions/``. This module maps source id to file, re-asserts the
declared-scope agreement the pipeline requires (the crawls already recorded their
scope completeness in the files; declining scope here blocks the run), and turns
records into listing rows in the shape ``ProgrammeListingAdapter`` expects.

All parsing is deterministic and never fabricates a value the evidence does not
carry: for example, an academic-year label absent from a source stays ``None``
(labelled ``season_asserted`` false) instead of being inferred from window dates.
The CZU English and Czech bachelor/master catalogues disagree on a handful of
titles; those disagreements are preserved as separate identities per catalogue,
not merged.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
ADMISSIONS_DIR = ROOT / "data" / "sources" / "admissions"

EVIDENCE_FILES = {
    "studyin": "studyin-programmes.json",
    "czu-study-english-programmes": "czu-english-programmes.json",
    "czu-studuj-bachelor-master-programmes": "czu-czech-programmes.json",
    "czu-doctoral-faculty-admissions": "czu-doctoral-programmes.json",
}

CATALOGUE_LABELS = {
    "studyin": "studyin",
    "czu-study-english-programmes": "czu-english-bachelor-master",
    "czu-studuj-bachelor-master-programmes": "czu-czech-bachelor-master",
    "czu-doctoral-faculty-admissions": "czu-doctoral-faculty-admissions",
}


def evidence_file(source_id: str) -> Path | None:
    name = EVIDENCE_FILES.get(source_id)
    return ADMISSIONS_DIR / name if name else None


def load_payload(source_id: str, base_dir: Path | None = None) -> dict[str, Any]:
    target = evidence_file(source_id)
    if target is None:
        raise KeyError(f"no evidence file registered for source {source_id!r}")
    path = target if base_dir is None else Path(base_dir) / target.name
    if not path.is_file():
        raise OSError(f"evidence file missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def gate_declared_scope(source_id: str, payload: dict[str, Any]) -> list[str]:
    """Reasons the evidence fails its own recorded declared scope; empty = pass.

    The gates re-assert the coverage agreement the crawls recorded. They only
    compare numbers the files themselves state; they never invent a threshold.
    """
    reasons: list[str] = []
    coverage = payload.get("coverage") or {}
    programmes = payload.get("programmes") or []
    if not isinstance(programmes, list) or not programmes:
        reasons.append("no-programme-records")
        return reasons
    count = len(programmes)

    if source_id == "studyin":
        if coverage.get("complete") is not True:
            reasons.append("declared-scope-incomplete")
        if coverage.get("localeUuidSetsMatch") is not True:
            reasons.append("locale-uuid-sets-mismatch")
        mapping = coverage.get("mapping") or {}
        if mapping.get("unmappedRecords") != 0:
            reasons.append(f"unmapped-records:{mapping.get('unmappedRecords')}")
        en_runs = [run for run in (coverage.get("runs") or []) if run.get("locale") == "en"]
        covered = 0
        for run in en_runs:
            covered += int(run.get("records") or 0)
            if int(run.get("records") or 0) != int(run.get("reportedTotal") or 0):
                reasons.append(f"api-records-vs-reported:{run.get('locale')}")
            if int(run.get("pagesSucceeded") or 0) != int(run.get("pagesExpected") or 0):
                reasons.append(f"pages-succeeded-vs-expected:{run.get('locale')}")
        counts = payload.get("counts") or {}
        if int(counts.get("programmes") or 0) != count:
            reasons.append(f"counts-vs-records:{counts.get('programmes')}vs{count}")
        if covered != count:
            reasons.append(f"covered-vs-records:{covered}vs{count}")

    elif source_id == "czu-study-english-programmes":
        if coverage.get("complete") is not True:
            reasons.append("declared-scope-incomplete")
        if coverage.get("availabilityCrosscheck") != "agrees":
            reasons.append(f"availability-crosscheck:{coverage.get('availabilityCrosscheck')}")
        for key in ("apiReportedTotal", "receivedUniqueProgrammeIds", "detailPagesExpected", "detailPagesParsed"):
            if int(coverage.get(key) or 0) != count:
                reasons.append(f"{key}-v-count:{coverage.get(key)}vs{count}")

    elif source_id == "czu-studuj-bachelor-master-programmes":
        if coverage.get("complete") is not True:
            reasons.append("declared-scope-incomplete")
        for key in ("homepageReportedTotal", "sitemapDetailTotal", "receivedUniqueProgrammeIds", "detailPagesExpected", "detailPagesParsed"):
            if int(coverage.get(key) or 0) != count:
                reasons.append(f"{key}-v-count:{coverage.get(key)}vs{count}")

    elif source_id == "czu-doctoral-faculty-admissions":
        if coverage.get("complete") is not True:
            reasons.append("declared-scope-incomplete")
        baseline = int(coverage.get("baselineOfferings") or 0)
        matched = int(coverage.get("matchedOfferings") or 0)
        if baseline != matched or matched != count:
            reasons.append(f"offerings-baseline-vs-count:{baseline}/{matched}vs{count}")
        if int(coverage.get("baselineFaculties") or 0) != int(coverage.get("facultiesWithProgrammeAndWindowEvidence") or 0):
            reasons.append("faculties-baseline-vs-with-window-evidence")
        for fs in coverage.get("facultyCoverage") or []:
            if int(fs.get("baselineOfferings") or 0) != int(fs.get("matchedOfferings") or 0):
                reasons.append(f"faculty-match:{fs.get('facultySlug')}")
            if int(fs.get("matchedOfferings") or 0) != int(fs.get("offeringsWithOfficialWindow") or 0):
                reasons.append(f"faculty-window:{fs.get('facultySlug')}")
    else:
        reasons.append(f"unregistered-programme-source:{source_id}")
    return reasons


def _record_digest(source_id: str, record: dict[str, Any]) -> str:
    return sha256(
        json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _row(
    *,
    source_id: str,
    record: dict[str, Any],
    code: str,
    detail_url: str,
    title: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "code": code,
        "sourceUrl": detail_url,
        "title": title,
        "catalogue": CATALOGUE_LABELS[source_id],
        "evidenceRecordSha256": _record_digest(source_id, record),
        "seasonAsserted": bool(record.get("academicYear")),
        "teachingLanguages": [record["studyLanguage"]] if record.get("studyLanguage") else None,
        **extra,
    }
    return {key: value for key, value in row.items() if value is not None}


def parse_studyin_rows(payload: dict[str, Any]) -> list[dict]:
    rows: list[dict] = []
    for record in payload.get("programmes") or []:
        titles = record.get("titles") or {}
        rows.append(
            _row(
                source_id="studyin",
                record=record,
                code=str(record["id"]),
                detail_url=str(record["officialDirectoryUrl"] or ""),
                title=str(titles.get("en") or titles.get("cs") or record["id"]),
                extra={
                    "sourceStableId": record.get("sourceStableId"),
                    "degree": record.get("degree"),
                    "institutionId": record.get("institutionId"),
                    "institutionNames": record.get("institutionNames"),
                    "facultyNames": record.get("facultyNames"),
                    "titles": titles,
                    "city": record.get("city"),
                    "studyForms": record.get("studyForms"),
                    "fields": record.get("fields"),
                    "studyLanguage": record.get("studyLanguage"),
                    "durationYears": record.get("durationYears"),
                    "credits": record.get("credits"),
                    "tuition": record.get("tuition"),
                    "applicationStatus": record.get("applicationStatus"),
                    "directoryReportsApplicationsOpen": record.get("directoryReportsApplicationsOpen"),
                    "applicationUrl": None,
                },
            )
        )
    return rows


def parse_czu_catalogue_rows(source_id: str, payload: dict[str, Any]) -> list[dict]:
    rows: list[dict] = []
    for record in payload.get("programmes") or []:
        titles = record.get("titles") or {}
        faculty = record.get("faculty") or {}
        rows.append(
            _row(
                source_id=source_id,
                record=record,
                code=str(record["id"]),
                detail_url=str(record["officialProgrammeUrl"] or ""),
                title=str(titles.get("en") or titles.get("cs") or record["id"]),
                extra={
                    "sourceStableId": record.get("sourceStableId"),
                    "degree": record.get("degree"),
                    "institutionId": record.get("institutionId"),
                    "sourceLanguage": record.get("sourceLanguage"),
                    "studyLanguage": record.get("studyLanguage"),
                    "titles": titles,
                    "faculty": faculty if isinstance(faculty, dict) else None,
                    "facultySlug": faculty.get("slug") if isinstance(faculty, dict) else None,
                    "fieldsOriginal": record.get("fieldsOriginal"),
                    "studyModesOriginal": record.get("studyModesOriginal"),
                    "durationYears": record.get("durationYears"),
                    "tuition": record.get("tuition"),
                    "tuitionEu": record.get("tuitionEu"),
                    "applicationWindows": record.get("applicationWindows"),
                    "applicationStatus": record.get("applicationStatus"),
                    "applicationUrl": record.get("applyUrl"),
                    "applicationPortalUrl": record.get("generalApplyPortalUrl"),
                    "admissionRequirementsTextSha256": record.get("admissionRequirementsTextSha256"),
                    "admissionEvidenceUrls": record.get("admissionEvidenceUrls"),
                    "sourceHtmlSha256": record.get("sourceHtmlSha256"),
                    "sourceModifiedAt": record.get("sourceModifiedAt"),
                    "publicationStatus": record.get("publicationStatus"),
                    "academicYear": record.get("academicYear"),
                },
            )
        )
    return rows


def parse_czu_doctoral_rows(payload: dict[str, Any]) -> list[dict]:
    rows: list[dict] = []
    for record in payload.get("programmes") or []:
        evidence_urls = record.get("officialProgrammeEvidenceUrls") or []
        rows.append(
            _row(
                source_id="czu-doctoral-faculty-admissions",
                record=record,
                code=str(record["id"]),
                detail_url=str(evidence_urls[0]) if evidence_urls else "",
                title=str(record.get("titleOriginal") or record["id"]),
                extra={
                    "degree": record.get("degree"),
                    "institutionId": record.get("institutionId"),
                    "academicYear": record.get("academicYear"),
                    "faculty": record.get("faculty"),
                    "facultySlug": record.get("facultySlug"),
                    "studyLanguage": record.get("studyLanguage"),
                    "sourceLanguage": record.get("sourceLanguage"),
                    "durationYears": record.get("durationYears"),
                    "iscedBroadOrNarrowCode": record.get("iscedBroadOrNarrowCode"),
                    "titleOriginal": record.get("titleOriginal"),
                    "sourceTitleVariant": record.get("sourceTitleVariant"),
                    "officialProgrammeEvidenceUrls": evidence_urls,
                    "admissionEvidenceUrls": record.get("admissionEvidenceUrls"),
                    "matchedSourceIds": record.get("matchedSourceIds"),
                    "applicationWindows": record.get("applicationWindows"),
                    "applicationStatus": record.get("applicationStatus"),
                    "applicationUrl": record.get("applyUrl"),
                },
            )
        )
    return rows


def parse_programme_rows(source_id: str, payload: dict[str, Any]) -> list[dict]:
    """Listing rows for one evidence file. ``code`` is the record id from the
    evidence itself, so re-running the same evidence yields the same identities."""
    if gate_declared_scope(source_id, payload):
        return []
    if source_id == "studyin":
        return parse_studyin_rows(payload)
    if source_id in {"czu-study-english-programmes", "czu-studuj-bachelor-master-programmes"}:
        return parse_czu_catalogue_rows(source_id, payload)
    if source_id == "czu-doctoral-faculty-admissions":
        return parse_czu_doctoral_rows(payload)
    return []


def evidence_context(
    source_id: str,
    *,
    payload: dict[str, Any] | None = None,
    base_dir: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Engine context that feeds ``ProgrammeListingAdapter`` from the evidence file.

    The first requested url returns the full evidence payload (this is the
    listing fetch); every detail url returns a short provenance marker so the
    audit trail stays small. No network I/O ever happens here. On gate failure
    every fetch returns (0, "") so the run cannot complete or write identities.
    """
    payload = payload if payload is not None else load_payload(source_id, base_dir=base_dir)
    reasons = gate_declared_scope(source_id, payload)

    state: dict[str, Any] = {}
    file_digest = file_sha256(payload)

    def fetch_page(url: str) -> tuple[int, str]:
        if reasons:
            return 0, ""
        if not state.get("served_full"):
            state["served_full"] = True
            state["full_text"] = json.dumps(payload, ensure_ascii=False)
            return 200, state["full_text"]
        return 200, f"evidence:{source_id}:{file_digest[:16]}"

    def parse_listing(html: str, listing_url: str) -> list[dict]:
        return parse_programme_rows(source_id, payload)

    return (
        {
            "fetch_page": fetch_page,
            "parse_programme_listing": parse_listing,
            "evidence_source_id": source_id,
            "evidence_file_sha256": file_digest,
        },
        reasons,
    )
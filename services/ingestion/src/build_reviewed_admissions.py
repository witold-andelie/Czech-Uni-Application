"""Build the first reviewed CZU admissions slice and bind tracer reviews.

Candidates stay in data/sources/admissions/*.json. This writes only approved
normalized records plus review hashes. It does not invent tuition, windows,
or programme-specific apply URLs.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from publication_rules import (  # noqa: E402
    FACT_NORMALIZATION_VERSION,
    LOCALES,
    offering_fact_hash,
    sha256_canonical,
    translation_content_hash,
)

SOURCES = ROOT / "data" / "sources"
OUT = SOURCES / "admissions" / "reviewed-offerings.json"
REVIEWS = SOURCES / "reviews" / "offering-translations.json"
EN_PATH = SOURCES / "admissions" / "czu-english-programmes.json"
CS_PATH = SOURCES / "admissions" / "czu-czech-programmes.json"
DOC_PATH = SOURCES / "admissions" / "czu-doctoral-programmes.json"
CUNI_PATH = SOURCES / "admissions" / "cuni-mff-cs-tracer.json"
MUNI_PATH = SOURCES / "admissions" / "muni-fi-tracer.json"

REVIEWED_AT = "2026-09-12T16:30:00Z"
REVIEWER = {"role": "operator_source_review"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def loc(zh: str, en: str, cs: str) -> dict[str, str]:
    return {"zh-CN": zh, "en": en, "cs": cs}


def by_id(rows: list[dict], ident: str) -> dict:
    return next(item for item in rows if item["id"] == ident)


def evidence(ident: str, url: str, note: dict[str, str], source_hash: str | None = None) -> dict:
    row = {"id": ident, "url": url, "note": note}
    if source_hash:
        row["sourceHash"] = f"sha256:{source_hash}" if not str(source_hash).startswith("sha256:") else source_hash
    return row


def window_row(*, ident: str, owner: str, academic_year: str | None, round_label: str, round_number: int | None, opens: str | None, closes: str | None, status: str, evidence_id: str, application_url: str | None, conditional: bool = False, round_type: str = "regular") -> dict:
    return {
        "id": ident,
        "ownerType": "offering",
        "ownerId": owner,
        "academicYear": academic_year,
        "roundNumber": round_number,
        "roundLabelOriginal": round_label,
        "roundType": round_type,
        "applicantScope": None,
        "opensAt": opens,
        "closesAt": closes,
        "timezone": "Europe/Prague",
        "datePrecision": "date",
        "status": status,
        "conditionalOnVacancies": conditional,
        "applicationUrl": application_url,
        "sourceEvidenceId": evidence_id,
    }


def bind_review(offering: dict, windows: list[dict], titles: dict[str, str], source_hash: str) -> dict:
    locales = {}
    for locale in LOCALES:
        locales[locale] = {
            "status": "reviewed",
            "translatedFromHash": source_hash,
            "reviewedAt": REVIEWED_AT,
            "contentHash": translation_content_hash(titles[locale]),
        }
    offering["title"] = dict(titles)
    offering["sourceHash"] = source_hash
    offering["publicationStatus"] = "approved"
    offering["translationStatus"] = "verified"
    offering["factsReviewedAt"] = REVIEWED_AT
    offering["translationReview"] = {
        "sourceHash": source_hash,
        "factHash": offering_fact_hash(offering, windows),
        "evidenceHash": source_hash,
        "normalizationVersion": FACT_NORMALIZATION_VERSION,
        "reviewer": REVIEWER,
        "locales": locales,
    }
    return {
        "sourceHash": source_hash,
        "factHash": offering["translationReview"]["factHash"],
        "evidenceHash": source_hash,
        "normalizationVersion": FACT_NORMALIZATION_VERSION,
        "reviewer": REVIEWER,
        "title": dict(titles),
        "locales": locales,
        "candidateIds": offering.get("candidateIds") or [],
    }


def build_czu_slice() -> tuple[dict, dict[str, dict]]:
    english = load(EN_PATH)
    czech = load(CS_PATH)
    doctoral = load(DOC_PATH)
    en_b = by_id(english["programmes"], "czu-study-507")
    en_m = by_id(english["programmes"], "czu-study-511")
    cs_gis = by_id(czech["programmes"], "czu-studuj-960")
    doc = by_id(doctoral["programmes"], "inv-330bf56297af")
    fetched_en = english["generatedAt"]
    fetched_cs = czech["generatedAt"]
    fetched_doc = doctoral["generatedAt"]

    pef = loc("经济管理学院", "Faculty of Economics and Management", "Provozně ekonomická fakulta")
    fzp = loc("环境学院", "Faculty of Environmental Sciences", "Fakulta životního prostředí")
    en_note = loc(
        "授课语言为英语。入学语言证明和材料以经济管理学院招生页为准，这里不编造成绩线。",
        "Taught in English. Language certificates and materials follow the Faculty of Economics and Management admissions page; scores are not invented here.",
        "Výuka probíhá v angličtině. Jazykové doklady a materiály se řídí stránkou PEF; bodové limity se zde nedomýšlejí.",
    )
    cs_note = loc(
        "授课语言为捷克语。具体入学材料以项目页为准，这里不编造考试科目。",
        "Taught in Czech. Application materials follow the programme page; exam subjects are not invented here.",
        "Výuka probíhá v češtině. Materiály se řídí stránkou programu; předměty zkoušek se zde nedomýšlejí.",
    )
    doc_note = loc(
        "捷克语博士。2026/27 两轮均已截止；下一学年窗口未在本证据中公布。",
        "Czech-taught doctorate. Both 2026/27 rounds are closed; the next academic year is not published in this evidence.",
        "Doktorské studium v češtině. Obě kola 2026/27 jsou uzavřená; další akademický rok tento důkaz nezveřejňuje.",
    )
    general_help = loc(
        "UIS 是学校通用申请系统，不是该项目已核验的专属申请页。",
        "UIS is the university’s general application system, not a verified programme-specific apply page.",
        "UIS je obecný podací systém univerzity, nikoli ověřená stránka konkrétního programu.",
    )

    offerings: list[dict] = []
    windows: list[dict] = []
    evidence_rows: list[dict] = []
    reviews: dict[str, dict] = {}

    def add_english(inv_id: str, candidate: dict, degree: str, duration_years: float, titles: dict[str, str], programme_path: str) -> None:
        ev_en = f"ev-{inv_id}-en"
        ev_cs = f"ev-{inv_id}-cs"
        ev_pef = f"ev-{inv_id}-faculty"
        win_id = f"win-{inv_id}-2026-09"
        cs_hit = by_id(czech["programmes"], "czu-studuj-1004" if degree == "bachelor" else "czu-studuj-1009")
        programme_url = candidate["officialProgrammeUrl"]
        pef_url = candidate["admissionEvidenceUrls"][0]
        general = candidate["generalApplyPortalUrl"]
        win = candidate["applicationWindows"][0]
        offering = {
            "id": inv_id,
            "programmeId": f"prog-{inv_id}",
            "institutionId": "msmt-vs_41000",
            "candidateIds": [candidate["id"], cs_hit["id"]],
            "academicYear": "unknown",
            "teachingLanguages": ["en"],
            "languageMode": "single",
            "languageEvidenceUrl": programme_url,
            "titleOriginal": candidate["titles"]["en"],
            "sourceLanguage": "en",
            "degree": degree,
            "durationSemesters": int(duration_years * 2),
            "field": pef,
            "iscedF": "0613",
            "officialProgrammeUrl": programme_url,
            "applicationUrl": None,
            "applicationTargetKind": "general_portal",
            "generalApplyPortalUrl": general,
            "applicationTargetNote": general_help,
            "tuition": {
                "amount": None,
                "currency": "EUR",
                "cycle": "year",
                "published": True,
                "evidenceUrl": programme_url,
                "unpublishedReason": None,
                "noteOriginal": candidate["tuition"]["displayOriginal"],
                "variants": [
                    {
                        "amount": candidate["tuition"]["amount"],
                        "currency": "EUR",
                        "cycle": "year",
                        "applicantScopeOriginal": candidate["tuition"]["displayOriginal"],
                        "sourceEvidenceId": ev_en,
                    },
                    {
                        "amount": candidate["tuitionEu"]["amount"],
                        "currency": "EUR",
                        "cycle": "year",
                        "applicantScopeOriginal": candidate["tuitionEu"]["displayOriginal"],
                        "sourceEvidenceId": ev_en,
                    },
                ],
                "doNotCollapseDualRates": True,
            },
            "applicationFee": {
                "amount": english["applicationFee"]["amount"],
                "currency": "CZK",
                "isNotTuition": True,
                "evidenceUrl": english["sourceUrls"]["admissions"],
            },
            "additionalLanguageRequirements": [
                {
                    "language": "en",
                    "context": "admission",
                    "requirement": "required",
                    "evidenceUrl": pef_url,
                    "note": en_note,
                }
            ],
            "fetchedAt": fetched_en,
            "dataClass": "official_admissions_extract",
            "lifecycleOverride": None,
        }
        win_row = window_row(
            ident=win_id,
            owner=inv_id,
            academic_year=None,
            round_label=win["roundOriginal"],
            round_number=None,
            opens=win["start"],
            closes=win["end"],
            status="unknown",
            evidence_id=ev_en,
            application_url=None,
        )
        windows.append(win_row)
        evidence_rows.extend(
            [
                evidence(ev_en, programme_url, loc("CZU 英语项目页（申请起止与学费）。", "CZU English programme page (dates and tuition).", "Anglická stránka programu ČZU (termíny a školné)."), candidate["sourceHtmlSha256"]),
                evidence(ev_cs, cs_hit["officialProgrammeUrl"], loc("CZU 捷克入口对应英语项目页，申请日期一致；该页未公布学费。", "Matching Czech-portal English record; dates agree, tuition is unpublished there.", "Shodný záznam na českém portálu; termíny souhlasí, školné tam není zveřejněno."), cs_hit["sourceHtmlSha256"]),
                evidence(ev_pef, pef_url, loc("经济管理学院招生说明。", "Faculty admissions page.", "Přijímací informace PEF.")),
            ]
        )
        raw = candidate.get("sourceHtmlSha256")
        source_hash = raw if str(raw).startswith("sha256:") else f"sha256:{raw}"
        reviews[inv_id] = bind_review(offering, [win_row], titles, source_hash)
        offerings.append(offering)

    add_english(
        "inv-898e810ed190",
        en_b,
        "bachelor",
        3.0,
        loc("信息学", "Informatics", "Informatika"),
        "informatics",
    )
    add_english(
        "inv-ac1fecbdfc9c",
        en_m,
        "master",
        2.0,
        loc("信息学", "Informatics", "Informatika"),
        "informatics-2",
    )

    gis_id = "inv-c50825f0199c"
    gis_ev = f"ev-{gis_id}"
    gis_win = cs_gis["applicationWindows"][0]
    gis_url = cs_gis["officialProgrammeUrl"]
    gis_offering = {
        "id": gis_id,
        "programmeId": f"prog-{gis_id}",
        "institutionId": "msmt-vs_41000",
        "candidateIds": [cs_gis["id"]],
        "academicYear": "unknown",
        "teachingLanguages": ["cs"],
        "languageMode": "single",
        "languageEvidenceUrl": gis_url,
        "titleOriginal": cs_gis["titles"]["cs"],
        "sourceLanguage": "cs",
        "degree": "bachelor",
        "durationSemesters": 6,
        "field": fzp,
        "iscedF": "0532",
        "officialProgrammeUrl": gis_url,
        "applicationUrl": None,
        "applicationTargetKind": "general_portal",
        "generalApplyPortalUrl": cs_gis["generalApplyPortalUrl"],
        "applicationTargetNote": general_help,
        "tuition": {
            "amount": None,
            "currency": None,
            "cycle": None,
            "published": False,
            "evidenceUrl": gis_url,
            "unpublishedReason": "Czech-portal page does not publish a tuition amount. Unpublished is not free.",
            "noteOriginal": None,
            "variants": [],
        },
        "applicationFee": {
            "amount": czech["applicationFee"]["amount"],
            "currency": "CZK",
            "isNotTuition": True,
            "evidenceUrl": czech["sourceUrls"]["admissions"],
        },
        "additionalLanguageRequirements": [
            {
                "language": "cs",
                "context": "admission",
                "requirement": "required",
                "evidenceUrl": gis_url,
                "note": cs_note,
            }
        ],
        "fetchedAt": fetched_cs,
        "dataClass": "official_admissions_extract",
        "lifecycleOverride": None,
    }
    gis_window = window_row(
        ident=f"win-{gis_id}-2025-11",
        owner=gis_id,
        academic_year=None,
        round_label=gis_win["roundOriginal"],
        round_number=None,
        opens=gis_win["start"],
        closes=gis_win["end"],
        status="closed",
        evidence_id=gis_ev,
        application_url=None,
    )
    windows.append(gis_window)
    evidence_rows.append(
        evidence(gis_ev, gis_url, loc("CZU 捷克入口本科项目页。学费未公布，不等于免费。", "Czech-portal bachelor page. Unpublished tuition is not free.", "Stránka bakalářského programu na českém portálu. Nezveřejněné školné není nula."), cs_gis["sourceHtmlSha256"])
    )
    gis_hash = cs_gis["sourceHtmlSha256"]
    gis_source = gis_hash if str(gis_hash).startswith("sha256:") else f"sha256:{gis_hash}"
    reviews[gis_id] = bind_review(
        gis_offering,
        [gis_window],
        loc("地理信息系统与环境遥感", "Geographic Information Systems and Remote Sensing in the Environment", cs_gis["titles"]["cs"]),
        gis_source,
    )
    offerings.append(gis_offering)

    doc_id = doc["id"]
    doc_ev = f"ev-{doc_id}"
    doc_url = doc["admissionEvidenceUrls"][0]
    doc_offering = {
        "id": doc_id,
        "programmeId": f"prog-{doc_id}",
        "institutionId": "msmt-vs_41000",
        "candidateIds": [doc_id],
        "academicYear": "2026/2027",
        "teachingLanguages": ["cs"],
        "languageMode": "single",
        "languageEvidenceUrl": doc_url,
        "titleOriginal": doc["titleOriginal"],
        "sourceLanguage": "cs",
        "degree": "doctorate",
        "durationSemesters": 8,
        "field": fzp,
        "iscedF": "0521",
        "officialProgrammeUrl": doc_url,
        "applicationUrl": None,
        "applicationTargetKind": "general_portal",
        "generalApplyPortalUrl": doc["generalApplyPortalUrl"],
        "applicationTargetNote": general_help,
        "tuition": {
            "amount": None,
            "currency": None,
            "cycle": None,
            "published": False,
            "evidenceUrl": doc_url,
            "unpublishedReason": "Faculty doctoral PDF used for windows does not state a tuition amount.",
            "noteOriginal": None,
            "variants": [],
        },
        "additionalLanguageRequirements": [
            {
                "language": "cs",
                "context": "admission",
                "requirement": "required",
                "evidenceUrl": doc_url,
                "note": doc_note,
            }
        ],
        "fetchedAt": fetched_doc,
        "dataClass": "official_admissions_extract",
        "lifecycleOverride": None,
    }
    doc_windows = []
    for index, win in enumerate(doc["applicationWindows"], start=1):
        row = window_row(
            ident=f"win-{doc_id}-{index}",
            owner=doc_id,
            academic_year="2026/2027",
            round_label=win["roundOriginal"],
            round_number=index,
            opens=win["start"],
            closes=win["end"],
            status="closed",
            evidence_id=doc_ev,
            application_url=None,
        )
        doc_windows.append(row)
        windows.append(row)
    evidence_rows.append(
        evidence(doc_ev, doc_url, loc("环境学院 2026/27 博士招生 PDF。两轮均已截止。", "FZP 2026/27 doctoral admissions PDF. Both rounds are closed.", "PDF přijímaček FZP 2026/27. Obě kola jsou uzavřená."))
    )
    reviews[doc_id] = bind_review(
        doc_offering,
        doc_windows,
        loc("应用与景观生态学", "Applied and Landscape Ecology", doc["titleOriginal"]),
        sha256_canonical({"id": doc_id, "pdf": doc_url, "title": doc["titleOriginal"]}),
    )
    offerings.append(doc_offering)

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_admissions_extract",
        "catalogKind": "reviewed_admissions",
        "institutionId": "msmt-vs_41000",
        "note": "First reviewed CZU admissions slice: English bachelor Informatics, English master Informatics, Czech-taught GIS bachelor, and Czech doctoral Applied and Landscape Ecology. Not complete CZU coverage. UIS links are general portals. Inventory IDs are preserved.",
        "sourceFetchedAt": {
            "czu-english-programmes": fetched_en,
            "czu-czech-programmes": fetched_cs,
            "czu-doctoral-programmes": fetched_doc,
        },
        "counts": {"offerings": len(offerings), "windows": len(windows), "evidence": len(evidence_rows)},
        "offerings": offerings,
        "windows": windows,
        "evidence": evidence_rows,
        "publicationSelection": {"approved": len(offerings), "reviewPendingExcluded": 0, "excludedIds": []},
    }
    return payload, reviews


def patch_tracer(path: Path, reviews: dict[str, dict]) -> None:
    payload = load(path)
    windows = [item for item in payload.get("windows") or [] if isinstance(item, dict)]
    nested_windows: list[dict] = []
    for offering in payload.get("offerings") or []:
        nested_windows.extend(offering.get("windows") or [])
        if isinstance(offering.get("window"), dict):
            nested_windows.append(offering["window"])
    all_windows = windows + nested_windows
    for offering in payload.get("offerings") or []:
        titles = offering["title"]
        offering["titleOriginal"] = offering.get("titleOriginal") or titles.get("en") or titles.get("cs")
        offering["sourceLanguage"] = "en" if offering["teachingLanguages"][0] == "en" else "cs"
        offering["applicationTargetKind"] = "programme_page"
        offering["officialProgrammeUrl"] = offering.get("languageEvidenceUrl")
        offering["fetchedAt"] = payload.get("generatedAt")
        source_hash = sha256_canonical({"id": offering["id"], "sisIdObor": offering.get("sisIdObor"), "titleOriginal": offering.get("titleOriginal")})
        owned = [item for item in all_windows if item.get("ownerId") == offering["id"] or item.get("id") == (offering.get("window") or {}).get("id")]
        reviews[offering["id"]] = bind_review(offering, owned, titles, source_hash)
    dump(path, payload)


def main() -> None:
    payload, reviews = build_czu_slice()
    patch_tracer(CUNI_PATH, reviews)
    patch_tracer(MUNI_PATH, reviews)
    dump(OUT, payload)
    dump(
        REVIEWS,
        {
            "schemaVersion": 1,
            "note": "Reviewed admissions titles and facts for the CZU slice and existing CUNI/MUNI tracers. reviewer.role=operator_source_review is an internal source-and-language review, not external certification.",
            "reviews": reviews,
        },
    )
    print(json.dumps({"offerings": payload["counts"]["offerings"], "reviews": len(reviews)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

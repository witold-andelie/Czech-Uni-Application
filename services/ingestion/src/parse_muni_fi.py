"""Parse Masaryk University FI admissions pages into a tracer snapshot.

Does not invent an English-taught bachelor (FI bachelor programmes are
Czech-only), does not collapse a 800/900 CZK application-fee conflict,
and does not write data/published/.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "work" / "raw" / "2026-09-06"
OUT = ROOT / "data" / "sources" / "admissions" / "muni-fi-tracer.json"
REGISTER = ROOT / "data" / "sources" / "programmes" / "vs_14000.json"

HOW_TO = RAW / "muni-how-to-apply-en.html"
TUITION = RAW / "muni-tuition-en.html"
FEES = RAW / "muni-admission-fees-en.html"
BACHELOR_CS = RAW / "muni-fi-bachelor-cs.html"
GUIDE_CS = RAW / "muni-fi-bachelor-guide-cs.html"
MASTER_EN = RAW / "muni-fi-master-en.html"
INDEX_EN = RAW / "muni-fi-index-en.html"

HOW_TO_URL = "https://www.muni.cz/en/admissions/bachelors-and-masters-studies/how-to-apply"
TUITION_URL = "https://www.muni.cz/en/admissions/bachelors-and-masters-studies/tuition-fees-and-financial-aid"
FEES_URL = "https://www.muni.cz/en/about-us/official-notice-board/admission-procedure-fees"
BACHELOR_URL = "https://www.fi.muni.cz/admission/info-bachelor.html.cs"
GUIDE_URL = "https://www.fi.muni.cz/admission/guide.html.cs"
MASTER_URL = "https://www.fi.muni.cz/admission/international/info-master.html.en"
INDEX_URL = "https://www.fi.muni.cz/admission/index.html.en"
TZ = "Europe/Prague"
EN_APPLY = "https://is.muni.cz/prihlaska/?lang=en"
CS_APPLY = "https://is.muni.cz/prihlaska/info?filtr-typ-studia=BM&filtr-forma-studia=P&filtr-fakulta=1433&vyhledat=Vyhledat"


def evidence(eid: str, url: str, quote: str, supports: list[str], path: str) -> dict:
    return {
        "id": eid,
        "url": url,
        "institution": "Masarykova univerzita",
        "extractedAt": "2026-09-06",
        "quoteOriginal": quote,
        "supports": supports,
        "localPath": path,
        "timezoneAssumed": TZ,
    }


def match_register(programmes: list[dict], title: str, language: str, deg: str) -> dict | None:
    hits = [
        item
        for item in programmes
        if item.get("titleOriginal") == title
        and item.get("teachingLanguage") == language
        and item.get("degree") == deg
        and "Fakulta informatiky" in (item.get("facultyName") or "")
    ]
    return hits[0] if len(hits) == 1 else None


def window_payload(
    wid: str,
    owner_id: str,
    label: str,
    opens: str,
    closes: str,
    apply_url: str,
    evidence_id: str,
    status: str,
) -> dict:
    return {
        "id": wid,
        "ownerType": "offering",
        "ownerId": owner_id,
        "academicYear": "2026/2027",
        "roundNumber": None,
        "roundLabelOriginal": label,
        "roundType": "unspecified",
        "applicantScope": None,
        "opensAt": opens,
        "opensAtNotInferredFrom": None,
        "opensAtFacultyNotePrecision": None,
        "closesAt": closes,
        "timezone": TZ,
        "datePrecision": "date",
        "status": status,
        "conditionalOnVacancies": False,
        "applicationUrl": apply_url,
        "sourceEvidenceId": evidence_id,
        "sisCannotApplyNow": None,
    }


def parse_sources() -> dict:
    how = HOW_TO.read_text(encoding="utf-8", errors="replace")
    tuition = TUITION.read_text(encoding="utf-8", errors="replace")
    fees = FEES.read_text(encoding="utf-8", errors="replace")
    bachelor = BACHELOR_CS.read_text(encoding="utf-8", errors="replace")
    guide = GUIDE_CS.read_text(encoding="utf-8", errors="replace")
    master = MASTER_EN.read_text(encoding="utf-8", errors="replace")
    index = INDEX_EN.read_text(encoding="utf-8", errors="replace")
    if "Taught in Czech only." not in index:
        raise SystemExit("FI index no longer says bachelor programmes are Czech-only")
    if "Visual Informatics" not in master:
        raise SystemExit("FI English master page missing Visual Informatics")
    if "1." not in bachelor or "28." not in bachelor or "2026" not in bachelor:
        raise SystemExit("FI Czech bachelor page missing 2026 application dates")
    if not re.search(r"1\.\s*11\.\s*2025", bachelor) or not re.search(r"28\.\s*2\.\s*2026", bachelor):
        raise SystemExit("FI Czech bachelor application window not 1.11.2025–28.2.2026")
    if "15 December" not in how or "15 April" not in how or "15 June" not in how or "15 October" not in how:
        raise SystemExit("MU how-to-apply missing FI English intake dates")
    if "4,500" not in tuition and "4500" not in tuition:
        raise SystemExit("MU tuition page missing FI 4,500 EUR")
    if "programmes taught in Czech are completely tuition free" not in tuition:
        raise SystemExit("MU tuition page missing Czech-taught tuition-free statement")
    if "800 CZK" not in master:
        raise SystemExit("FI English master page missing 800 CZK application fee")
    if "800" not in guide or "Kč" not in guide:
        raise SystemExit("FI Czech bachelor guide missing 800 Kč application fee")
    if "<strong>FI</strong>" not in fees or "900 CZK" not in fees:
        raise SystemExit("Official notice board missing FI 900 CZK fee row")
    return {
        "how": how,
        "tuition": tuition,
        "fees": fees,
        "bachelor": bachelor,
        "guide": guide,
        "master": master,
        "index": index,
    }


def build() -> dict:
    parse_sources()
    programmes = json.loads(REGISTER.read_text(encoding="utf-8")).get("programmes") or []
    en_reg = match_register(programmes, "Visual Informatics", "en", "master")
    cs_reg = match_register(programmes, "Informatika", "cs", "bachelor")
    if not en_reg or not cs_reg:
        raise SystemExit("register match failed for FI Visual Informatics / Informatika")

    en_windows = [
        window_payload(
            "win-muni-fi-vi-en-sep-2026",
            "muni-fi-vi-en-2026",
            "September intake",
            "2025-12-15",
            "2026-04-15",
            EN_APPLY,
            "ev-muni-fi-en-sep",
            "closed",
        ),
        window_payload(
            "win-muni-fi-vi-en-feb-2027",
            "muni-fi-vi-en-2026",
            "February intake",
            "2026-06-15",
            "2026-10-15",
            EN_APPLY,
            "ev-muni-fi-en-feb",
            "open",
        ),
    ]
    cs_windows = [
        window_payload(
            "win-muni-fi-inf-cs-2026",
            "muni-fi-inf-cs-2026",
            "Termíny pro podávání přihlášek",
            "2025-11-01",
            "2026-02-28",
            CS_APPLY,
            "ev-muni-fi-cs-close",
            "closed",
        )
    ]

    en = {
        "id": "muni-fi-vi-en-2026",
        "institutionId": "msmt-vs_14000",
        "facultyOriginal": "Fakulta informatiky",
        "facultySisOriginal": "Faculty of Informatics",
        "registerMatch": {
            "titleOriginal": en_reg["titleOriginal"],
            "facultyName": en_reg["facultyName"],
            "degree": en_reg["degree"],
            "teachingLanguage": en_reg["teachingLanguage"],
            "iscedF": en_reg["iscedF"],
            "standardYears": en_reg["standardYears"],
        },
        "academicYear": "2026/2027",
        "academicYearEvidence": "FI English master criteria are titled 2026/2027 (autumn 2026 and spring 2027 intakes).",
        "teachingLanguages": ["en"],
        "languageMode": "single",
        "languageEvidenceUrl": MASTER_URL,
        "titleOriginal": "Visual Informatics",
        "title": {"zh-CN": "视觉信息学", "en": "Visual Informatics", "cs": "Visual Informatics"},
        "degree": "master",
        "durationOriginal": "2 years",
        "formOriginal": "full-time",
        "sisIdObor": None,
        "additionalLanguageRequirements": [
            {
                "language": "en",
                "context": "admission",
                "requirement": "required",
                "evidenceUrl": MASTER_URL,
                "note": {
                    "zh-CN": "英语授课硕士要求至少 B2（FI 列出 TOEFL iBT 85、IELTS 6.5 等）。",
                    "en": "English at least B2 is required (FI lists TOEFL iBT 85, IELTS 6.5, and other accepted tests).",
                    "cs": "Je požadována angličtina alespoň na úrovni B2 (FI uvádí TOEFL iBT 85, IELTS 6.5 a další uznávané testy).",
                },
            }
        ],
        "applicationUrl": EN_APPLY,
        "applicationUrlNote": "FI English master page links the MU e-application. February intake is still within 15 June–15 October 2026.",
        "tuition": {
            "amount": 4500,
            "currency": "EUR",
            "cycle": "year",
            "published": True,
            "evidenceUrl": TUITION_URL,
            "unpublishedReason": None,
            "noteOriginal": "Faculty of Informatics 4,500 EUR (faculty-wide English-taught rate on the central tuition page, not a programme-specific figure).",
            "variants": [
                {
                    "amount": 4500,
                    "currency": "EUR",
                    "cycle": "year",
                    "applicantScopeOriginal": "Faculty of Informatics",
                    "sourceEvidenceId": "ev-muni-tuition-fi",
                }
            ],
            "doNotCollapseDualRates": True,
        },
        "applicationFee": {
            "onlineOriginal": "FI English master page: 800 CZK. Official notice board FI follow-up master's (foreign language, 2026/27): 900 CZK. Amount not collapsed.",
            "paperOriginal": None,
            "amount": None,
            "currency": "CZK",
            "isNotTuition": True,
            "evidenceUrl": MASTER_URL,
            "candidates": [
                {"amount": 800, "currency": "CZK", "sourceEvidenceId": "ev-muni-fi-en-fee-800"},
                {"amount": 900, "currency": "CZK", "sourceEvidenceId": "ev-muni-fi-en-fee-900"},
            ],
        },
        "window": en_windows[1],
        "windows": en_windows,
        "dataClass": "official_admissions_extract",
        "catalogKind": "tracer_not_published",
    }
    cs = {
        "id": "muni-fi-inf-cs-2026",
        "institutionId": "msmt-vs_14000",
        "facultyOriginal": "Fakulta informatiky",
        "facultySisOriginal": "Fakulta informatiky",
        "registerMatch": {
            "titleOriginal": cs_reg["titleOriginal"],
            "facultyName": cs_reg["facultyName"],
            "degree": cs_reg["degree"],
            "teachingLanguage": cs_reg["teachingLanguage"],
            "iscedF": cs_reg["iscedF"],
            "standardYears": cs_reg["standardYears"],
        },
        "academicYear": "2026/2027",
        "academicYearEvidence": "FI Czech bachelor page is titled Bakalářské studium 2026/2027 with application dates 1.11.2025–28.2.2026.",
        "teachingLanguages": ["cs"],
        "languageMode": "single",
        "languageEvidenceUrl": BACHELOR_URL,
        "titleOriginal": "Informatika",
        "title": {"zh-CN": "信息学", "en": "Informatika", "cs": "Informatika"},
        "degree": "bachelor",
        "durationOriginal": "3 roky",
        "formOriginal": "prezenční",
        "sisIdObor": None,
        "additionalLanguageRequirements": [],
        "applicationUrl": CS_APPLY,
        "applicationUrlNote": "FI Czech bachelor page links the MU e-application. The 2026/2027 window is closed.",
        "tuition": {
            "amount": 0,
            "currency": "CZK",
            "cycle": "year",
            "published": True,
            "evidenceUrl": TUITION_URL,
            "unpublishedReason": None,
            "noteOriginal": "programmes taught in Czech are completely tuition free",
            "variants": [],
            "doNotCollapseDualRates": True,
        },
        "applicationFee": {
            "onlineOriginal": "FI Czech bachelor guide: 800 Kč. Official notice board FI bachelor 2026/27: 900 CZK. Amount not collapsed.",
            "paperOriginal": None,
            "amount": None,
            "currency": "CZK",
            "isNotTuition": True,
            "evidenceUrl": GUIDE_URL,
            "candidates": [
                {"amount": 800, "currency": "CZK", "sourceEvidenceId": "ev-muni-fi-cs-fee-800"},
                {"amount": 900, "currency": "CZK", "sourceEvidenceId": "ev-muni-fi-cs-fee-900"},
            ],
        },
        "window": cs_windows[0],
        "windows": cs_windows,
        "dataClass": "official_admissions_extract",
        "catalogKind": "tracer_not_published",
    }
    if en["tuition"]["amount"] != 4500:
        raise SystemExit("EN tuition must stay the published FI 4500 EUR rate")
    if cs["tuition"]["amount"] != 0 or not cs["tuition"]["published"]:
        raise SystemExit("Czech-taught tuition must use the published tuition-free statement, not unpublished")
    if en["applicationFee"]["amount"] is not None or cs["applicationFee"]["amount"] is not None:
        raise SystemExit("conflicting application fees must not collapse to one amount")
    snapshot = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_admissions_extract",
        "catalogKind": "tracer_not_published",
        "institutionId": "msmt-vs_14000",
        "institutionOfficialName": "Masarykova univerzita",
        "msmtCode": "VS_14000",
        "facultyOriginal": "Fakulta informatiky",
        "note": "Masaryk University FI tracer: English Visual Informatics master's (two intakes) and Czech Informatika bachelor. FI bachelor programmes are Czech-only. Not a published catalogue. Not written to data/published/.",
        "sources": {
            "howToApply": HOW_TO_URL,
            "tuition": TUITION_URL,
            "admissionFees": FEES_URL,
            "fiBachelorCs": BACHELOR_URL,
            "fiBachelorGuideCs": GUIDE_URL,
            "fiMasterEn": MASTER_URL,
            "fiIndexEn": INDEX_URL,
            "register": "https://regvssp.msmt.cz/registrvssp/csplist.aspx",
        },
        "offerings": [en, cs],
        "windows": en_windows + cs_windows,
        "evidence": [
            evidence(
                "ev-muni-fi-en-sep",
                HOW_TO_URL,
                "Faculty of Informatics September intake: 15 December–15 April",
                ["window.opensAt", "window.closesAt"],
                "work/raw/2026-09-06/muni-how-to-apply-en.html",
            ),
            evidence(
                "ev-muni-fi-en-feb",
                HOW_TO_URL,
                "Faculty of Informatics February intake: 15 June–15 October",
                ["window.opensAt", "window.closesAt"],
                "work/raw/2026-09-06/muni-how-to-apply-en.html",
            ),
            evidence(
                "ev-muni-fi-en-eval-autumn",
                MASTER_URL,
                "dates of evaluation of fully submitted and paid applications are: 15 January, 15 February, 15 March, 15 April 2026",
                ["window.closesAt"],
                "work/raw/2026-09-06/muni-fi-master-en.html",
            ),
            evidence(
                "ev-muni-fi-cs-close",
                BACHELOR_URL,
                "Termíny pro podávání přihlášek: 1. 11. 2025 – 28. 2. 2026",
                ["window.opensAt", "window.closesAt"],
                "work/raw/2026-09-06/muni-fi-bachelor-cs.html",
            ),
            evidence(
                "ev-muni-tuition-fi",
                TUITION_URL,
                "Faculty of Informatics 4,500 EUR",
                ["tuition.amount"],
                "work/raw/2026-09-06/muni-tuition-en.html",
            ),
            evidence(
                "ev-muni-tuition-czech-free",
                TUITION_URL,
                "programmes taught in Czech are completely tuition free",
                ["tuition.amount"],
                "work/raw/2026-09-06/muni-tuition-en.html",
            ),
            evidence(
                "ev-muni-fi-en-fee-800",
                MASTER_URL,
                "The application fee is 800 CZK",
                ["applicationFee"],
                "work/raw/2026-09-06/muni-fi-master-en.html",
            ),
            evidence(
                "ev-muni-fi-en-fee-900",
                FEES_URL,
                "FI follow-up master's foreign-language admission procedure fee 900 CZK (2026/27 table)",
                ["applicationFee"],
                "work/raw/2026-09-06/muni-admission-fees-en.html",
            ),
            evidence(
                "ev-muni-fi-cs-fee-800",
                GUIDE_URL,
                "Přihláška se podává elektronicky a poplatek je 800 Kč.",
                ["applicationFee"],
                "work/raw/2026-09-06/muni-fi-bachelor-guide-cs.html",
            ),
            evidence(
                "ev-muni-fi-cs-fee-900",
                FEES_URL,
                "FI bachelor admission procedure fee 900 CZK (2026/27 table)",
                ["applicationFee"],
                "work/raw/2026-09-06/muni-admission-fees-en.html",
            ),
            evidence(
                "ev-muni-fi-bachelor-czech-only",
                INDEX_URL,
                "Bachelor's Taught in Czech only.",
                ["teachingLanguages"],
                "work/raw/2026-09-06/muni-fi-index-en.html",
            ),
        ],
    }
    return snapshot


def main() -> None:
    snapshot = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} offerings={len(snapshot['offerings'])} windows={len(snapshot['windows'])}")


if __name__ == "__main__":
    main()

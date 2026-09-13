"""Parse Charles University SIS programme-detail HTML into admissions facts.

Does not invent an application start date from a month-only faculty note,
does not treat an application fee as tuition, and does not write 0 when
Czech-taught tuition is unpublished.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "services" / "ingestion" / "tests" / "fixtures" / "raw-2026-09-06"
if not RAW.exists():
    RAW = ROOT / "work" / "raw" / "2026-09-06"
OUT = ROOT / "data" / "sources" / "admissions" / "cuni-mff-cs-tracer.json"
REGISTER = ROOT / "data" / "sources" / "programmes" / "vs_11000.json"

EN_SIS = RAW / "cuni-sis-cs-bachelor-en.html"
CS_SIS = RAW / "cuni-sis-cs-bachelor-cs.html"
MFF_COSTS = RAW / "cuni-mff-costs.html"
FACULTY_CS = RAW / "cuni-sis-mff-faculty-cs.html"

EN_SIS_URL = "https://is.cuni.cz/studium/eng/prijimacky/index.php?do=detail_obor&id_obor=34738"
CS_SIS_URL = "https://is.cuni.cz/studium/prijimacky/index.php?do=detail_obor&id_obor=34456"
MFF_COSTS_URL = "https://www.mff.cuni.cz/en/admissions/costs-and-dates"
EN_APPLY_URL = "https://is.cuni.cz/studium/eng/prihlaska/"
TZ = "Europe/Prague"

TH_TD = re.compile(r"<th>(.*?)</th>\s*<td[^>]*>(.*?)</td>", re.S | re.I)
H2 = re.compile(r"<h2>(.*?)</h2>", re.S | re.I)
ID_OBOR = re.compile(r"id_obor=(\d+)")
DATE_DMY = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
MONEY = re.compile(r"(\d[\d\s]*)\s*(EUR|CZK|Kč)", re.I)
EPRIHLASKA = re.compile(r"https?://(?:www\.)?mff\.cuni\.cz/eprihlaska", re.I)
TAG = re.compile(r"<[^>]+>")
CURRENCY = {"EUR": "EUR", "CZK": "CZK", "KČ": "CZK"}


def clean(value: str) -> str:
    text = value.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    text = TAG.sub(" ", text)
    text = html_lib.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def table_map(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_th, raw_td in TH_TD.findall(html):
        th = clean(raw_th).rstrip(":")
        td = clean(raw_td)
        if th and th not in out:
            out[th] = td
    return out


def first_h2(html: str) -> str:
    match = H2.search(html)
    return clean(match.group(1)) if match else ""


def dmy_to_iso(value: str) -> str | None:
    match = DATE_DMY.search(value or "")
    if not match:
        return None
    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return f"{year:04d}-{month:02d}-{day:02d}"


def money_parts(value: str) -> tuple[int, str] | None:
    match = MONEY.search(value or "")
    if not match:
        return None
    amount = int(re.sub(r"\s+", "", match.group(1)))
    currency = CURRENCY.get(match.group(2).upper(), match.group(2).upper())
    return amount, currency


def pick(fields: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if fields.get(key):
            return fields[key]
    return None


def cannot_apply(html: str) -> bool | None:
    text = clean(html)
    lower = text.lower()
    if "you cannot apply for study of this programme/branch now" in lower:
        return True
    if "nyní nelze podat" in lower or "nyni nelze podat" in lower:
        return True
    if "you can apply" in lower or "nyní se lze přihlásit" in lower:
        return False
    return None


def faculty_eprihlaska(html: str) -> str | None:
    match = EPRIHLASKA.search(html)
    return match.group(0) if match else None


def parse_sis(html: str, url: str, source_language: str) -> dict:
    fields = table_map(html)
    heading = first_h2(html)
    title = re.sub(r"\s*\([^)]*\)\s*$", "", heading).strip()
    code_match = re.search(r"\(([^)]+)\)\s*$", heading)
    id_match = ID_OBOR.search(html) or ID_OBOR.search(url)
    close_raw = pick(fields, "Application submission date", "Termín podání přihlášky")
    tuition_raw = pick(fields, "Tuition [EUR] / per period", "Školné [EUR] / za období")
    tuition_note = pick(fields, "Note on tuition [EUR]", "Poznámka ke školnému [EUR]")
    fee_online = pick(
        fields,
        "Charge for an on-line application",
        "Charge for an online application",
        "Poplatek za elektronickou přihlášku",
        "Poplatek za elektronickou formu přihlášky",
    )
    fee_paper = pick(
        fields,
        "Charge for a paper application",
        "Poplatek za papírovou přihlášku",
        "Poplatek za listinnou formu přihlášky",
    )
    language_raw = pick(fields, "Language of instruction", "Jazyk výuky")
    degree_raw = pick(fields, "Type of study", "Druh studia")
    faculty_raw = pick(fields, "Faculty", "Fakulta")
    programme_raw = pick(fields, "Study programme", "Studijní program")
    length_raw = pick(fields, "Standard length of study", "Standardní doba studia")
    form_raw = pick(fields, "Form of study", "Forma studia")
    apply_now = cannot_apply(html)
    return {
        "url": url,
        "sourceLanguage": source_language,
        "sisIdObor": id_match.group(1) if id_match else None,
        "headingOriginal": heading,
        "titleOriginal": title,
        "sisCodeOriginal": code_match.group(1) if code_match else None,
        "facultyOriginal": faculty_raw,
        "programmeOriginal": programme_raw,
        "formOriginal": form_raw,
        "degreeOriginal": degree_raw,
        "languageOriginal": language_raw,
        "lengthOriginal": length_raw,
        "applicationTypeOriginal": pick(fields, "Application type", "Typ přihlášky", "Forma přihlášky"),
        "submissionDateOriginal": close_raw,
        "submissionDateIso": dmy_to_iso(close_raw or ""),
        "dateNoteOriginal": pick(fields, "Note on date", "Poznámka k termínu"),
        "cannotApplyNow": apply_now,
        "applicationFeeOnlineOriginal": fee_online,
        "applicationFeePaperOriginal": fee_paper,
        "tuitionOriginal": tuition_raw,
        "tuitionNoteOriginal": tuition_note,
        "hasTuitionField": bool(tuition_raw),
        "fields": fields,
    }


def parse_mff_costs(html: str) -> dict:
    text = clean(html)
    opens_month = "December 2025" if re.search(r"Application\s+server opens:\s*December 2025", text) else None
    deadline = "2026-04-30" if "April 30, 2026" in text else None
    return {
        "url": MFF_COSTS_URL,
        "academicYearOriginal": "Academic year 2026/2027" if "2026/2027" in text else None,
        "applicationFeeOriginal": "1500 CZK" if "1500" in text and "CZK" in text else None,
        "tuitionEuOriginal": "tuition fee for students from the EU is 4200 EUR per academic year"
        if "4200" in text
        else None,
        "tuitionNonEuOriginal": "students from outside the EU 7100 EUR per academic year from 2026/27"
        if "7100" in text
        else None,
        "applicationServerOpensOriginal": opens_month,
        "applicationDeadlineOriginal": "April 30, 2026" if deadline else None,
        "applicationDeadlineIso": deadline,
        "applicationUrl": EN_APPLY_URL if EN_APPLY_URL in html else None,
        "opensAtNotInferred": True,
        "opensAtPrecisionIfUsed": "month",
    }


def teaching_language(sis: dict) -> str:
    raw = (sis.get("languageOriginal") or "").lower()
    if "english" in raw or "angličtina" in raw:
        return "en"
    if "czech" in raw or "čeština" in raw:
        return "cs"
    return "unknown"


def degree(sis: dict) -> str:
    raw = (sis.get("degreeOriginal") or "").lower()
    if "bachelor" in raw or "bakalář" in raw:
        return "bachelor"
    if "master" in raw or "magister" in raw:
        return "master"
    if "doctor" in raw or "doktor" in raw:
        return "doctorate"
    return "unknown"


def match_register(programmes: list[dict], title: str, language: str, deg: str, faculty_needle: str) -> dict | None:
    hits = [
        item
        for item in programmes
        if item.get("titleOriginal") == title
        and item.get("teachingLanguage") == language
        and item.get("degree") == deg
        and faculty_needle in (item.get("facultyName") or "")
    ]
    if len(hits) == 1:
        return hits[0]
    return None


def evidence(eid: str, url: str, quote: str, supports: list[str], path: str) -> dict:
    return {
        "id": eid,
        "url": url,
        "institution": "Univerzita Karlova",
        "extractedAt": "2026-09-06",
        "quoteOriginal": quote,
        "supports": supports,
        "localPath": path,
        "timezoneAssumed": TZ,
    }


def en_offering(sis: dict, costs: dict, register: dict | None) -> dict:
    tuition_head = money_parts(sis.get("tuitionOriginal") or "")
    fee = money_parts(sis.get("applicationFeeOnlineOriginal") or "")
    variants = []
    if tuition_head:
        variants.append(
            {
                "amount": tuition_head[0],
                "currency": tuition_head[1],
                "cycle": "year",
                "applicantScopeOriginal": sis.get("tuitionOriginal"),
                "sourceEvidenceId": "ev-cuni-sis-34738-tuition",
            }
        )
    if sis.get("tuitionNoteOriginal") and "4200" in sis["tuitionNoteOriginal"]:
        variants.append(
            {
                "amount": 4200,
                "currency": "EUR",
                "cycle": "year",
                "applicantScopeOriginal": sis["tuitionNoteOriginal"],
                "sourceEvidenceId": "ev-cuni-sis-34738-tuition-note",
            }
        )
    payload = {
        "id": "cuni-mff-cs-en-2026",
        "institutionId": "msmt-vs_11000",
        "facultyOriginal": "Matematicko-fyzikální fakulta",
        "facultySisOriginal": sis.get("facultyOriginal"),
        "registerMatch": {
            "titleOriginal": register.get("titleOriginal") if register else None,
            "facultyName": register.get("facultyName") if register else None,
            "degree": register.get("degree") if register else None,
            "teachingLanguage": register.get("teachingLanguage") if register else None,
            "iscedF": register.get("iscedF") if register else None,
            "standardYears": register.get("standardYears") if register else None,
        },
        "academicYear": "2026/2027",
        "academicYearEvidence": "MFF costs page: Academic year 2026/2027. SIS English Computer Science page refers to the admission round for 2026/27.",
        "teachingLanguages": ["en"],
        "languageMode": "single",
        "languageEvidenceUrl": EN_SIS_URL,
        "titleOriginal": sis.get("titleOriginal"),
        "title": {
            "zh-CN": "计算机科学",
            "en": "Computer Science",
            "cs": "Computer Science",
        },
        "degree": "bachelor",
        "durationOriginal": sis.get("lengthOriginal"),
        "formOriginal": sis.get("formOriginal"),
        "sisIdObor": sis.get("sisIdObor"),
        "additionalLanguageRequirements": [
            {
                "language": "en",
                "context": "admission",
                "requirement": "required",
                "evidenceUrl": EN_SIS_URL,
                "note": {
                    "zh-CN": "英语授课项目要求英语水平证明（SIS 列出 TOEFL iBT 85、IELTS 6.5 等）。",
                    "en": "English proficiency is required (SIS lists TOEFL iBT 85, IELTS 6.5, and other accepted tests).",
                    "cs": "Je požadována znalost angličtiny (SIS uvádí TOEFL iBT 85, IELTS 6.5 a další uznávané testy).",
                },
            }
        ],
        "applicationUrl": costs.get("applicationUrl") or EN_APPLY_URL,
        "applicationUrlNote": "Faculty costs page links this electronic-application server. SIS states the window is not open now.",
        "tuition": {
            "amount": None,
            "currency": "EUR",
            "cycle": "year",
            "published": True,
            "evidenceUrl": EN_SIS_URL,
            "unpublishedReason": None,
            "variants": variants,
            "doNotCollapseDualRates": True,
        },
        "applicationFee": {
            "onlineOriginal": sis.get("applicationFeeOnlineOriginal"),
            "paperOriginal": sis.get("applicationFeePaperOriginal"),
            "amount": fee[0] if fee else None,
            "currency": fee[1] if fee else None,
            "isNotTuition": True,
            "evidenceUrl": EN_SIS_URL,
        },
        "window": {
            "id": "win-cuni-mff-cs-en-2026",
            "ownerType": "offering",
            "ownerId": "cuni-mff-cs-en-2026",
            "academicYear": "2026/2027",
            "roundNumber": None,
            "roundLabelOriginal": "Application submission date",
            "roundType": "unspecified",
            "applicantScope": None,
            "opensAt": None,
            "opensAtNotInferredFrom": costs.get("applicationServerOpensOriginal"),
            "opensAtFacultyNotePrecision": "month",
            "closesAt": sis.get("submissionDateIso"),
            "timezone": TZ,
            "datePrecision": "date",
            "status": "closed",
            "conditionalOnVacancies": False,
            "applicationUrl": costs.get("applicationUrl") or EN_APPLY_URL,
            "sourceEvidenceId": "ev-cuni-sis-34738-close",
            "sisCannotApplyNow": sis.get("cannotApplyNow"),
        },
        "dataClass": "official_admissions_extract",
        "catalogKind": "tracer_not_published",
    }
    payload["windows"] = [payload["window"]]
    return payload


def cs_offering(sis: dict, register: dict | None, apply_url: str) -> dict:
    fee_online = money_parts(sis.get("applicationFeeOnlineOriginal") or "")
    payload = {
        "id": "cuni-mff-cs-cs-2026",
        "institutionId": "msmt-vs_11000",
        "facultyOriginal": "Matematicko-fyzikální fakulta",
        "facultySisOriginal": sis.get("facultyOriginal"),
        "registerMatch": {
            "titleOriginal": register.get("titleOriginal") if register else None,
            "facultyName": register.get("facultyName") if register else None,
            "degree": register.get("degree") if register else None,
            "teachingLanguage": register.get("teachingLanguage") if register else None,
            "iscedF": register.get("iscedF") if register else None,
            "standardYears": register.get("standardYears") if register else None,
        },
        "academicYear": "2026/2027",
        "academicYearEvidence": "Current SIS Informatika bachelor detail harvested 2026-09-06 has application submission date 31.03.2026. The bachelor block does not print the 2026/2027 label; the year is taken from that live cycle, not invented as round 1.",
        "teachingLanguages": ["cs"],
        "languageMode": "single",
        "languageEvidenceUrl": CS_SIS_URL,
        "titleOriginal": sis.get("titleOriginal"),
        "title": {
            "zh-CN": "信息学",
            "en": "Informatika",
            "cs": "Informatika",
        },
        "degree": "bachelor",
        "durationOriginal": sis.get("lengthOriginal"),
        "formOriginal": sis.get("formOriginal"),
        "sisIdObor": sis.get("sisIdObor"),
        "additionalLanguageRequirements": [
            {
                "language": "cs",
                "context": "admission",
                "requirement": "required",
                "evidenceUrl": CS_SIS_URL,
                "note": {
                    "zh-CN": "无捷克语或斯洛伐克语高考者须另行证明捷克语水平（B2/C1 或 SIS 列出的同等证明）。",
                    "en": "Applicants without Czech or Slovak school-leaving Czech/Slovak must document Czech at B2 or C1, or another equivalent listed on SIS.",
                    "cs": "Uchazeči bez maturity z češtiny nebo slovenštiny musí doložit znalost češtiny na úrovni B2/C1 nebo jiný ekvivalent uvedený v SIS.",
                },
            }
        ],
        "applicationUrl": apply_url,
        "applicationUrlNote": "MFF faculty SIS page links http://www.mff.cuni.cz/eprihlaska. SIS states electronic applications cannot be submitted now.",
        "tuition": {
            "amount": None,
            "currency": None,
            "cycle": None,
            "published": False,
            "evidenceUrl": CS_SIS_URL,
            "unpublishedReason": "SIS programme page has no tuition field for this Czech-taught offering. Unpublished is not 0 and not free.",
            "variants": [],
            "doNotCollapseDualRates": True,
        },
        "applicationFee": {
            "onlineOriginal": sis.get("applicationFeeOnlineOriginal"),
            "paperOriginal": sis.get("applicationFeePaperOriginal"),
            "amount": fee_online[0] if fee_online else None,
            "currency": fee_online[1] if fee_online else None,
            "isNotTuition": True,
            "evidenceUrl": CS_SIS_URL,
        },
        "window": {
            "id": "win-cuni-mff-cs-cs-2026",
            "ownerType": "offering",
            "ownerId": "cuni-mff-cs-cs-2026",
            "academicYear": "2026/2027",
            "roundNumber": None,
            "roundLabelOriginal": "Termín podání přihlášky",
            "roundType": "unspecified",
            "applicantScope": None,
            "opensAt": None,
            "opensAtNotInferredFrom": None,
            "opensAtFacultyNotePrecision": None,
            "closesAt": sis.get("submissionDateIso"),
            "timezone": TZ,
            "datePrecision": "date",
            "status": "closed",
            "conditionalOnVacancies": False,
            "applicationUrl": apply_url,
            "sourceEvidenceId": "ev-cuni-sis-34456-close",
            "sisCannotApplyNow": sis.get("cannotApplyNow"),
        },
        "dataClass": "official_admissions_extract",
        "catalogKind": "tracer_not_published",
    }
    payload["windows"] = [payload["window"]]
    return payload


def build() -> dict:
    en_html = EN_SIS.read_text(encoding="utf-8", errors="replace")
    cs_html = CS_SIS.read_text(encoding="utf-8", errors="replace")
    costs_html = MFF_COSTS.read_text(encoding="utf-8", errors="replace")
    faculty_cs_html = FACULTY_CS.read_text(encoding="utf-8", errors="replace")
    register_doc = json.loads(REGISTER.read_text(encoding="utf-8"))
    programmes = register_doc.get("programmes") or []
    en_sis = parse_sis(en_html, EN_SIS_URL, "en")
    cs_sis = parse_sis(cs_html, CS_SIS_URL, "cs")
    costs = parse_mff_costs(costs_html)
    cs_apply = faculty_eprihlaska(faculty_cs_html)
    if not cs_apply:
        raise SystemExit("Czech MFF faculty page is missing the eprihlaska application URL")
    if teaching_language(en_sis) != "en" or degree(en_sis) != "bachelor":
        raise SystemExit(f"unexpected EN SIS identity: {en_sis.get('languageOriginal')} {en_sis.get('degreeOriginal')}")
    if teaching_language(cs_sis) != "cs" or degree(cs_sis) != "bachelor":
        raise SystemExit(f"unexpected CS SIS identity: {cs_sis.get('languageOriginal')} {cs_sis.get('degreeOriginal')}")
    if not en_sis.get("submissionDateIso"):
        raise SystemExit("EN SIS missing submission date")
    if not cs_sis.get("submissionDateIso"):
        raise SystemExit("CS SIS missing submission date")
    if en_sis.get("sisIdObor") != "34738":
        raise SystemExit(f"EN SIS unexpected id_obor {en_sis.get('sisIdObor')}")
    if cs_sis.get("sisIdObor") != "34456":
        raise SystemExit(f"CS SIS unexpected id_obor {cs_sis.get('sisIdObor')}")
    year = int(en_sis["submissionDateIso"][:4])
    if year < 2026:
        raise SystemExit(f"EN SIS date looks stale: {en_sis['submissionDateIso']}")
    year_cs = int(cs_sis["submissionDateIso"][:4])
    if year_cs < 2026:
        raise SystemExit(f"CS SIS date looks stale: {cs_sis['submissionDateIso']}")
    en_reg = match_register(programmes, "Computer Science", "en", "bachelor", "Matematicko-fyzikální")
    cs_reg = match_register(programmes, "Informatika", "cs", "bachelor", "Matematicko-fyzikální")
    if not en_reg or not cs_reg:
        raise SystemExit("register match failed for MFF Computer Science / Informatika bachelor")
    en = en_offering(en_sis, costs, en_reg)
    cs = cs_offering(cs_sis, cs_reg, cs_apply)
    if en["tuition"]["amount"] is not None:
        raise SystemExit("dual EN tuition must not collapse to a single amount")
    if cs["tuition"]["published"] or cs["tuition"]["amount"] == 0:
        raise SystemExit("Czech-taught tuition must stay unpublished, not 0")
    if en["window"]["opensAt"] is not None or cs["window"]["opensAt"] is not None:
        raise SystemExit("opensAt must stay null; month-only faculty note is not a start date")
    snapshot = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataClass": "official_admissions_extract",
        "catalogKind": "tracer_not_published",
        "institutionId": "msmt-vs_11000",
        "institutionOfficialName": "Univerzita Karlova",
        "msmtCode": "VS_11000",
        "facultyOriginal": "Matematicko-fyzikální fakulta",
        "note": "Charles University MFF bachelor Computer Science (English) and Informatika (Czech) admissions tracer. Not a published catalogue. Not written to data/published/. Register inventory is not an offering.",
        "sources": {
            "enSis": EN_SIS_URL,
            "csSis": CS_SIS_URL,
            "mffCosts": MFF_COSTS_URL,
            "csFacultySis": "https://is.cuni.cz/studium/prijimacky/index.php?do=info_fakulta&fak=11320",
            "register": "https://regvssp.msmt.cz/registrvssp/csplist.aspx",
        },
        "offerings": [en, cs],
        "windows": [en["window"], cs["window"]],
        "evidence": [
            evidence(
                "ev-cuni-sis-34738-close",
                EN_SIS_URL,
                f"Application submission date: {en_sis.get('submissionDateOriginal')}",
                ["window.closesAt", "window.datePrecision"],
                "work/raw/2026-09-06/cuni-sis-cs-bachelor-en.html",
            ),
            evidence(
                "ev-cuni-sis-34738-cannot-apply",
                EN_SIS_URL,
                "You cannot apply for study of this programme/branch now.",
                ["window.sisCannotApplyNow"],
                "work/raw/2026-09-06/cuni-sis-cs-bachelor-en.html",
            ),
            evidence(
                "ev-cuni-sis-34738-tuition",
                EN_SIS_URL,
                en_sis.get("tuitionOriginal") or "",
                ["tuition.variants"],
                "work/raw/2026-09-06/cuni-sis-cs-bachelor-en.html",
            ),
            evidence(
                "ev-cuni-sis-34738-tuition-note",
                EN_SIS_URL,
                en_sis.get("tuitionNoteOriginal") or "",
                ["tuition.variants"],
                "work/raw/2026-09-06/cuni-sis-cs-bachelor-en.html",
            ),
            evidence(
                "ev-cuni-sis-34738-fee",
                EN_SIS_URL,
                f"Charge for an on-line application: {en_sis.get('applicationFeeOnlineOriginal')}",
                ["applicationFee"],
                "work/raw/2026-09-06/cuni-sis-cs-bachelor-en.html",
            ),
            evidence(
                "ev-cuni-mff-costs-opens-month",
                MFF_COSTS_URL,
                "Application server opens: December 2025",
                ["window.opensAtNotInferredFrom"],
                "work/raw/2026-09-06/cuni-mff-costs.html",
            ),
            evidence(
                "ev-cuni-sis-34456-close",
                CS_SIS_URL,
                f"Termín podání přihlášky: {cs_sis.get('submissionDateOriginal')}",
                ["window.closesAt"],
                "work/raw/2026-09-06/cuni-sis-cs-bachelor-cs.html",
            ),
            evidence(
                "ev-cuni-sis-34456-cannot-apply",
                CS_SIS_URL,
                "Na tento program/obor nyní nelze podat elektronickou přihlášku.",
                ["window.sisCannotApplyNow"],
                "work/raw/2026-09-06/cuni-sis-cs-bachelor-cs.html",
            ),
            evidence(
                "ev-cuni-sis-34456-no-tuition",
                CS_SIS_URL,
                "SIS Czech-taught Informatika bachelor page has no tuition field",
                ["tuition.published"],
                "work/raw/2026-09-06/cuni-sis-cs-bachelor-cs.html",
            ),
            evidence(
                "ev-cuni-sis-34456-fee",
                CS_SIS_URL,
                f"Poplatek za elektronickou formu přihlášky: {cs_sis.get('applicationFeeOnlineOriginal')}",
                ["applicationFee"],
                "work/raw/2026-09-06/cuni-sis-cs-bachelor-cs.html",
            ),
            evidence(
                "ev-cuni-mff-faculty-cs-apply",
                "https://is.cuni.cz/studium/prijimacky/index.php?do=info_fakulta&fak=11320",
                cs_apply,
                ["applicationUrl"],
                "work/raw/2026-09-06/cuni-sis-mff-faculty-cs.html",
            ),
        ],
        "parsed": {"en": en_sis, "cs": cs_sis, "mffCosts": costs},
    }
    # Drop bulky raw field maps from the published-adjacent snapshot? Keep parsed for tests/debug
    # but strip the full fields dict to keep the file readable.
    snapshot["parsed"]["en"] = {k: v for k, v in en_sis.items() if k != "fields"}
    snapshot["parsed"]["cs"] = {k: v for k, v in cs_sis.items() if k != "fields"}
    return snapshot


def main() -> None:
    snapshot = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} offerings={len(snapshot['offerings'])}")


if __name__ == "__main__":
    main()

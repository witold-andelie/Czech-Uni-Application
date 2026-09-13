"""Apply an operator-supplied CSCSE listed-name set onto the MŠMT baseline.

This is not a live scrape of yxcx.cscse.edu.cn. It records the operator list
dated 2026-09-06, matches names to the current ministry register, and does
not invent institutions. Listing is a lookup reference, not a certification
guarantee. Names on the list that are absent from the current register stay
unmatched instead of being created.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "data" / "sources" / "msmt-hei-baseline.json"
OUT_LIST = ROOT / "data" / "sources" / "cscse-operator-list-2026-09-06.json"
LOOKUP_URL = "http://yxcx.cscse.edu.cn/rzyxmd"
CHECKED_AT = "2026-09-06"
SOURCE_VERSION = "operator_supplied_list_2026-09-06"

# Explicit matches only. Do not fuzzy-match the rest of the 54 HEIs.
LISTED: list[dict] = [
    {"n": 1, "zh": "奥帕瓦西里西亚大学", "en": "Silesian University in Opava", "msmtCode": "VS_19000", "officialName": "Slezská univerzita v Opavě"},
    {"n": 2, "zh": "AMBIS大学", "en": "AMBIS University", "msmtCode": "VS_61000", "officialName": "AMBIS vysoká škola, a.s."},
    {"n": 3, "zh": "奥斯特拉发大学", "en": "Ostravská Univerzita", "msmtCode": "VS_17000", "officialName": "Ostravská univerzita"},
    {"n": 4, "zh": "奥斯特拉发技术大学", "en": "VSB-Technical University of Ostrava", "msmtCode": "VS_27000", "officialName": "Vysoká škola báňská – Technická univerzita Ostrava"},
    {"n": 5, "zh": "比尔森西波西米亚大学", "en": "Západočeská Univerzita v Plzni", "msmtCode": "VS_23000", "officialName": "Západočeská univerzita v Plzni"},
    {"n": 6, "zh": "布拉格表演艺术学院", "en": "Akademie muzickych umeni v Praze", "msmtCode": "VS_51000", "officialName": "Akademie múzických umění v Praze"},
    {"n": 7, "zh": "布拉格化工大学", "en": "Vysoká škola chemicko-technologická v Praze", "msmtCode": "VS_22000", "officialName": "Vysoká škola chemicko-technologická v Praze"},
    {"n": 8, "zh": "布尔诺理工大学", "en": "Brno University of Technology", "msmtCode": "VS_26000", "officialName": "Vysoké učení technické v Brně"},
    {"n": 9, "zh": "布拉格经济大学", "en": "Vysoká škola ekonomická v Praze", "msmtCode": "VS_31000", "officialName": "Vysoká škola ekonomická v Praze"},
    {"n": 10, "zh": "布尔诺孟德尔大学", "en": "Mendel University in Brno", "msmtCode": "VS_43000", "officialName": "Mendelova univerzita v Brně"},
    {"n": 11, "zh": "布拉格城市大学", "en": "Metropolitan University Prague", "msmtCode": "VS_75000", "officialName": "Metropolitní univerzita Praha, o. p. s."},
    {"n": 12, "zh": "布拉格捷克技术大学", "en": "Czech Technical University in Prague", "msmtCode": "VS_21000", "officialName": "České vysoké učení technické v Praze"},
    {"n": 13, "zh": "查理大学", "en": "Univerzita Karlova", "msmtCode": "VS_11000", "officialName": "Univerzita Karlova"},
    {"n": 14, "zh": "泛欧大学", "en": "Panevropská univerzita", "msmtCode": "VS_7S000", "officialName": "Panevropská univerzita, a.s."},
    {"n": 15, "zh": "捷克布杰约维采南波西米亚大学", "en": "Jihočeská univerzita v Českých Budějovicích", "msmtCode": "VS_12000", "officialName": "Jihočeská univerzita v Českých Budějovicích"},
    {"n": 16, "zh": "金融与管理大学", "en": "The University of Finance and Administration", "msmtCode": "VS_7U000", "officialName": "Vysoká škola finanční a správní, a.s."},
    {"n": 17, "zh": "捷克生命科学大学", "en": "Czech University of Life Sciences Prague", "msmtCode": "VS_41000", "officialName": "Česká zemědělská univerzita v Praze"},
    {"n": 18, "zh": "利贝雷茨技术大学", "en": "Technical University of Liberec", "msmtCode": "VS_24000", "officialName": "Technická univerzita v Liberci"},
    {"n": 19, "zh": "马萨里克大学", "en": "Masaryk University", "msmtCode": "VS_14000", "officialName": "Masarykova univerzita"},
    {"n": 20, "zh": "纽约大学布拉格分校", "en": "University of New York in Prague", "msmtCode": "VS_6D000", "officialName": "University of New York in Prague, s.r.o."},
    {"n": 21, "zh": "帕拉茨基大学", "en": "Palacký University Olomouc", "msmtCode": "VS_15000", "officialName": "Univerzita Palackého v Olomouci"},
    {"n": 22, "zh": "帕尔杜比采大学", "en": "Univerzita Pardubice", "msmtCode": "VS_25000", "officialName": "Univerzita Pardubice"},
    {"n": 23, "zh": "斯科达汽车大学", "en": "ŠKODA AUTO Vysoká škola o.p.s.", "msmtCode": "VS_7P000", "officialName": "Škoda Auto Vysoká škola o.p.s."},
    {"n": 24, "zh": "雅纳切克音乐艺术学院", "en": "Janáčkova akademie múzických umění v Brně", "msmtCode": "VS_54000", "officialName": "Janáčkova akademie múzických umění"},
]

UNMATCHED: list[dict] = [
    {
        "n": 25,
        "zh": "政治与社会科学学院",
        "en": "Academia Rerum Civilium – Vysoká škola politických a společenských věd",
        "msmtCode": None,
        "reason": "Not among the 54 HEIs on the MŠMT register harvested 2026-09-06. Public reports: private non-university HEI; state approval 2003; insolvency and loss of accreditation in 2022; activity ended. Not created as a current catalogue row.",
        "reasonZh": "未出现在 2026-09-06 教育部现行 54 所登记中。公开报道：私立非大学型高校，2003 年获国家批准，2022 年破产、取消认证后停办。未做成现行高校条目，也未把可查标签标到其他学校。",
    }
]


def listed_by_code() -> dict[str, dict]:
    return {item["msmtCode"]: item for item in LISTED}


def apply(payload: dict) -> dict:
    by_code = listed_by_code()
    listed = 0
    not_found = 0
    for item in payload["institutions"]:
        hit = by_code.get(item["msmtCode"])
        if hit:
            if hit["officialName"] != item["officialName"]:
                raise SystemExit(
                    f"CSCSE map officialName drift for {item['msmtCode']}: "
                    f"{hit['officialName']!r} vs register {item['officialName']!r}"
                )
            existing = item.get("cscseReference") or {}
            item["cscseLookupStatus"] = "unverified"
            item["cscseReference"] = {
                "lookupStatus": "unverified",
                "operatorListStatus": "listed",
                "evidenceKind": "operator_supplied_list",
                "listedNameZh": hit["zh"],
                "listedNameEn": hit["en"],
                "officialMatchedName": item["officialName"],
                "matchedAwardingInstitutionId": item["id"],
                "lookupUrl": LOOKUP_URL,
                "checkedAt": None,
                "operatorListDated": CHECKED_AT,
                "sourceVersion": SOURCE_VERSION,
                "evidenceId": "ev-cscse-operator-list-2026-09-06",
                "reviewer": "operator",
                "matchConfidence": "exact",
                "notices": existing.get("notices") or [],
            }
            listed += 1
        else:
            existing = item.get("cscseReference") or {}
            item["cscseLookupStatus"] = "unverified"
            item["cscseReference"] = {
                "lookupStatus": "unverified",
                "operatorListStatus": "absent",
                "evidenceKind": "operator_supplied_list",
                "listedNameZh": None,
                "listedNameEn": None,
                "officialMatchedName": None,
                "matchedAwardingInstitutionId": None,
                "lookupUrl": LOOKUP_URL,
                "checkedAt": None,
                "operatorListDated": CHECKED_AT,
                "sourceVersion": SOURCE_VERSION,
                "evidenceId": "ev-cscse-operator-list-2026-09-06",
                "reviewer": "operator",
                "matchConfidence": None,
                "notices": existing.get("notices") or [],
            }
            not_found += 1
    payload["cscseApply"] = {
        "at": date.fromisoformat(CHECKED_AT).isoformat(),
        "sourceVersion": SOURCE_VERSION,
        "lookupUrl": LOOKUP_URL,
        "operatorListedNames": len(LISTED) + len(UNMATCHED),
        "matchedListed": listed,
        "registerNotOnList": not_found,
        "unmatchedOperatorNames": len(UNMATCHED),
        "note": "Operator-supplied CSCSE listed names matched to the current MŠMT register. Not a live official CSCSE lookup. Public lookupStatus remains unverified until a retrievable official result exists. operatorListStatus=listed means the current register row was on this supplied list; absent means it was not.",
    }
    payload["cscseUnmatched"] = UNMATCHED
    return payload


def write_list_artifact() -> None:
    OUT_LIST.write_text(
        json.dumps(
            {
                "suppliedAt": CHECKED_AT,
                "sourceVersion": SOURCE_VERSION,
                "lookupUrl": LOOKUP_URL,
                "note": "Operator-supplied CSCSE listed names. Matches are to the current MŠMT HEI register only.",
                "listedMatched": LISTED,
                "unmatched": UNMATCHED,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    payload = apply(payload)
    write_list_artifact()
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "matchedListed": payload["cscseApply"]["matchedListed"],
                "registerNotOnList": payload["cscseApply"]["registerNotOnList"],
                "unmatchedOperatorNames": payload["cscseApply"]["unmatchedOperatorNames"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

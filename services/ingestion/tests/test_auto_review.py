from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import auto_review  # noqa: E402
from harvest_nine_hei_jobs import apply_translation_review  # noqa: E402
from publication_rules import job_fact_hash  # noqa: E402
from title_translation import validate  # noqa: E402

NOW = "2026-10-02T21:00:00Z"
TODAY = date(2026, 10, 2)


def _job(**overrides) -> dict:
    job = {
        "id": "job-x",
        "employerId": "msmt-vs_21000",
        "originalText": "Odborný asistent v oboru algebra (úvazek 1,0)",
        "track": "post_master",
        "catalogueScopeStatus": "included",
        "lifecycleStatus": "unknown",
        "visibility": "review_pending",
        "applicationUrl": "https://uni.test/job/1",
        "sourceHash": "sha256:" + "a" * 64,
        "minimumDegree": "doctorate",
        "paidStatus": "confirmed",
    }
    job.update(overrides)
    return job


def _fake(title: str, language: str) -> dict:
    return {"en": "Assistant Professor in Algebra (1.0 FTE)", "cs": title, "zh-CN": "代数方向助理教授（1.0 工作量）"}


def test_a_vacancy_without_human_review_is_approved_with_machine_titles() -> None:
    payload = {"jobs": [_job()], "windows": []}
    auto, cache = {}, {}
    report = auto_review.run(payload, {}, auto, cache, today=TODAY, now=NOW, translate=_fake)
    assert report["approved"] == ["job-x"]
    entry = auto["job-x"]
    assert entry["reviewer"] == {"role": "automatic_pipeline"}
    assert {locale: item["status"] for locale, item in entry["locales"].items()} == {
        "zh-CN": "machine", "en": "machine", "cs": "reviewed"}
    job = apply_translation_review(dict(payload["jobs"][0]), payload["jobs"][0]["sourceHash"], {"job-x": entry}, [])
    assert job["publicationStatus"] == "approved" and job["reviewMode"] == "automatic"
    assert job["translationReview"]["locales"]["zh-CN"]["status"] == "machine"
    # A second run reuses the cached translation and keeps the entry.
    again = auto_review.run(payload, {}, auto, cache, today=TODAY, now=NOW, translate=lambda *a: 1 / 0)
    assert again["kept"] == ["job-x"] and again["translated"] == 0


def test_human_reviews_and_operator_decisions_win() -> None:
    job = _job()
    human = {"factHash": job_fact_hash(job, []), "title": {"zh-CN": "人工", "en": "Human", "cs": "Lidský"}}
    auto = {"job-x": {"factHash": "old"}}
    report = auto_review.run({"jobs": [job], "windows": []}, {"job-x": human}, auto, {}, today=TODAY, now=NOW, translate=_fake)
    assert report["humanMatches"] == 1 and auto == {}
    decided = {"job-x": {"disposition": {"publicationStatus": "rejected", "reason": "out_of_scope_administrative"}}}
    auto_review.run({"jobs": [job], "windows": []}, decided, auto, {}, today=TODAY, now=NOW, translate=_fake)
    assert auto == {}


def test_stale_human_review_rebinds_facts_and_keeps_human_titles() -> None:
    job = _job(minimumDegree="master")
    human = {"factHash": "sha256:old", "title": {"zh-CN": "人工", "en": "Human", "cs": "Lidský"}}
    auto: dict = {}
    auto_review.run({"jobs": [job], "windows": []}, {"job-x": human}, auto, {}, today=TODAY, now=NOW, translate=lambda *a: 1 / 0)
    assert auto["job-x"]["title"]["en"] == "Human"
    assert {item["status"] for item in auto["job-x"]["locales"].values()} == {"reviewed"}


def test_gates_withhold_and_say_why() -> None:
    payload = {"jobs": [
        _job(id="chrome", originalText="Přejít na hlavní obsah"),
        _job(id="dated", originalText="30.09.2026 Volná místa, konkursy Výběrové řízení"),
        _job(id="scope", track=None),
        _job(id="late"),
    ], "windows": [{"ownerId": "late", "closesAt": "2026-09-30"}]}
    report = auto_review.run(payload, {}, {}, {}, today=TODAY, now=NOW, translate=_fake)
    assert report["approved"] == []
    assert "title-is-page-chrome" in report["withheld"]["chrome"]
    assert "title-is-page-chrome" in report["withheld"]["dated"]
    assert "outside-research-catalogue-scope" in report["withheld"]["scope"]
    assert "deadline-passed" in report["withheld"]["late"]


def test_translation_checks_withhold_a_changed_number_or_missing_chinese() -> None:
    title = "Odborný/ná pracovník/ce v analytické laboratoři (úvazek 1,0)"
    assert validate(title, "cs", {"cs": title, "en": "Specialist (1.0 FTE)", "zh-CN": "专家（1.0 工作量）"}) == []
    problems = validate(title, "cs", {"cs": title, "en": "Specialist (time 1,0)", "zh-CN": "分析实验室专家(时间:1 000)"})
    assert "zh-CN-numbers-changed" in problems
    assert "zh-CN-not-chinese" in validate(title, "cs", {"cs": title, "en": "Specialist (1.0 FTE)", "zh-CN": "Specialist 1.0"})
    report = auto_review.run({"jobs": [_job()], "windows": []}, {}, {}, {}, today=TODAY, now=NOW,
                             translate=lambda t, lang: {"en": "Assistant", "cs": t, "zh-CN": "助理"})
    assert any(reason.startswith("translation:") for reason in report["withheld"]["job-x"])


def test_contract_accepts_machine_titles_only_from_the_automatic_pipeline() -> None:
    from publication_contract import _validate_translation_review
    from publication_rules import translation_content_hash

    source = "sha256:" + "b" * 64
    titles = {"zh-CN": "代数方向助理教授", "en": "Assistant Professor in Algebra", "cs": "Odborný asistent v oboru algebra"}
    job = {"id": "job-y", "sourceHash": source, "title": titles, "minimumDegree": "doctorate"}

    def review(role: str) -> dict:
        return {
            "sourceHash": source, "evidenceHash": source, "normalizationVersion": "fact-v2",
            "reviewer": {"role": role}, "factHash": job_fact_hash(job, [], "fact-v2"),
            "locales": {
                locale: {"status": "reviewed" if locale == "cs" else "machine", "translatedFromHash": source,
                         "reviewedAt": NOW, "contentHash": translation_content_hash(text)}
                for locale, text in titles.items()
            },
        }

    for role, ok in (("automatic_pipeline", True), ("operator_source_review", False)):
        errors: list[str] = []
        _validate_translation_review({**job, "translationReview": review(role)}, "job-y", errors, windows=[], evidence_hash=source)
        assert (not any("not reviewed" in error for error in errors)) is ok, (role, errors)

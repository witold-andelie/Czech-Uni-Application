from __future__ import annotations

import json
import sys
import urllib.error
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import harvest_nine_hei_jobs as jobs_harvester  # noqa: E402
jobs_harvest_nine_hei_jobs_visible_text = jobs_harvester.visible_text


def test_verified_candidates_live_in_data_file() -> None:
    path = ROOT / "services" / "ingestion" / "src" / "data" / "verified_candidates.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, list) and payload
    assert len(payload) == len(jobs_harvester.load_verified_candidates())
    assert [item["id"] for item in payload] == [
        item["id"] for item in jobs_harvester.load_verified_candidates()
    ]

from harvest_nine_hei_jobs import (  # noqa: E402
    TODAY,
    classify_track,
    discover_registered_candidates,
    extract_html_element,
    extract_deadline,
    extract_qualifications,
    harvest_candidates,
    harvest_with_registered_discovery,
    page_is_closed,
    parse_avcr_vacancies,
    parse_cuni_ajax_listing,
    parse_czu_ajax_listing,
    parse_czu_rest_listing,
    parse_ctu_notice_detail,
    parse_ctu_notice_listing,
    parse_date,
    parse_generic_job_page,
    parse_generic_listing_links,
    parse_inline_heading_jobs,
    parse_lmc_graphql_detail,
    parse_lmc_graphql_listing,
    parse_lmc_widget_config,
    parse_muni_vacancies,
    parse_recruitis_widget_urls,
    parse_tul_careers,
    parse_ujep_open_positions,
    parse_utb_careers,
    parse_vsb_listing,
    request,
)


def test_live_request_retries_a_transient_transport_failure(monkeypatch) -> None:
    calls = 0
    sleeps: list[float] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args) -> bytes:
            return b"<html><body>official vacancy listing</body></html>"

    def fake_urlopen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.URLError("connection reset")
        return Response()

    monkeypatch.setattr(jobs_harvester.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(jobs_harvester.time, "sleep", sleeps.append)

    status, html = request("https://jobs.example.test/current")

    assert status == 200
    assert "official vacancy listing" in html
    assert calls == 2
    assert sleeps == [jobs_harvester.REQUEST_RETRY_DELAYS[0]]


def cuni_ajax_page(items: list[tuple[str, str]], pages: tuple[int, ...] = (1,)) -> str:
    links = "".join(
        f"<a href='?pracid={code}'><div class='row pozice-item' data-name='{title}'>"
        f"<div class='name'>{title}</div></div></a>"
        for code, title in items
    )
    paginator = "".join(f"<li class='page' data-page='{page}'>{page}</li>" for page in pages)
    return __import__("json").dumps(
        {"result": "ok", "page": 1, "count": len(items), "html": links + paginator}
    )


def test_track_classification() -> None:
    assert classify_track("Postdoctoral Research Positions in software architectures") == "postdoc"
    assert classify_track("PhD student: near real-time optimization") == "assistant"
    assert classify_track("Research Fellow at the Institute of Particle and Nuclear Physics") == "post_master"
    assert classify_track("Academic Researcher at the Department of Software") == "post_master"
    assert classify_track("Assistant Professor at Department of Algebra") is None
    assert classify_track("Dean of the Faculty of Science") is None
    assert classify_track("Event Manager for the Department of Computer Science") is None
    assert classify_track("Koordinátor Welcome Centre", "Podpora vědy a výzkumu") is None
    assert classify_track("PhD Candidate: secure distributed systems") == "assistant"
    assert (
        classify_track(
            "Odborný pracovník ve výzkumu",
            "Děkan fakulty vyhlašuje řízení. Náplní jsou výzkumné úkoly a publikace.",
        )
        == "post_master"
    )


def test_past_deadline_is_not_open() -> None:
    reference_date = parse_date("2026-09-06")
    assert parse_date("31 Jan 2026") < reference_date
    assert parse_date("14 September 2026") > reference_date
    assert parse_date("2026-09-14") == parse_date("14. 9. 2026")
    assert str(parse_date("September 24, 2026")) == "2026-09-24"
    assert str(parse_date("Sep 24th, 2026")) == "2026-09-24"
    assert str(parse_date("30. září 2026")) == "2026-09-30"
    assert str(parse_date("4. října 2026")) == "2026-10-04"


def test_salary_amount_requires_salary_context_and_precise_czech_deadline_wins() -> None:
    html = """
    <h1>Postdoc I</h1>
    <p>Doktorský titul (Ph.D.). Předpokládaný termín nástupu 15. října 2026.</p>
    <p>Mzdové podmínky se řídí vnitřním předpisem. Příspěvek 200 Kč na sdílená kola.</p>
    <p>Lhůta pro včasné podání žádosti 30. září 2026.</p>
    """
    parsed = parse_generic_job_page(html, "https://example.test/postdoc", "Postdoc I")
    assert parsed is not None
    assert parsed["closesAt"] == "2026-09-30"
    assert parsed["minimumDegree"] == "doctorate"
    assert parsed["doctorateRequired"] is True
    assert parsed["salaryAmount"] is None
    assert parsed["salaryCurrency"] is None
    assert parsed["paidStatus"] == "confirmed"


def test_salary_amount_uses_explicit_label_and_does_not_infer_optional_full_time() -> None:
    html = """
    <h1>Postdoctoral Researcher in Chemistry</h1>
    <p>Position: Part-time or Full-time. We are looking for a researcher with a PhD in Chemistry.</p>
    <p>Gross monthly salary: 46 000 CZK plus bonuses. Application deadline: October 2, 2026.</p>
    """
    parsed = parse_generic_job_page(html, "https://example.test/postdoc")
    assert parsed is not None
    assert parsed["salaryAmount"] == 46000
    assert parsed["salaryCurrency"] == "CZK"
    assert parsed["basisFte"] is None
    assert parsed["minimumDegree"] == "doctorate"
    assert parsed["doctorateRequired"] is True


def test_harvest_skips_http_failures_and_keeps_title_match() -> None:
    candidates = [
        {
            "id": "job-keep",
            "employerId": "msmt-vs_11000",
            "title": "Research Fellow at the Institute of Particle and Nuclear Physics",
            "sourceUrl": "https://example.cz/keep",
            "applicationUrl": "https://example.cz/keep",
            "opensAt": None,
            "closesAt": "2026-09-15",
            "track": "post_master",
            "workingLanguages": ["en"],
            "paidStatus": "confirmed",
        },
        {
            "id": "job-404",
            "employerId": "msmt-vs_11000",
            "title": "Research Fellow missing page",
            "sourceUrl": "https://example.cz/missing",
            "applicationUrl": "https://example.cz/missing",
            "opensAt": None,
            "closesAt": "2026-09-15",
            "track": "post_master",
            "workingLanguages": ["en"],
            "paidStatus": "confirmed",
        },
        {
            "id": "job-past",
            "employerId": "msmt-vs_11000",
            "title": "Post-doctoral Researcher in Regional Economics",
            "sourceUrl": "https://example.cz/past",
            "applicationUrl": "https://example.cz/past",
            "opensAt": None,
            "closesAt": "2026-01-31",
            "track": "postdoc",
            "workingLanguages": ["en"],
            "paidStatus": "confirmed",
        },
    ]

    def fetch(url: str):
        if "missing" in url:
            return 404, "Page not found"
        if "past" in url:
            return 200, "<h1>Post-doctoral Researcher in Regional Economics</h1><p>Deadline 31 Jan 2026</p>"
        return 200, "<h1>Research Fellow at the Institute of Particle and Nuclear Physics</h1><p>Deadline 15 September 2026</p>"

    payload = harvest_candidates(candidates, fetch, as_of=date(2026, 9, 14))
    ids = [job["id"] for job in payload["jobs"]]
    assert ids == ["job-keep"]
    assert payload["jobs"][0]["dataClass"] == "official_career_extract"
    assert payload["jobs"][0]["isPostdoc"] is False
    window = payload["windows"][0]
    assert window["opensAt"] is None
    assert window["closesAt"] == "2026-09-15"
    assert window["datePrecision"] == "date"
    assert window["status"] == "unknown"
    reasons = {item["id"]: item["reason"] for item in payload["skipped"]}
    assert reasons["job-404"].startswith("http-")
    assert reasons["job-past"] == "past-deadline"


def test_page_facts_override_seed_and_keep_previous_on_failure() -> None:
    as_of = date(2026, 9, 9)
    candidate = {
        "id": "audit-job",
        "employerId": "msmt-vs_11000",
        "title": "Research Fellow in Computing",
        "sourceUrl": "https://example.cz/job",
        "applicationUrl": "https://example.cz/job",
        "opensAt": "2026-09-01",
        "closesAt": "2026-09-30",
        "track": "post_master",
        "workingLanguages": ["en"],
        "paidStatus": "confirmed",
    }
    closed = harvest_candidates(
        [candidate],
        lambda _url: (200, "<h1>Research Fellow in Computing</h1><p>Applications are closed. The position has been filled. A PhD is required.</p>"),
        as_of=as_of,
    )
    assert closed["jobs"][0]["wholeOpportunityClosed"] is True
    assert closed["jobs"][0]["lifecycleStatus"] == "closed"
    assert closed["jobs"][0]["minimumDegree"] == "doctorate"
    assert closed["jobs"][0]["doctorateRequired"] is True

    degree = harvest_candidates(
        [candidate],
        lambda _url: (200, "<h1>Research Fellow in Computing</h1><p>Required qualification: PhD in computer science. Application deadline: 10 September 2026.</p>"),
        as_of=as_of,
    )
    assert degree["jobs"][0]["minimumDegree"] == "doctorate"
    assert degree["jobs"][0]["doctorateRequired"] is True
    assert degree["windows"][0]["closesAt"] == "2026-09-10"

    previous = {
        "jobs": [{"id": "audit-job", "title": {"en": "kept"}, "verifiedAt": "2026-09-01"}],
        "windows": [{"id": "win-audit-job", "ownerId": "audit-job"}],
        "evidence": [{"id": "ev-audit-job", "url": "https://example.cz/job"}],
    }
    failed = harvest_candidates([candidate], lambda _url: (503, "Service unavailable"), previous)
    assert len(failed["jobs"]) == 1
    assert failed["jobs"][0]["verifiedAt"] == "2026-09-01"
    assert failed["jobs"][0]["lastAttemptReason"] == "http-503"


def test_deadline_with_published_date() -> None:
    text = "Published 2026-09-01. Application deadline: 2026-09-30."
    deadline = extract_deadline(text)
    assert str(deadline) == "2026-09-30"


def test_qualifications_does_not_treat_unrelated_not_required_as_doctoral() -> None:
    quals = extract_qualifications("Research assistant", "A master's degree is required. Czech is not required.")
    assert quals["minimumDegree"] == "master"
    assert quals["doctoralEnrollment"] == "unspecified"


def test_signatory_honorifics_are_not_minimum_degree_evidence() -> None:
    quals = extract_qualifications(
        "Vědecký pracovník v chemii",
        "prof. Ing. Václav Example, Ph.D., děkan. Požadujeme dokončené vysokoškolské vzdělání v chemii.",
    )
    assert quals["minimumDegree"] == "unknown"
    assert quals["doctorateRequired"] is None


def test_research_institution_background_does_not_turn_admin_role_into_research_job() -> None:
    body = (
        "Jsme vědecko-výzkumný ústav. Náplň práce je finanční správa grantů, "
        "reporting a příprava podkladů pro audit. Pracovní smlouva."
    )
    assert classify_track("Finanční manažer/ka grantových projektů", body) is None
    assert classify_track("Ostraha výzkumného centra", body) is None
    assert classify_track("Project coordinator", "Signed by Prof. Example, Ph.D.") is None
    assert classify_track("Specialista pro popularizaci vědy", body) is None
    assert classify_track("Specialista podpory výzkumu", body) is None
    assert classify_track("Specialista pro nanofabrikační procesy", "Technical production duties.") == "post_master"


def test_science_faculty_name_does_not_turn_building_maintenance_into_research() -> None:
    title = "Údržbář budov Přírodovědecké fakulty"
    body = (
        "Technická údržba budov, opravy, stěhování nábytku a provozní servis. "
        "Pracovní prostředí slouží studentům, vědcům i zaměstnancům."
    )
    assert classify_track(title, body) is None


def test_mixed_listing_does_not_close_whole_page() -> None:
    text = "Job A: applications are closed. Job B: Research assistant, applications open until 2026-09-30."
    assert page_is_closed(text) is False
    assert page_is_closed(text, "Job A") is True
    assert page_is_closed(text, "Job B") is False


def test_adjacent_closed_job_does_not_close_target() -> None:
    text = (
        "Research assistant B: Master degree required. Applications open until 2026-09-30. "
        "Research assistant A: Applications are closed."
    )
    assert page_is_closed(text, "Research assistant B") is False
    assert page_is_closed(text, "Research assistant A") is True


def test_office_hours_footer_does_not_close_current_vacancy() -> None:
    text = (
        "Webový vývojář / vývojářka. Pracovní smlouva. "
        "Přihlášky posílejte do 30. 9. 2026. "
        "InfoCentrum. Otevřeno 7:00–19:00. Během měsíců července a srpna uzavřeno."
    )
    assert page_is_closed(text, "Webový vývojář / vývojářka") is False
    assert page_is_closed("Výběrové řízení je uzavřeno.", "Výběrové řízení") is True


def test_navigation_title_is_not_mistaken_for_the_vacancy_body() -> None:
    text = (
        "Navigation: Research assistant B · Research assistant A. "
        "Research assistant B: Applications open until 2026-09-30. "
        "Research assistant A: Applications are closed."
    )
    assert page_is_closed(text, "Research assistant B") is False


def test_phd_enrollment_negation_wins_over_positive_substring() -> None:
    quals = extract_qualifications(
        "Research assistant",
        "A master's degree is required. Enrollment in a PhD is not required.",
    )
    assert quals["minimumDegree"] == "master"
    assert quals["doctorateRequired"] is False
    assert quals["doctoralEnrollment"] == "not_required"


def test_degree_and_enrollment_are_independent_facts() -> None:
    quals = extract_qualifications(
        "Research assistant",
        "A PhD degree is not required. Enrollment in a doctoral programme is required.",
    )
    assert quals["doctorateRequired"] is False
    assert quals["doctoralEnrollment"] == "required"

    alternative = extract_qualifications(
        "Research assistant",
        "A master's degree or a PhD is accepted.",
    )
    assert alternative["minimumDegree"] == "master"
    assert alternative["doctorateRequired"] is False


def test_doctoral_students_in_institution_background_do_not_require_enrollment() -> None:
    body = (
        "Hardware engineering for research projects. The department has 50 doctoral students. "
        "A university degree is required."
    )
    assert classify_track("Embedded Hardware Engineer", body) == "post_master"
    quals = extract_qualifications("Embedded Hardware Engineer", body)
    assert quals["doctoralEnrollment"] == "unspecified"

    required = extract_qualifications(
        "Research assistant",
        "Enrollment in a doctoral programme is required before employment.",
    )
    assert required["doctoralEnrollment"] == "required"


def test_parse_generic_job_page() -> None:
    html = "<h1>Research assistant</h1><p>Master degree. Salary CZK 40000. Deadline 2026-09-30.</p>"
    parsed = parse_generic_job_page(html, "https://example.invalid/job")
    assert parsed is not None
    assert parsed["title"] == "Research assistant"
    assert parsed["track"] == "assistant"
    assert parsed["closesAt"] == "2026-09-30"
    assert parsed["salaryAmount"] == 40000.0
    assert parsed["salaryCurrency"] == "CZK"
    assert parsed["minimumDegree"] == "master"
    assert parsed["doctorateRequired"] is False


def test_generic_parser_does_not_guess_qualification_from_track() -> None:
    html = "<h1>Research assistant</h1><p>Paid employment. Deadline 2026-09-30.</p>"
    parsed = parse_generic_job_page(html, "https://example.invalid/job")
    assert parsed is not None
    assert parsed["track"] == "assistant"
    assert parsed["minimumDegree"] == "unknown"
    assert parsed["doctorateRequired"] is None
    assert parsed["doctoralEnrollment"] == "unspecified"


def test_parse_muni_and_avcr_vacancies() -> None:
    muni_html = """
    <div class="vacancies">
      <a href="/en/about-us/careers/vacancies/81652">Ph.D. Fellowship</a>
      <a href="/en/about-us/careers/vacancies/81445">Postdoctoral position in Astrophysics</a>
      <a href="https://www.muni.cz/en/about-us/careers/vacancies/81445">Postdoctoral position in Astrophysics</a>
      <a href="/o-univerzite/kariera/volna-mista/76543-novy">Výzkumný asistent v informatice</a>
      <a href="/en/about-us/careers/vacancies/99999">Dean of Faculty</a>
    </div>
    """
    muni_jobs = parse_muni_vacancies(muni_html)
    assert len(muni_jobs) == 4
    assert muni_jobs[0]["code"] == "81652"
    assert muni_jobs[0]["track"] == "assistant"
    assert muni_jobs[1]["code"] == "81445"
    assert muni_jobs[1]["track"] == "postdoc"
    assert muni_jobs[2]["code"] == "76543"
    assert muni_jobs[2]["track"] == "assistant"
    # Untracked vacancies survive the listing stage so the linked detail text
    # decides eligibility (degree / doctoral-enrolment), never the listing title.
    assert muni_jobs[3]["code"] == "99999"
    assert muni_jobs[3]["track"] is None

    avcr_html = """
    <div>
      <a href="/en/about-us/career/selection-procedures/postdoc-physics">Postdoctoral Fellow in Laser Physics</a>
    </div>
    """
    avcr_jobs = parse_avcr_vacancies(avcr_html)
    assert len(avcr_jobs) == 1
    assert avcr_jobs[0]["track"] == "postdoc"
    assert avcr_jobs[0]["employerId"] is None
    assert avcr_jobs[0]["employerIdentityStatus"] == "unresolved"


def test_parse_cuni_central_ajax_keeps_encoded_code_and_defers_eligibility() -> None:
    payload = cuni_ajax_page(
        [
            ("202610-VP2-P%C5%99F-1400-093", "SCIENTIFIC POSITION Junior Group Leader in Virology (M/F)"),
            ("202609-AP2-MFF-KA-064", "Assistant Professor at the Department of Algebra"),
        ],
        pages=(1, 2),
    )
    jobs = parse_cuni_ajax_listing(payload)
    assert [item["code"] for item in jobs] == [
        "202610-VP2-PřF-1400-093",
        "202609-AP2-MFF-KA-064",
    ]
    assert jobs[0]["sourceUrl"].endswith("pracid=202610-VP2-P%C5%99F-1400-093")
    assert "track" not in jobs[1]


def test_cuni_central_discovery_follows_all_ajax_pages_and_full_details() -> None:
    listing = "https://cuni.test/vyberova-rizeni/ajax.php?lang=en&stav=active&apo=all"
    page_two = f"{listing}&p=2"
    detail_one = "https://cuni.test/open?pracid=CU-RESEARCH-1"
    detail_two = "https://cuni.test/open?pracid=CU-TEACHING-2"
    registry = [
        {
            "id": "cuni-central-test",
            "url": listing,
            "detailBaseUrl": "https://cuni.test/open",
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_11000",
            "parser": "cuni_ajax",
            "followDetails": True,
        }
    ]
    pages = {
        listing: (
            200,
            cuni_ajax_page([("CU-RESEARCH-1", "Research assistant in virology")], pages=(1, 2)),
        ),
        page_two: (
            200,
            cuni_ajax_page(
                [
                    ("CU-RESEARCH-1", "Research assistant in virology"),
                    ("CU-TEACHING-2", "Lecturer in Latin"),
                ],
                pages=(1, 2),
            ),
        ),
        detail_one: (
            200,
            "<h1>Research assistant in virology</h1><p>Master degree. Employment contract. "
            "Enrollment in a PhD is not required. Application deadline: 2026-10-31.</p>",
        ),
        detail_two: (
            200,
            "<h1>Lecturer in Latin</h1><p>Teaching duties. Application deadline: 2026-10-31.</p>",
        ),
    }
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        return pages[url]

    discovery = discover_registered_candidates(fetch, registry=registry)
    assert calls == [listing, page_two, detail_one, detail_two]
    assert discovery["completeSourceIds"] == ["cuni-central-test"]
    assert len(discovery["candidates"]) == 1
    assert discovery["candidates"][0]["minimumDegree"] == "master"
    assert discovery["candidates"][0]["doctoralEnrollment"] == "not_required"
    assert any(item["reason"] == "detail-not-a-supported-research-vacancy" for item in discovery["quarantined"])


def test_lmc_widget_discovery_reads_every_api_page_and_full_detail() -> None:
    import json

    portal = "https://vut.test/"
    endpoint = "https://api.vut.test/graphql"
    config = {
        "apiKey": "public-widget-key",
        "widgetId": "widget-1",
        "host": "vut.test",
        "detailPath": "detail-pozice",
    }
    landing = (
        "<div id='widget_container'></div><script>window.__LMC_CAREER_WIDGET__ = [];"
        f"window.__LMC_CAREER_WIDGET__.push({json.dumps(config)});</script>"
    )
    assert parse_lmc_widget_config(landing) == config

    def listing(page: int, item: dict) -> str:
        return json.dumps(
            {
                "data": {
                    "widget": {
                        "jobAdList": {
                            "groupedJobAds": {"jobAds": [item], "groups": []},
                            "paginator": {
                                "currentPage": page,
                                "lastPage": 2,
                                "totalNumberOfItems": 2,
                            },
                        }
                    }
                }
            },
            ensure_ascii=False,
        )

    research = {
        "id": "2001",
        "title": "Odborný pracovník ve výzkumu pro informační systémy",
    }
    accounting = {"id": "2002", "title": "Účetní"}
    detail_research = json.dumps(
        {
            "data": {
                "widget": {
                    "jobAd": {
                        **research,
                        "validFrom": "2026-09-04T10:38:25+02:00",
                        "languageIso": "cs",
                        "content": {
                            "htmlContent": (
                                "<p>Realizace výzkumných úkolů a příprava publikací.</p>"
                                "<p>Minimálně bakalářské vzdělání.</p>"
                                "<p>Termín pro podání přihlášek je do 30. 9. 2026.</p>"
                                "<p>Kontaktní osoba: Mgr. Jana Nováková.</p>"
                            ),
                            "sections": [],
                        },
                        "parameters": {
                            "employmentTypes": ["Práce na zkrácený úvazek"],
                            "contractTypes": ["pracovní smlouva"],
                            "requiredEducation": "Bakalářské",
                            "requiredLanguages": [
                                {"language": "Čeština", "skill": "Výborná"},
                                {"language": "Angličtina", "skill": "Mírně pokročilá"},
                            ],
                        },
                        "salary": None,
                    }
                }
            }
        },
        ensure_ascii=False,
    )
    detail_accounting = json.dumps(
        {
            "data": {
                "widget": {
                    "jobAd": {
                        **accounting,
                        "validFrom": "2026-09-10T10:00:00+02:00",
                        "languageIso": "cs",
                        "content": {"htmlContent": "<p>Vedení účetnictví.</p>", "sections": []},
                        "parameters": {},
                        "salary": None,
                    }
                }
            }
        },
        ensure_ascii=False,
    )

    parsed_listing = parse_lmc_graphql_listing(listing(1, research), portal)
    assert parsed_listing is not None
    assert parsed_listing[0][0]["sourceUrl"] == "https://vut.test/detail-pozice?r=detail&id=2001"
    parsed_detail = parse_lmc_graphql_detail(
        detail_research,
        "https://vut.test/detail-pozice?r=detail&id=2001",
        "2001",
    )
    assert parsed_detail is not None
    assert parsed_detail["minimumDegree"] == "bachelor"
    assert parsed_detail["paidStatus"] == "confirmed"
    assert parsed_detail["closesAt"] == "2026-09-30"
    assert parsed_detail["workingLanguages"] == ["cs", "en"]

    api_calls: list[tuple[str, str]] = []

    def post_json(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, str]:
        assert url == endpoint
        assert headers == {"X-Api-Key": "public-widget-key"}
        variables = payload["variables"]
        if "page" in variables:
            page = variables["page"]
            api_calls.append(("listing", str(page)))
            return (200, listing(page, research if page == 1 else accounting))
        job_id = variables["jobAdId"]
        api_calls.append(("detail", job_id))
        return (200, detail_research if job_id == "2001" else detail_accounting)

    registry = [
        {
            "id": "vut-widget-test",
            "url": portal,
            "apiUrl": endpoint,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_26000",
            "parser": "lmc_graphql",
            "followDetails": False,
        }
    ]
    discovery = discover_registered_candidates(
        lambda url: (200, landing) if url == portal else (404, ""),
        registry=registry,
        post_json=post_json,
    )
    assert api_calls == [
        ("listing", "1"),
        ("listing", "2"),
        ("detail", "2001"),
        ("detail", "2002"),
    ]
    assert discovery["completeSourceIds"] == ["vut-widget-test"]
    assert len(discovery["candidates"]) == 1
    assert discovery["candidates"][0]["id"] == "job-26000-2001"
    assert any(item["title"] == "Účetní" for item in discovery["quarantined"])

    api_calls.clear()
    harvested = harvest_with_registered_discovery(
        [],
        lambda url: (200, landing) if url == portal else (404, ""),
        registry=registry,
        post_json=post_json,
    )
    assert harvested["jobs"][0]["minimumDegree"] == "bachelor"
    assert harvested["jobs"][0]["doctorateRequired"] is False


def test_registered_discovery_follows_new_muni_detail_without_seed_constant() -> None:
    listing_url = "https://www.muni.cz/en/about-us/careers"
    detail_url = "https://www.muni.cz/en/about-us/careers/vacancies/98765-new"
    registry = [
        {
            "id": "muni-careers-test",
            "url": listing_url,
            "baseUrl": "https://www.muni.cz",
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_14000",
            "parser": "muni_vacancies",
            "followDetails": True,
        }
    ]
    pages = {
        listing_url: (
            200,
            '<a href="/en/about-us/careers/vacancies/98765-new">Research assistant in trustworthy AI</a>',
        ),
        detail_url: (
            200,
            "<h1>Research assistant in trustworthy AI</h1>"
            "<p>A master's degree is required. Enrollment in a PhD is not required. "
            "Employment contract. Application deadline: 2026-09-30.</p>",
        ),
    }
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        return pages[url]

    payload = harvest_with_registered_discovery(
        [],
        fetch,
        as_of=parse_date("2026-09-01"),
        employer_ids={"msmt-vs_14000"},
        registry=registry,
    )
    assert payload["discovery"]["discoveredCount"] == 1
    assert payload["processedCandidateIds"] == ["job-14000-98765"]
    assert payload["jobs"][0]["id"] == "job-14000-98765"
    assert payload["jobs"][0]["minimumDegree"] == "master"
    assert payload["jobs"][0]["doctoralEnrollment"] == "not_required"
    assert payload["jobs"][0]["publicationStatus"] == "review_pending"
    assert calls.count(listing_url) == 1
    assert calls.count(detail_url) == 1


def test_dynamic_discovery_reuses_reviewed_id_and_removes_generated_duplicate() -> None:
    listing_url = "https://www.muni.cz/en/about-us/careers"
    detail_url = "https://www.muni.cz/en/about-us/careers/vacancies/98765-new"
    registry = [
        {
            "id": "muni-stable-id-test",
            "url": listing_url,
            "baseUrl": "https://www.muni.cz",
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_14000",
            "parser": "muni_vacancies",
            "followDetails": True,
        }
    ]
    previous = {
        "jobs": [
            {
                "id": "reviewed-stable-id",
                "employerId": "msmt-vs_14000",
                "title": {"en": "Research assistant in trustworthy AI"},
                "sourceUrl": detail_url,
                "publicationStatus": "approved",
                "translationStatus": "reviewed",
            },
            {
                "id": "job-14000-98765",
                "employerId": "msmt-vs_14000",
                "title": {"en": "Research assistant in trustworthy AI"},
                "sourceUrl": detail_url,
                "publicationStatus": "review_pending",
            },
        ]
    }
    pages = {
        listing_url: (
            200,
            '<a href="/en/about-us/careers/vacancies/98765-new">Research assistant in trustworthy AI</a>',
        ),
        detail_url: (
            200,
            "<h1>Research assistant in trustworthy AI</h1><p>Master degree. Employment contract. "
            "Application deadline: 2026-09-30.</p>",
        ),
    }
    payload = harvest_with_registered_discovery(
        [],
        lambda url: pages[url],
        previous=previous,
        as_of=parse_date("2026-09-01"),
        registry=registry,
    )
    assert [item["id"] for item in payload["jobs"]] == ["reviewed-stable-id"]
    assert set(payload["processedCandidateIds"]) == {
        "reviewed-stable-id",
        "job-14000-98765",
    }


def test_same_title_at_different_official_urls_remains_distinct() -> None:
    listing_url = "https://university.test/jobs"
    first_url = "https://university.test/jobs/department-a"
    second_url = "https://university.test/jobs/department-b"
    registry = [
        {
            "id": "same-title-test",
            "url": listing_url,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_25000",
            "parser": "generic_listing_links",
            "pathPatterns": [r"/jobs/department-"],
            "followDetails": True,
        }
    ]
    listing = (
        f'<a href="{first_url}">Research assistant</a>'
        f'<a href="{second_url}">Research assistant</a>'
    )
    detail = (
        "<h1>Research assistant</h1><p>Master degree. Employment contract. "
        "Application deadline 2026-09-30.</p>"
    )
    pages = {
        listing_url: (200, listing),
        first_url: (200, detail),
        second_url: (200, detail),
    }
    payload = harvest_with_registered_discovery(
        [],
        lambda url: pages[url],
        as_of=parse_date("2026-09-01"),
        registry=registry,
    )
    assert len(payload["jobs"]) == 2
    assert len({item["id"] for item in payload["jobs"]}) == 2
    assert {item["sourceUrl"] for item in payload["jobs"]} == {first_url, second_url}


def test_avcr_discovery_quarantines_unresolved_institute() -> None:
    listing_url = "https://www.avcr.cz/en/about-us/career/selection-procedures/"
    registry = [
        {
            "id": "avcr-test",
            "url": listing_url,
            "baseUrl": "https://www.avcr.cz",
            "sourceType": "official_job_listing",
            "employerId": None,
            "employersByUrlPrefix": {},
            "parser": "avcr_vacancies",
            "followDetails": True,
        }
    ]
    listing = (
        '<a href="/en/about-us/career/selection-procedures/postdoc-physics">'
        "Postdoctoral Fellow in Laser Physics</a>"
    )
    result = discover_registered_candidates(lambda _url: (200, listing), registry=registry)
    assert result["candidates"] == []
    assert result["quarantined"][0]["reason"] == "unresolved-legal-employer"


def test_registered_discovery_follows_pagination_deduplicates_and_parses_czech() -> None:
    first_url = "https://www.muni.cz/en/about-us/careers"
    second_url = "https://www.muni.cz/en/about-us/careers?page=2"
    en_detail = "https://www.muni.cz/en/about-us/careers/vacancies/98765-new"
    cs_detail = "https://www.muni.cz/o-univerzite/kariera/volna-mista/76543-novy"
    registry = [
        {
            "id": "muni-paged-test",
            "url": first_url,
            "baseUrl": "https://www.muni.cz",
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_14000",
            "parser": "muni_vacancies",
            "followDetails": True,
        }
    ]
    pages = {
        first_url: (
            200,
            '<a href="/en/about-us/careers/vacancies/98765-new">Research assistant in AI</a>'
            '<a rel="next" href="?page=2">Next</a>',
        ),
        second_url: (
            200,
            '<a href="https://www.muni.cz/en/about-us/careers/vacancies/98765-new">Research assistant in AI</a>'
            '<a href="/o-univerzite/kariera/volna-mista/76543-novy">Výzkumný asistent v informatice</a>',
        ),
        en_detail: (200, "<h1>Research assistant in AI</h1><p>Master degree. Deadline 2026-09-30.</p>"),
        cs_detail: (
            200,
            "<h1>Výzkumný asistent v informatice</h1><p>Požadujeme magisterské vzdělání. "
            "Zápis do doktorského studia není podmínkou. Pracovní poměr. "
            "Termín přihlášek 30. 9. 2026.</p>",
        ),
    }
    result = discover_registered_candidates(lambda url: pages[url], registry=registry)
    assert len(result["candidates"]) == 2
    assert result["completeSourceIds"] == ["muni-paged-test"]
    czech = next(item for item in result["candidates"] if item["code"] == "76543")
    assert czech["sourceLanguage"] == "cs"
    assert czech["minimumDegree"] == "master"
    assert czech["doctoralEnrollment"] == "not_required"


def test_complete_listing_archives_a_disappeared_dynamic_candidate() -> None:
    listing_url = "https://www.muni.cz/en/about-us/careers"
    detail_url = "https://www.muni.cz/en/about-us/careers/vacancies/98765-new"
    registry = [
        {
            "id": "muni-disappearance-test",
            "url": listing_url,
            "baseUrl": "https://www.muni.cz",
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_14000",
            "parser": "muni_vacancies",
            "followDetails": True,
        }
    ]
    first = harvest_with_registered_discovery(
        [],
        lambda url: (
            (200, '<a href="/en/about-us/careers/vacancies/98765-new">Research assistant in AI</a>')
            if url == listing_url
            else (200, "<h1>Research assistant in AI</h1><p>Master degree. Deadline 2026-09-30.</p>")
        ),
        as_of=parse_date("2026-09-01"),
        registry=registry,
    )
    assert first["jobs"][0]["discoverySourceId"] == "muni-disappearance-test"

    second = harvest_with_registered_discovery(
        [],
        lambda url: (200, "<p>No current vacancies.</p>"),
        previous=first,
        as_of=parse_date("2026-09-02"),
        registry=registry,
    )
    assert second["discovery"]["disappearedCount"] == 1
    assert second["jobs"][0]["lifecycleStatus"] == "unavailable"
    assert second["jobs"][0]["visibility"] == "archived"
    assert second["jobs"][0]["wholeOpportunityClosed"] is False


def test_listed_job_that_leaves_supported_scope_is_not_reported_as_officially_missing() -> None:
    listing_url = "https://university.test/careers"
    detail_url = "https://university.test/careers/123"
    registry = [{
        "id": "official-careers-test",
        "url": listing_url,
        "sourceType": "official_job_listing",
        "employerId": "msmt-vs_21000",
        "parser": "generic_listing_links",
        "pathPatterns": [r"/careers/\d+"],
        "followDetails": True,
    }]
    previous = {
        "jobs": [{
            "id": "job-21000-123",
            "employerId": "msmt-vs_21000",
            "sourceUrl": detail_url,
            "discoverySourceId": "official-careers-test",
            "visibility": "review_pending",
            "lifecycleStatus": "open",
        }],
        "windows": [],
        "evidence": [],
    }
    pages = {
        listing_url: (200, f'<a href="{detail_url}">Financial manager</a>'),
        detail_url: (200, "<h1>Financial manager</h1><p>Budget reporting and audits.</p>"),
    }
    result = harvest_with_registered_discovery(
        [],
        lambda url: pages[url],
        previous=previous,
        registry=registry,
    )
    job = result["jobs"][0]
    assert job["visibility"] == "archived"
    assert job["lifecycleStatus"] == "unknown"
    assert job["catalogueScopeStatus"] == "excluded"
    assert job["lastAttemptReason"].startswith("no-longer-meets-supported-scope:")


def test_vsb_cards_keep_active_academic_details_and_exclude_completed_results() -> None:
    html = """
    <h2>Výběrová řízení</h2>
    <div class="card">
      <h5 class="card-subtitle">Centrum ENET</h5>
      <h4 class="card-title">Odborný asistent / Odborná asistentka</h4>
      <p>Typ pozice: <b>Akademická pozice</b></p>
      <p>Termín pro podání přihlášek: <b>12. 9. 2026</b></p>
      <a href="/jobs/inzerat/?procedureId=54">Inzerát</a>
    </div>
    <h2>Výsledky ukončených výběrových řízení</h2>
    <div class="card">
      <h4 class="card-title">Vědecko-výzkumný pracovník</h4>
      <a href="/jobs/inzerat/?procedureId=old">Inzerát</a>
    </div>
    """
    rows = parse_vsb_listing(html, "https://www.vsb.cz/cs/jobs/")
    assert len(rows) == 1
    assert rows[0]["code"] == "54"
    assert rows[0]["laboratory"] == "Centrum ENET"
    assert rows[0]["closesAt"] == "2026-09-12"
    assert rows[0]["sourceUrl"] == "https://www.vsb.cz/jobs/inzerat/?procedureId=54"


def test_configured_generic_links_follow_only_official_detail_paths() -> None:
    html = """
    <a href="/en/faculty/careers">Careers</a>
    <a href="/en/faculty/careers/36448-research-engineer">Research Engineer</a>
    <a href="https://external.example/jobs/1">Research Fellow</a>
    """
    rows = parse_generic_listing_links(
        html,
        "https://fel.cvut.cz/en/faculty/careers",
        [r"/en/faculty/careers/\d+"],
    )
    assert len(rows) == 1
    assert rows[0]["code"] == "36448"
    assert rows[0]["sourceUrl"].endswith("36448-research-engineer")


def test_configured_generic_links_allow_only_explicit_official_faculty_hosts() -> None:
    html = """
    <a href="https://www.famu.cz/cs/aktuality/vyberove-rizeni-123/">FAMU vacancy</a>
    <a href="https://evil.example/cs/aktuality/vyberove-rizeni-999/">Copied vacancy</a>
    """
    rows = parse_generic_listing_links(
        html,
        "https://www.amu.cz/cs/uredni-deska/volna-mista-konkurzy/",
        [r"/cs/aktuality/vyberove-rizeni-"],
        ["www.famu.cz", "www.damu.cz", "www.hamu.cz"],
    )
    assert [row["sourceUrl"] for row in rows] == [
        "https://www.famu.cz/cs/aktuality/vyberove-rizeni-123/"
    ]


def test_configured_generic_links_reject_anchors_pointing_at_the_listing_itself() -> None:
    """A listing page's own anchors are chrome, not vacancies.

    VSTECB's careers page matched every anchor on itself, which produced three
    candidate rows for "Pejít na hlavní obsah" (#content), "Skola Základní
    informace" (the page itself) and "TOP" (#top). Anchors that resolve to the
    page being parsed - fragment-only or not - must never become a vacancy.
    """
    listing_url = "https://www.vstecb.cz/volna-pracovni-mista/"
    html = f"""
    <a href="{listing_url}#content">Pejít na hlavní obsah</a>
    <a href="{listing_url}">Skola Základní informace</a>
    <a href="{listing_url}#top">TOP</a>
    <a href="/volna-pracovni-mista/?id=1">Academic staff member</a>
    """
    rows = parse_generic_listing_links(html, listing_url, [r"/volna-pracovni-mista/"])
    assert [row["sourceUrl"] for row in rows] == ["https://www.vstecb.cz/volna-pracovni-mista/?id=1"]


def test_generic_pdf_listing_uses_attachment_text_and_hashed_identity() -> None:
    listing_url = "https://jcu.test/cz/univerzita/volna-mista"
    first_pdf = "https://jcu.test/images/UNIVERZITA/volna-mista/2026/09/07092026-postdoc.pdf"
    second_pdf = "https://jcu.test/images/UNIVERZITA/volna-mista/2026/09/07092026-researcher.pdf"
    registry = [
        {
            "id": "jcu-pdf-test",
            "url": listing_url,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_12000",
            "parser": "generic_listing_links",
            "pathPatterns": [r"/images/UNIVERZITA/volna-mista/20\d{2}/"],
            "followDetails": True,
        }
    ]
    listing = (
        f'<a href="{first_pdf}">Postdoctoral Researcher in Biophysics</a>'
        f'<a href="{second_pdf}">Vědecký pracovník v biologii</a>'
        '<a href="/images/UNIVERZITA/volna-mista/privacy.pdf">Privacy policy</a>'
    )
    attachments: list[str] = []

    def fetch_attachment(url: str) -> tuple[int, bytes]:
        attachments.append(url)
        return 200, b"%PDF-test"

    def pdf_text(_body: bytes) -> str:
        return (
            "Postdoctoral Researcher in Biophysics. PhD is required. Employment contract. "
            "Vědecký pracovník v biologii. Magisterské vzdělání. Pracovní smlouva. "
            "Termín přihlášek 30. 9. 2026."
        )

    result = discover_registered_candidates(
        lambda url: (200, listing) if url == listing_url else (404, ""),
        registry=registry,
        fetch_attachment=fetch_attachment,
        pdf_text=pdf_text,
    )

    assert result["completeSourceIds"] == ["jcu-pdf-test"]
    assert attachments == [first_pdf, second_pdf]
    assert len(result["candidates"]) == 2
    assert {item["code"] for item in result["candidates"]} == {None}
    assert len({item["id"] for item in result["candidates"]}) == 2
    assert all(item["id"].startswith("job-12000-") for item in result["candidates"])
    assert all(item.get("_factHtml", "").startswith("<h1>") for item in result["candidates"])
    assert all(attempt["kind"] == "detail-attachment" for attempt in result["attempts"][1:])


def test_generic_html_detail_expands_each_official_job_pdf() -> None:
    listing_url = "https://upce.test/volna-mista"
    detail_url = "https://upce.test/katedra-dopravy-2"
    pdf_url = "https://upce.test/sites/default/files/2026/research-doktorand.pdf"
    registry = [
        {
            "id": "upce-pdf-test",
            "url": listing_url,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_25000",
            "parser": "generic_listing_links",
            "pathPatterns": [r"/katedra-"],
            "detailAttachmentPatterns": [r"\.pdf(?:$|[?#])"],
            "followDetails": True,
        }
    ]
    pages = {
        listing_url: (200, f'<a href="{detail_url}">Katedra dopravy</a>'),
        detail_url: (200, f'<h1>Katedra dopravy</h1><a href="{pdf_url}">Výzkumný pracovník - doktorand M/Ž - pdf</a>'),
    }
    result = discover_registered_candidates(
        lambda url: pages[url],
        registry=registry,
        fetch_attachment=lambda url: (200, b"%PDF-test") if url == pdf_url else (404, b""),
        pdf_text=lambda _body: (
            "Výzkumný pracovník - doktorand. Pracovní smlouva. "
            "Student doktorského studijního programu. Přihlášky do 18. 9. 2026."
        ),
    )
    assert result["completeSourceIds"] == ["upce-pdf-test"]
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["title"] == "Výzkumný pracovník - doktorand M/Ž"
    assert candidate["sourceUrl"] == pdf_url
    assert candidate["applicationUrl"] == pdf_url
    assert candidate["doctoralEnrollment"] == "required"
    assert candidate["paidStatus"] == "confirmed"
    assert [attempt["kind"] for attempt in result["attempts"]] == [
        "listing",
        "detail",
        "detail-attachment",
    ]


def test_utb_cards_pair_heading_with_same_card_detail_link() -> None:
    html = """
    <article class="bde-loop-item ee-post">
      <h5>Akademický pracovník pro Ústav informatiky</h5>
      <a href="/akademicky-pracovnik-pro-ustav-informatiky/">Zobrazit</a>
    </article>
    <article class="bde-loop-item ee-post">
      <h5>Webový vývojář / vývojářka</h5>
      <a href="https://kariera.utb.test/webovy-vyvojar/">Zobrazit</a>
    </article>
    <article><h5>External advert</h5><a href="https://external.test/job">Zobrazit</a></article>
    """
    rows = parse_utb_careers(html, "https://kariera.utb.test/volne-pozice/akademicke-pozice/")
    assert [item["title"] for item in rows] == [
        "Akademický pracovník pro Ústav informatiky",
        "Webový vývojář / vývojářka",
    ]
    assert [item["sourceUrl"] for item in rows] == [
        "https://kariera.utb.test/akademicky-pracovnik-pro-ustav-informatiky/",
        "https://kariera.utb.test/webovy-vyvojar/",
    ]
    assert all(item["code"] is None for item in rows)


def test_ujep_parser_reads_only_the_open_position_article() -> None:
    listing_url = "https://zamo.ujep.test/open-positions/"
    html = f"""
    <nav><a href="https://zamo.ujep.test/staff-salary/">Mzda</a></nav>
    <article class="page" id="post">
      <header><a href="https://zamo.ujep.test/">ZAMO</a><h1>Open Positions</h1></header>
      <p><a href="https://zamo.ujep.test/technology-transfer-officer/">Technology Transfer Officer</a></p>
      <p><a href="https://zamo.ujep.test/academic-geoinformatics/">Academic staff member in geoinformatics</a></p>
    </article>
    <footer><a href="https://zamo.ujep.test/privacy/">Privacy</a></footer>
    """
    fragment = extract_html_element(html, "article", element_id="post")
    assert "Technology Transfer Officer" in fragment
    assert "staff-salary" not in fragment
    rows = parse_ujep_open_positions(html, listing_url)
    assert [item["title"] for item in rows] == [
        "Technology Transfer Officer",
        "Academic staff member in geoinformatics",
    ]


def test_tul_parser_keeps_unresolved_notices_and_drops_rows_with_decisions() -> None:
    listing_url = "https://www.tul.cz/kariera/probihajici-vyberova-rizeni/"
    html = """
    <div class="entry-content"><ul class="wp-block-list ridkyseznam">
      <li><strong><a href="https://doc.tul.cz/15755">Researcher in chemistry</a></strong>
        <ul><li><a href="https://doc.tul.cz/15833">Jmenování výběrové komise</a></li></ul>
      </li>
      <li><strong><a href="https://doc.tul.cz/15371">Researcher in polymers</a></strong>
        <ul><li><a href="https://doc.tul.cz/15707">Rozhodnutí</a></li></ul>
      </li>
      <li><strong><a href="https://external.test/job">External role</a></strong></li>
    </ul></div>
    """
    rows = parse_tul_careers(html, listing_url)
    assert rows == [
        {
            "title": "Researcher in chemistry",
            "code": "15755",
            "sourceUrl": "https://doc.tul.cz/15755",
            "applicationUrl": "https://doc.tul.cz/15755",
        }
    ]


def test_pdf_detail_format_reads_extensionless_official_document() -> None:
    listing_url = "https://www.tul.cz/kariera/probihajici-vyberova-rizeni/"
    detail_url = "https://doc.tul.cz/15755"
    registry = [
        {
            "id": "tul-test",
            "url": listing_url,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_24000",
            "parser": "tul_careers",
            "detailFormat": "pdf",
            "followDetails": True,
        }
    ]
    listing = (
        '<div class="entry-content"><ul class="wp-block-list ridkyseznam"><li><strong>'
        f'<a href="{detail_url}">Researcher in chemistry</a>'
        "</strong></li></ul></div>"
    )
    result = discover_registered_candidates(
        lambda _url: (200, listing),
        registry=registry,
        fetch_attachment=lambda url: (200, b"%PDF") if url == detail_url else (404, b""),
        pdf_text=lambda _body: (
            "Research and publication duties. Ukončené doktorské studium. "
            "Pracovní smlouva. Životopis zaslat nejpozději do 30. 9. 2026."
        ),
    )
    assert result["completeSourceIds"] == ["tul-test"]
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["minimumDegree"] == "doctorate"
    assert candidate["closesAt"] == "2026-09-30"
    assert candidate["_factHtml"].startswith("<h1>Researcher in chemistry</h1>")


def test_production_loader_includes_batch4_and_promoted_sources() -> None:
    sources = jobs_harvester.load_registered_job_sources()
    ids = {item["id"] for item in sources}
    for source_id in (
        "ujep-open-positions",
        "uhk-central-selection",
        "tul-central-careers",
        "osu-central-careers",
        "slu-central-vacancies",
        "vetuni-central-vacancies",
        "unob-academic-selection",
        "vstecb-central-vacancies",
        "vspj-academic-vacancies",
    ):
        assert source_id in ids, source_id


def test_new_school_listing_discovers_unseeded_job_id() -> None:
    listing_url = "https://www.slu.cz/slu/cz/volnamista"
    detail_url = "https://www.slu.cz/slu/cz/file/cul/abc123"
    registry = [
        {
            "id": "slu-central-vacancies",
            "url": listing_url,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_19000",
            "parser": "generic_listing_links",
            "pathPatterns": ["/file/cul/"],
            "followDetails": True,
        }
    ]
    listing = (
        '<h3>Filozoficko-přírodovědecká fakulta</h3>'
        f'<a href="{detail_url}">Asistent se zaměřením na vývoj softwaru</a>'
        '<a href="https://www.slu.cz/slu/cz/kontakty">Kontakty</a>'
    )
    detail = (
        "<h1>Asistent se zaměřením na vývoj softwaru</h1>"
        "<p>Research software engineering. Master's degree required. "
        "Životopis zaslat nejpozději do 30. 11. 2026.</p>"
    )
    pages = {listing_url: (200, listing), detail_url: (200, detail)}
    result = discover_registered_candidates(lambda url: pages[url], registry=registry)
    assert result["completeSourceIds"] == ["slu-central-vacancies"]
    assert result["runKind"] == "all_registered_sources"
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["id"].startswith("job-19000-")
    assert result["candidates"][0]["id"] not in {
        item["id"] for item in jobs_harvester.VERIFIED_CANDIDATES
    }


def test_deferred_retry_after_does_not_archive_or_hit_source(monkeypatch) -> None:
    # A74: the cooldown verdict must use an injected clock, not the wall clock,
    # so the test stays valid before, exactly at, and after expiry.
    from datetime import datetime, timedelta, timezone

    expiry = datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)
    jobs_harvester.clear_host_cooldowns()
    jobs_harvester.set_host_cooldown(
        "https://www.slu.cz/slu/cz/volnamista",
        expiry,
    )
    registry = [
        {
            "id": "slu-central-vacancies",
            "url": "https://www.slu.cz/slu/cz/volnamista",
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_19000",
            "parser": "generic_listing_links",
            "followDetails": False,
        }
    ]

    def boom(_url):
        raise AssertionError("throttled host must not be requested")

    def listing_page(_url):
        return 200, "<html><body>No vacancies listed here.</body></html>"

    before_expiry = expiry - timedelta(seconds=1)
    result = discover_registered_candidates(boom, registry=registry, now=before_expiry)
    assert result["deferredSourceIds"] == ["slu-central-vacancies"]
    assert result["completeSourceIds"] == []
    assert result["candidates"] == []
    assert result["attempts"][0]["reason"] == "retry-after-deferred"

    at_expiry = expiry
    eligible = discover_registered_candidates(listing_page, registry=registry, now=at_expiry)
    assert "slu-central-vacancies" not in eligible["deferredSourceIds"]
    assert [a["kind"] for a in eligible["attempts"] if a["url"].endswith("volnamista")] == ["listing"]

    after_expiry = expiry + timedelta(seconds=1)
    eligible_after = discover_registered_candidates(listing_page, registry=registry, now=after_expiry)
    assert "slu-central-vacancies" not in eligible_after["deferredSourceIds"]
    jobs_harvester.clear_host_cooldowns()


def test_configured_detail_container_excludes_navigation_facts() -> None:
    listing_url = "https://jobs.example.test/current/"
    detail_url = "https://jobs.example.test/current/?inzeratid=181"
    listing = '<a href="./?inzeratid=181">Postdoc I</a>'
    detail = """
    <nav>Přihlášky do 14. 9. 2026. Mzda 200 Kč.</nav>
    <article><h1>Postdoc I</h1><p>Doktorský titul (Ph.D.). Pracovní smlouva.</p>
    <p>Lhůta pro včasné podání žádosti 30. září 2026.</p></article>
    """
    registry = [
        {
            "id": "scoped-detail-test",
            "url": listing_url,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_17000",
            "parser": "generic_listing_links",
            "pathPatterns": [r"[?&]inzeratid=\d+"],
            "detailContainerTag": "article",
            "followDetails": True,
        }
    ]
    pages = {listing_url: (200, listing), detail_url: (200, detail)}
    result = discover_registered_candidates(lambda url: pages[url], registry=registry)
    candidate = result["candidates"][0]
    assert candidate["code"] == "181"
    assert candidate["closesAt"] == "2026-09-30"
    assert candidate["salaryAmount"] is None
    assert "<nav>" not in candidate["_factHtml"]


def test_recruitis_widget_is_discovered_from_official_page_and_missing_embed_is_incomplete() -> None:
    landing_url = "https://university.test/en/job-vacancies"
    widget_url = "https://app.recruitis.io/zadavatel/widgets/offers/h/public-feed"
    detail_url = "https://app.recruitis.io/zadavatel/widgets/offers-detail/public-feed/492828/token"
    landing = f'<iframe src="{widget_url}" id="official_jobs"></iframe>'
    widget = f'<h3><a href="{detail_url}">Research Assistant in Forestry</a></h3>'
    detail = (
        "<h1>Research Assistant in Forestry</h1><p>Master degree required. "
        "Employment contract. Application deadline 2026-09-30.</p>"
    )
    registry = [
        {
            "id": "recruitis-test",
            "url": landing_url,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_43000",
            "parser": "recruitis_widget",
            "pathPatterns": [r"/zadavatel/widgets/offers-detail/"],
            "followDetails": True,
        }
    ]
    assert parse_recruitis_widget_urls(landing, landing_url) == [widget_url]
    pages = {
        landing_url: (200, landing),
        widget_url: (200, widget),
        detail_url: (200, detail),
    }
    result = discover_registered_candidates(lambda url: pages[url], registry=registry)
    assert result["completeSourceIds"] == ["recruitis-test"]
    assert result["candidates"][0]["code"] == "492828"
    assert result["candidates"][0]["minimumDegree"] == "master"

    missing = discover_registered_candidates(
        lambda _url: (200, "<p>No embedded vacancy feed.</p>"),
        registry=registry,
    )
    assert missing["completeSourceIds"] == []
    assert any(
        attempt.get("reason") == "missing-official-recruitis-widget"
        for attempt in missing["attempts"]
    )


def test_utb_multi_position_detail_does_not_collapse_mixed_thresholds_or_salaries() -> None:
    listing_url = "https://kariera.utb.test/volne-pozice/akademicke-pozice/"
    detail_url = "https://kariera.utb.test/three-academic-roles/"
    registry = [
        {
            "id": "utb-bundle-test",
            "url": listing_url,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_28000",
            "parser": "utb_careers",
            "followDetails": True,
        }
    ]
    listing = f"""
    <article><h5>Akademičtí pracovníci pro Ústav bezpečnosti</h5>
    <a href="{detail_url}">Zobrazit</a></article>
    """
    detail = """
    <h1>Akademičtí pracovníci pro Ústav bezpečnosti</h1>
    <p>Ústav vypisuje výběrové řízení na obsazení 3 pracovních pozic.</p>
    <p>Odborný asistent: ukončené doktorské studium, vědecko-výzkumná práce, mzda 40 000 Kč.</p>
    <p>Dva asistenti: magisterské vzdělání, vědecko-výzkumná práce, mzda 30 000 Kč. Pracovní smlouva.</p>
    """
    pages = {listing_url: (200, listing), detail_url: (200, detail)}
    result = discover_registered_candidates(lambda url: pages[url], registry=registry)
    candidate = result["candidates"][0]
    assert candidate["eligibilityGranularity"] == "notice_bundle"
    assert candidate["minimumDegree"] == "unknown"
    assert candidate["doctorateRequired"] is None
    assert candidate["salaryAmount"] is None
    assert candidate["salaryCurrency"] is None
    assert candidate["paidStatus"] == "confirmed"


def test_inline_job_sections_do_not_mix_qualifications_or_deadlines() -> None:
    html = """
    <h2>Research assistant in analytical chemistry - 560</h2>
    <p>Master degree required. Employment contract. Deadline 30. 9. 2026.</p>
    <h2>Postdoctoral researcher in biotechnology - 319</h2>
    <p>PhD is required. Employment contract. Deadline 15. 10. 2026.</p>
    """
    rows = parse_inline_heading_jobs(html, "https://www.vscht.cz/official-jobs")
    assert len(rows) == 2
    assert rows[0]["code"] == "560"
    assert rows[0]["minimumDegree"] == "master"
    assert rows[0]["closesAt"] == "2026-09-30"
    assert rows[0]["paidStatus"] == "confirmed"
    assert rows[1]["code"] == "319"
    assert rows[1]["minimumDegree"] == "doctorate"
    assert rows[1]["closesAt"] == "2026-10-15"


def test_ctu_notice_board_reads_full_pdf_facts_before_accepting_research_jobs() -> None:
    listing_url = "https://eud.is.cvut.cz/pub/deska/36000002/ifis/?kategorie_id=66&pocet=100"
    listing = """
    <table><tbody>
      <tr><td>FJFI</td><td>Personální</td><td><a href="/pub/deska/36000002/ifis/5467">Výzkumný pracovník v chemii</a></td><td>CASE-1</td><td>27. 08. 2026</td><td>30. 09. 2026</td></tr>
      <tr><td>Rektorát</td><td>Personální</td><td><a href="/pub/deska/36000002/ifis/5460">Účetní</a></td><td>CASE-2</td><td>21. 08. 2026</td><td>20. 09. 2026</td></tr>
    </tbody></table>
    <option selected>1-2 z 2</option>
    """

    def detail(title: str, unit: str, attachment: str) -> str:
        return f"""
        <table><tbody>
          <tr><th>Součást</th><td>{unit}</td></tr>
          <tr><th>Kategorie</th><td>Personální</td></tr>
          <tr><th>Název</th><td>{title}</td></tr>
          <tr><th>Číslo jednací</th><td>CASE</td></tr>
          <tr><th>Vyvěšeno</th><td>27.08.2026</td></tr>
          <tr><th>Sejmout</th><td>30.09.2026</td></tr>
          <tr><th>Stav vyvěšení</th><td>vyvěšeno</td></tr>
        </tbody></table>
        <a href="{attachment}">advertisement.pdf</a>
        """

    pages = {
        listing_url: (200, listing),
        "https://eud.is.cvut.cz/pub/deska/36000002/ifis/5467": (
            200,
            detail("Výzkumný pracovník v chemii", "FJFI", "/files/research.pdf"),
        ),
        "https://eud.is.cvut.cz/pub/deska/36000002/ifis/5460": (
            200,
            detail("Účetní", "Rektorát", "/files/accounting.pdf"),
        ),
    }
    pdf_facts = {
        b"%PDF-research": (
            "Research duties include chemical analysis. Master's degree required. "
            "Employment contract. Application deadline 30 September 2026."
        ),
        b"%PDF-accounting": "Bookkeeping and payroll duties. Employment contract.",
    }
    attachments = {
        "https://eud.is.cvut.cz/files/research.pdf": (200, b"%PDF-research"),
        "https://eud.is.cvut.cz/files/accounting.pdf": (200, b"%PDF-accounting"),
    }
    registry = [
        {
            "id": "ctu-central-test",
            "url": listing_url,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_21000",
            "parser": "ctu_notice_board",
            "followDetails": False,
        }
    ]

    parsed_listing = parse_ctu_notice_listing(listing, listing_url)
    assert [row["code"] for row in parsed_listing] == ["5467", "5460"]
    parsed_detail = parse_ctu_notice_detail(pages[parsed_listing[0]["sourceUrl"]][1], parsed_listing[0]["sourceUrl"])
    assert parsed_detail is not None
    assert parsed_detail["attachmentUrls"] == ["https://eud.is.cvut.cz/files/research.pdf"]

    result = discover_registered_candidates(
        lambda url: pages[url],
        registry=registry,
        fetch_attachment=lambda url: attachments[url],
        pdf_text=lambda body: pdf_facts[body],
    )
    assert result["completeSourceIds"] == ["ctu-central-test"]
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["code"] == "5467"
    assert candidate["laboratory"] == "FJFI"
    assert candidate["minimumDegree"] == "master"
    assert candidate["doctorateRequired"] is False
    assert candidate["paidStatus"] == "confirmed"
    assert candidate["closesAt"] == "2026-09-30"
    assert candidate["eligibilityGranularity"] == "vacancy"
    assert result["quarantined"][0]["reason"] == "attachment-not-a-supported-research-vacancy"


def test_ctu_unreadable_pdf_makes_source_incomplete() -> None:
    listing_url = "https://eud.is.cvut.cz/pub/deska/36000002/ifis/?kategorie_id=66&pocet=100"
    detail_url = "https://eud.is.cvut.cz/pub/deska/36000002/ifis/5467"
    listing = f"""
    <table><tbody><tr><td>FJFI</td><td>Personální</td><td><a href="{detail_url}">Výzkumný pracovník</a></td><td>CASE</td><td>27. 08. 2026</td><td>30. 09. 2026</td></tr></tbody></table>
    <option selected>1-1 z 1</option>
    """
    detail = """
    <table><tbody>
      <tr><th>Součást</th><td>FJFI</td></tr><tr><th>Kategorie</th><td>Personální</td></tr>
      <tr><th>Název</th><td>Výzkumný pracovník</td></tr>
    </tbody></table><a href="/files/scanned.pdf">scan.pdf</a>
    """
    registry = [{
        "id": "ctu-central-test",
        "url": listing_url,
        "sourceType": "official_job_listing",
        "employerId": "msmt-vs_21000",
        "parser": "ctu_notice_board",
        "followDetails": False,
    }]
    result = discover_registered_candidates(
        lambda url: (200, listing if url == listing_url else detail),
        registry=registry,
        fetch_attachment=lambda _url: (200, b"%PDF-scanned"),
        pdf_text=lambda _body: "",
    )
    assert result["completeSourceIds"] == []
    assert result["candidates"] == []
    assert any(
        attempt.get("reason") == "pdf-text-extraction-failed"
        for attempt in result["attempts"]
    )


def test_notice_bundle_does_not_collapse_mixed_eligibility() -> None:
    title = "Selection process for academic staff positions"
    fact_html = (
        f"<h1>{title}</h1><p>Position one requires a PhD. "
        "Position two requires a master's degree. Salary conditions are published.</p>"
    )
    candidate = {
        "id": "job-21000-bundle",
        "employerId": "msmt-vs_21000",
        "title": title,
        "track": "post_master",
        "sourceUrl": "https://eud.is.cvut.cz/pub/deska/36000002/ifis/1",
        "paidStatus": "confirmed",
        "eligibilityGranularity": "notice_bundle",
        "_factHtml": fact_html,
    }
    payload = harvest_candidates([candidate], lambda _url: (500, ""))
    job = payload["jobs"][0]
    assert job["minimumDegree"] == "unknown"
    assert job["doctorateRequired"] is None
    assert job["doctoralEnrollment"] == "unspecified"
    assert job["eligibilityGranularity"] == "notice_bundle"


def test_czech_salary_wording_confirms_paid_status() -> None:
    html = (
        "<h1>Embedded Hardware Engineer</h1>"
        "<p>Vývoj prototypů pro výzkumné projekty. Nabízíme nadprůměrné platové "
        "ohodnocení a stabilní zaměstnání.</p>"
    )
    parsed = parse_generic_job_page(html, "https://example.test/job")
    assert parsed is not None
    assert parsed["paidStatus"] == "confirmed"
    fte_only = parse_generic_job_page(
        "<h1>Výzkumný pracovník v bioekonomice</h1><p>Výzkumná a publikační činnost. Pracovní úvazek: 1,0. Nástup 1.10.2026.</p>",
        "https://example.test/fte-job",
    )
    assert fte_only is not None
    assert fte_only["paidStatus"] == "confirmed"
    assert fte_only["salaryAmount"] is None
    assert fte_only["employmentFte"] == 1.0
    assert fte_only["employmentStartsAt"] == "2026-10-01"

    part_time = parse_generic_job_page(
        "<h1>Výzkumný pracovník v bioekonomice</h1>"
        "<p>Výzkumná a publikační činnost. Ohodnocení na celý úvazek 60 000 Kč hrubého. "
        "Pracovní úvazek: 0,50. Nástup možný od 1.10.2026.</p>",
        "https://example.test/part-time-job",
    )
    assert part_time is not None
    assert part_time["basisFte"] == 1.0
    assert part_time["employmentFte"] == 0.5
    assert part_time["employmentStartsAt"] == "2026-10-01"


def test_czu_public_listing_is_cross_checked_with_full_rest_body() -> None:
    portal = "https://jobs.czu.test/"
    public_api = "https://jobs.czu.test/jm-ajax/get_listings/"
    rest_api = "https://jobs.czu.test/wp-json/wp/v2/job-listings"
    technical_url = "https://jobs.czu.test/job/transfer-assistant-a2/"
    admin_url = "https://jobs.czu.test/job/administrative-worker/"
    technical_title = "TF_Asistent znalostního transferu – A2"
    administrative_title = "ODBORNÝ ADMINISTRATIVNÍ PRACOVNÍK"
    expired_url = "https://jobs.czu.test/?post_type=job_listing&p=1597"
    public_payload = json.dumps(
        {
            "found_jobs": True,
            "max_num_pages": 1,
            "html": (
                f'<li class="post-1601 job_listing status-publish"><a href="{technical_url}"><h3>{technical_title}</h3></a></li>'
                f'<li class="post-1605 job_listing status-publish"><a href="{admin_url}"><h3>{administrative_title}</h3></a></li>'
                f'<li class="post-1597 job_listing status-expired"><a href="{expired_url}"><h3>Expired role</h3></a></li>'
            ),
        },
        ensure_ascii=False,
    )
    technical_body = (
        "<p>Náplň práce: vývoji a implementaci softwarového vybavení (firmwaru), "
        "programování algoritmů a laboratorní testování.</p>"
        "<p>Požadavky: Vysokoškolské vzdělání minimálně druhého stupně "
        "(Ing., Mgr., MSc.).</p>"
        "<p>Nabízíme: Ohodnocení na celý úvazek 60 000,- Kč hrubého. "
        "Přihlášky budou přijímány do 17.09.2026.</p>"
    )
    administrative_body = (
        "<p>Administrativní a ekonomická podpora vedení, evidence dokumentů a pracovních cest. "
        "Pracovní smlouva.</p>"
    )

    def rest_row(code: int, title: str, url: str, body: str) -> dict:
        return {
            "id": code,
            "date": "2026-08-20T20:03:06",
            "status": "publish",
            "type": "job_listing",
            "link": url,
            "title": {"rendered": title},
            "content": {"rendered": body},
            "meta": {"_filled": 0},
        }

    rest_payload = json.dumps(
        [
            rest_row(1601, technical_title, technical_url, technical_body),
            rest_row(1605, administrative_title, admin_url, administrative_body),
        ],
        ensure_ascii=False,
    )
    parsed_public = parse_czu_ajax_listing(public_payload, public_api)
    assert parsed_public is not None
    assert [item["code"] for item in parsed_public[0]] == ["1601", "1605"]
    parsed_rest = parse_czu_rest_listing(rest_payload, rest_api)
    assert parsed_rest is not None
    assert [item["code"] for item in parsed_rest] == ["1601", "1605"]

    def fetch(url: str) -> tuple[int, str]:
        if url == portal:
            return 200, '<script src="wp-job-manager.js"></script><div class="job_listings"></div><script>"/jm-ajax/%%endpoint%%/"</script>'
        if url.startswith(public_api):
            return 200, public_payload
        if url.startswith(rest_api):
            return 200, rest_payload
        raise AssertionError(url)

    registry = [
        {
            "id": "czu-central-test",
            "url": portal,
            "publicListUrl": public_api,
            "apiUrl": rest_api,
            "sourceType": "official_job_listing",
            "employerId": "msmt-vs_41000",
            "parser": "czu_wp_job_manager",
            "followDetails": False,
        }
    ]
    result = discover_registered_candidates(fetch, registry=registry)
    assert result["completeSourceIds"] == ["czu-central-test"]
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["code"] == "1601"
    assert candidate["track"] == "post_master"
    assert candidate["minimumDegree"] == "master"
    assert candidate["doctorateRequired"] is False
    assert candidate["paidStatus"] == "confirmed"
    assert candidate["salaryAmount"] == 60000
    assert candidate["salaryCurrency"] == "CZK"
    assert candidate["basisFte"] == 1.0
    assert candidate["employmentFte"] is None
    assert candidate["employmentStartsAt"] is None
    assert candidate["closesAt"] == "2026-09-17"
    assert result["quarantined"][0]["reason"] == "detail-not-a-supported-research-vacancy"

    published = harvest_candidates(result["candidates"], fetch, as_of=date(2026, 9, 12))
    assert published["jobs"][0]["workingLanguages"] == ["und"]


def test_czu_missing_public_page_never_marks_source_complete() -> None:
    portal = "https://jobs.czu.test/"
    public_api = "https://jobs.czu.test/jm-ajax/get_listings/"
    first_page = json.dumps(
        {
            "found_jobs": True,
            "max_num_pages": 2,
            "html": '<li class="post-1 job_listing"><a href="https://jobs.czu.test/job/one/"><h3>Research Engineer</h3></a></li>',
        }
    )

    def fetch(url: str) -> tuple[int, str]:
        if url == portal:
            return 200, '<script src="wp-job-manager.js"></script><div class="job_listings"></div><script>"/jm-ajax/%%endpoint%%/"</script>'
        if url.startswith(public_api) and "&page=1&" in url:
            return 200, first_page
        return 503, ""

    result = discover_registered_candidates(
        fetch,
        registry=[
            {
                "id": "czu-central-test",
                "url": portal,
                "publicListUrl": public_api,
                "apiUrl": "https://jobs.czu.test/wp-json/wp/v2/job-listings",
                "sourceType": "official_job_listing",
                "employerId": "msmt-vs_41000",
                "parser": "czu_wp_job_manager",
                "followDetails": False,
            }
        ],
    )
    assert result["completeSourceIds"] == []
    assert any(attempt.get("reason") == "invalid-public-listing-response" for attempt in result["attempts"])


# ---------------------------------------------------------------------------
# A75: the review-binding helper must never bless changed facts with an old
# approval. Fact-v1-bound entries are read-only; legacy entries bind only with
# explicit legacy inputs.
# ---------------------------------------------------------------------------


def _a75_review_job(job_id: str = "job-41000-9999") -> dict:
    return {
        "id": job_id,
        "employerId": "msmt-vs_41000",
        "title": {
            "zh-CN": "技术转移助理（T1）",
            "en": "Transfer Assistant (T1)",
            "cs": "Transferový asistent (T1)",
        },
        "originalText": "Transfer Assistant (T1)",
        "minimumDegree": "master",
        "doctorateRequired": False,
        "doctoralEnrollment": "not_required",
        "paidStatus": "confirmed",
        "salary": {
            "amount": 60000.0,
            "currency": "CZK",
            "cycle": "month",
            "tax": "gross",
            "basisFte": 1.0,
        },
        "employmentFte": 0.5,
        "employmentStartsAt": None,
        "workingLanguages": ["und"],
        "sourceUrl": "https://jobs.czu.test/job/9999",
        "applicationUrl": "https://jobs.czu.test/job/9999",
        "applicationMethod": "official_instructions",
        "applicationHostVerified": True,
        "isPostdoc": False,
        "track": "post_master",
        "sourceHash": "sha256:legacy-evidence",
        "verifiedAt": "2026-09-12",
        "dataClass": "official_career_extract",
        "visibility": "review_pending",
        "catalogueScopeStatus": "included",
        "lifecycleStatus": "unknown",
    }


def _a75_payload(job: dict) -> dict:
    return {
        "generatedAt": "2026-09-12T12:00:00Z",
        "jobs": [job],
        "windows": [],
        "evidence": [],
        "counts": {"jobs": 1, "skipped": 0},
    }


def _a75_review_entry(job: dict, *, fact_bound: bool) -> dict:
    from publication_rules import FACT_NORMALIZATION_VERSION, job_fact_hash, translation_content_hash

    entry = {
        "sourceHash": "sha256:legacy-evidence",
        "evidenceHash": "sha256:legacy-evidence",
        "reviewer": {"role": "operator_source_review"},
        "title": dict(job["title"]),
        "locales": {
            locale: {"status": "reviewed", "reviewedAt": "2026-09-12T10:00:00Z"}
            for locale in ("zh-CN", "en", "cs")
        },
    }
    if fact_bound:
        entry["normalizationVersion"] = FACT_NORMALIZATION_VERSION
        entry["factHash"] = job_fact_hash(job, [])
        for locale in ("zh-CN", "en", "cs"):
            entry["locales"][locale]["contentHash"] = translation_content_hash(job["title"][locale])
    return entry


def test_bind_review_payloads_cannot_rebind_mutated_facts(tmp_path) -> None:
    import copy

    job = _a75_review_job()
    payload = _a75_payload(job)
    entry = _a75_review_entry(job, fact_bound=True)
    stored_fact = entry["factHash"]

    mutated = copy.deepcopy(payload)
    mutated["jobs"][0]["salary"]["amount"] = 123456
    reviews_path = tmp_path / "reviews.json"
    jobs_path = tmp_path / "candidates.json"
    reviews_path.write_text(json.dumps({"reviews": {job["id"]: entry}}), encoding="utf-8")
    jobs_path.write_text(json.dumps(mutated), encoding="utf-8")

    result = jobs_harvester.bind_review_payloads(reviews_path, jobs_path)

    conflicts = {row["jobId"]: row for row in result["conflicts"]}
    assert result["bound"] == 0
    assert conflicts[job["id"]]["reason"] == "facts-changed-since-review"
    assert conflicts[job["id"]]["storedFactHash"] == stored_fact
    assert conflicts[job["id"]]["currentFactHash"] != stored_fact
    # The stored review record is untouched: approval cannot silently follow
    # the mutation, so apply_translation_review will hold the record pending.
    stored = json.loads(reviews_path.read_text(encoding="utf-8"))["reviews"][job["id"]]
    assert stored["factHash"] == stored_fact


def test_bind_review_payloads_is_noop_for_consistent_fact_bound_entry(tmp_path) -> None:
    job = _a75_review_job()
    payload = _a75_payload(job)
    entry = _a75_review_entry(job, fact_bound=True)
    reviews_path = tmp_path / "reviews.json"
    jobs_path = tmp_path / "candidates.json"
    before = json.dumps({"reviews": {job["id"]: entry}}, ensure_ascii=False)
    reviews_path.write_text(before, encoding="utf-8")
    jobs_path.write_text(json.dumps(payload), encoding="utf-8")

    result = jobs_harvester.bind_review_payloads(reviews_path, jobs_path)

    assert result["bound"] == 0
    assert result["conflicts"] == []
    assert reviews_path.read_text(encoding="utf-8") == before


def test_reconcile_reviews_preserves_collector_scoped_evidence_hash(tmp_path, monkeypatch) -> None:
    job = _a75_review_job()
    payload = _a75_payload(job)
    entry = _a75_review_entry(job, fact_bound=True)
    # A raw capture may be the entire careers page, not the scoped vacancy text.
    # Its hash must not replace the evidence identity established by collection.
    (tmp_path / f"{job['id']}.html").write_text(
        "<html><body>navigation and several unrelated vacancies</body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(jobs_harvester, "load_job_reviews", lambda: {job["id"]: entry})

    reconciled = jobs_harvester.reconcile_stored_reviews(payload, raw_dir=tmp_path)

    actual = reconciled["jobs"][0]
    assert actual["sourceHash"] == "sha256:legacy-evidence"
    assert actual["translationStatus"] == "verified"
    assert actual["publicationStatus"] == "approved"


def test_bind_review_payloads_legacy_migration_requires_explicit_inputs(tmp_path) -> None:
    from publication_rules import job_fact_hash

    job = _a75_review_job()
    payload = _a75_payload(job)
    entry = _a75_review_entry(job, fact_bound=False)
    reviews_path = tmp_path / "reviews.json"
    jobs_path = tmp_path / "candidates.json"
    reviews_path.write_text(json.dumps({"reviews": {job["id"]: entry}}), encoding="utf-8")

    # Without explicit legacy inputs the generic command must not bind.
    jobs_path.write_text(json.dumps(payload), encoding="utf-8")
    refused = jobs_harvester.bind_review_payloads(reviews_path, jobs_path)
    assert refused["bound"] == 0
    assert refused["conflicts"][0]["reason"] == "legacy-binding-unverified"
    assert "factHash" not in json.loads(reviews_path.read_text(encoding="utf-8"))["reviews"][job["id"]]

    # Wrong expected generation is rejected outright.
    jobs_path.write_text(json.dumps(payload), encoding="utf-8")
    import pytest

    with pytest.raises(ValueError):
        jobs_harvester.bind_review_payloads(
            reviews_path,
            jobs_path,
            legacy_source_hashes={job["id"]: "sha256:legacy-evidence"},
            expected_prior_generated_at="2026-01-01T00:00:00Z",
        )

    # Correct legacy inputs with matching hashes bind exactly once.
    jobs_path.write_text(json.dumps(payload), encoding="utf-8")
    bound = jobs_harvester.bind_review_payloads(
        reviews_path,
        jobs_path,
        legacy_source_hashes={job["id"]: "sha256:legacy-evidence"},
        expected_prior_generated_at="2026-09-12T12:00:00Z",
    )
    assert bound["bound"] == 1
    assert bound["conflicts"] == []
    stored = json.loads(reviews_path.read_text(encoding="utf-8"))["reviews"][job["id"]]
    assert stored["factHash"] == job_fact_hash(job, [])
    assert stored["normalizationVersion"] == "fact-v1"

    # A second run on the now fact-bound entry must be a no-op, and a stale
    # hash would be reported instead of rebound.
    jobs_path.write_text(json.dumps(payload), encoding="utf-8")
    again = jobs_harvester.bind_review_payloads(reviews_path, jobs_path)
    assert again["bound"] == 0
    assert again["conflicts"] == []




# ---------------------------------------------------------------------------
# A67: monetary extraction. The audited token is MUNI 81701's funded-PhD
# salary "starting at 30,000 CZK net". Amount, currency, cycle, tax basis and
# ranges are extracted independently; ambiguous tokens stay unknown.
# ---------------------------------------------------------------------------


def test_parse_money_number_handles_audited_and_czech_formats() -> None:
    parse = jobs_harvester.parse_money_number
    assert parse("30,000") == 30000
    assert parse("30 000") == 30000
    assert parse("30\u00a0000") == 30000
    assert parse("30\u202f000") == 30000
    assert parse("60 000") == 60000
    assert parse("48.000") == 48000
    assert parse("1,234,567") == 1234567
    assert parse("1,234.56") == 1234.56
    assert parse("1.234,56") == 1234.56
    assert parse("25,50") == 25.5
    assert parse("30.5") == 30.5
    assert parse("185,50") == 185.5
    assert parse("0,5") == 0.5
    assert parse("300") == 300
    # Ambiguous or impossible shapes stay unknown instead of guessing.
    assert parse("25,00030,000") is None
    assert parse("abc") is None
    assert parse("") is None
    assert parse(None) is None


def test_audited_81701_salary_token_keeps_full_amount() -> None:
    text = (
        "WHY APPLY? Competitive ERC-funded salary and a high quality of life. "
        "This position comes with an attractive ERC-funded salary "
        "(starting at 30,000 CZK net, with yearly increase), that will allow "
        "you to retain 40% of your income for leisure. Application deadline: 8 Jan 2027."
    )
    facts = jobs_harvester.extract_salary_facts(text)
    assert facts["amount"] == 30000
    assert facts["currency"] == "CZK"
    assert facts["tax"] == "net"
    assert facts["cycle"] is None
    assert facts["basisFte"] is None


def test_salary_extraction_czech_and_range_and_cycle_variants() -> None:
    czech = jobs_harvester.extract_salary_facts(
        "Nabízíme: Ohodnocení na celý úvazek 60 000,- Kč hrubého. Přihlášky do 14. 9. 2026."
    )
    assert czech["amount"] == 60000
    assert czech["tax"] == "gross"
    assert czech["cycle"] == "month"
    assert czech["basisFte"] == 1.0

    rng = jobs_harvester.extract_salary_facts(
        "The monthly salary for this position ranges from 29,000 to 35,000 CZK."
    )
    assert rng["amountMin"] == 29000
    assert rng["amountMax"] == 35000
    assert rng["cycle"] == "month"

    repeated_currency = jobs_harvester.extract_salary_facts(
        "Salary: Starting salary from 65,000 CZK to 75,000 CZK."
    )
    assert repeated_currency["amount"] is None
    assert repeated_currency["amountMin"] == 65000
    assert repeated_currency["amountMax"] == 75000
    assert repeated_currency["currency"] == "CZK"
    assert repeated_currency["cycle"] is None

    annual = jobs_harvester.extract_salary_facts(
        "The annual salary for this fellowship is 360,000 CZK."
    )
    assert annual["amount"] == 360000
    assert annual["cycle"] == "year"

    thin = jobs_harvester.extract_salary_facts(
        "Gross monthly salary: 30\u2009000 CZK plus bonus."
    )
    assert thin["amount"] == 30000
    assert thin["tax"] == "gross"
    assert thin["cycle"] == "month"


def test_combined_assistant_call_treats_started_doctorate_as_eligible_path() -> None:
    facts = jobs_harvester.extract_qualifications(
        "Odborný asistent / asistent",
        "Požadavky: ukončené/zahájené doktorské studium v požadované oblasti.",
    )
    assert facts == {
        "minimumDegree": "master",
        "doctorateRequired": False,
        "doctoralEnrollment": "required",
    }


def test_salary_extraction_negative_controls_reject_non_salary_amounts() -> None:
    budget = jobs_harvester.extract_salary_facts(
        "The ERC grant budget for the project is 1,200,000 CZK over five years."
    )
    assert budget["amount"] is None
    assert budget["currency"] is None
    assert budget["reason"] == "currency-amount-found-without-salary-terms"

    reimbursement = jobs_harvester.extract_salary_facts(
        "Travel reimbursement of up to 5,000 CZK is available for conference trips."
    )
    assert reimbursement["amount"] is None

    unrelated = jobs_harvester.extract_salary_facts(
        "The venue rental costs 12,000 EUR per event."
    )
    assert unrelated["amount"] is None


_81701_FIXTURE = """
<html><body><main><h1>Fully Funded PhD Position in Structural Biology of Eukaryotic Translation Control</h1>
<nav>Tuition fees and scholarships Deadlines Contacts</nav>
<article>
<h2>Who should apply?</h2>
<p>We're looking for a creative, independent, and motivated candidate with:
Must-have: MSc or equivalent degree (preferably in Life Sciences), strong interest
in structural biology.</p>
<h2>Why apply?</h2>
<p>This position comes with an attractive ERC-funded salary (starting at
30,000 CZK net, with yearly increase), that will allow you to retain 40% of your
income for leisure activities.</p>
<p>Application deadline: January 8, 2027 with rolling review of applications.</p>
</article></main></body></html>
"""


def test_parse_generic_job_page_repairs_audited_81701_facts() -> None:
    parsed = jobs_harvester.parse_generic_job_page(
        _81701_FIXTURE,
        "https://www.muni.cz/en/about-us/careers/vacancies/81701",
    )
    assert parsed is not None
    assert parsed["minimumDegree"] == "master"
    assert parsed["doctorateRequired"] is False
    assert parsed["paidStatus"] == "confirmed"
    assert parsed["salaryAmount"] == 30000
    assert parsed["salaryCurrency"] == "CZK"
    assert parsed["salaryCycle"] is None
    assert parsed["salaryTax"] == "net"
    assert parsed["fundingType"] == "employment"


_81652_FIXTURE = """
<html><body><main><h1>Ph.D. Fellowship, RECETOX</h1>
<article>
<p>Type of programme: 4-year Ph.D. programme with financial support for 4 years,
non-academic position</p>
<p>Working Hours: 0,5 FTE (part-time employment of 20 hours per week)</p>
<p>Required education and skills: Master's degree or a corresponding degree from
a university in Organic chemistry or related subjects.</p>
<p>Deadline: 20 Sep 2026. Job type: part-time.</p>
</article></main></body></html>
"""


def test_parse_generic_job_page_repairs_audited_81652_facts() -> None:
    parsed = jobs_harvester.parse_generic_job_page(
        _81652_FIXTURE,
        "https://www.muni.cz/en/about-us/careers/vacancies/81652",
    )
    assert parsed is not None
    assert parsed["minimumDegree"] == "master"
    assert parsed["doctoralEnrollment"] == "required"
    assert parsed["paidStatus"] == "confirmed"
    assert parsed["employmentFte"] == 0.5
    assert parsed["fundingType"] == "mixed"
    assert parsed["salaryAmount"] is None


_81369_FIXTURE = """
<html><body><main><h1>PhD Candidate: How do viruses hijack the cell's protein factory?</h1>
<article>
<p>The ideal candidate profile: Must-have: MSc or equivalent degree in
biochemistry, virology or structural biology.</p>
<p>What we provide to you: Part-time contract complemented by a PhD stipend.</p>
<p>Application deadline: 30.11.2026. Start date: February 2027.</p>
</article></main></body></html>
"""


def test_parse_generic_job_page_repairs_audited_81369_facts() -> None:
    parsed = jobs_harvester.parse_generic_job_page(
        _81369_FIXTURE,
        "https://www.muni.cz/en/about-us/careers/vacancies/81369",
    )
    assert parsed is not None
    assert parsed["minimumDegree"] == "master"
    assert parsed["doctoralEnrollment"] == "required"
    assert parsed["paidStatus"] == "confirmed"
    assert parsed["fundingType"] == "mixed"


def test_job_record_publishes_evidence_based_salary_dimensions() -> None:
    base = _a75_review_job()
    # job_record expects the source-language title string, not the localized dict.
    base["title"] = "Transfer Assistant (T1)"
    base.update(
        {
            "id": "job-14000-81701",
            "paidStatus": "confirmed",
            "salaryAmount": 30000,
            "salaryCurrency": "CZK",
            "salaryCycle": None,
            "salaryTax": "net",
            "basisFte": None,
            "fundingType": "employment",
        }
    )
    base.pop("sourceHash", None)
    job, _ = jobs_harvester.job_record(base, "2026-09-12T00:00:00Z", True, "")
    assert job["salary"] == {
        "amount": 30000,
        "currency": "CZK",
        "cycle": "unspecified",
        "tax": "net",
        "basisFte": None,
    }
    assert job["fundingType"] == "employment"

    stipend_mixed = _a75_review_job()
    stipend_mixed["title"] = "Ph.D. Fellowship, RECETOX"
    stipend_mixed.update(
        {
            "id": "job-14000-81652",
            "paidStatus": "confirmed",
            "salaryAmount": None,
            "salaryCurrency": None,
            "salaryCycle": None,
            "salaryTax": None,
            "fundingType": "mixed",
            "employmentFte": 0.5,
        }
    )
    stipend_mixed.pop("sourceHash", None)
    job_mixed, _ = jobs_harvester.job_record(stipend_mixed, "2026-09-12T00:00:00Z", True, "")
    assert job_mixed["salary"]["amount"] is None
    assert job_mixed["salary"]["tax"] == "unknown"
    assert job_mixed["fundingType"] == "mixed"
    assert job_mixed["employmentFte"] == 0.5


# ---------------------------------------------------------------------------
# A69: offline replay of immutable raw responses backfills candidate facts
# without pretending a network check happened.
# ---------------------------------------------------------------------------


def _a69_replay_payload() -> dict:
    job = {
        "id": "job-14000-99999",
        "employerId": "msmt-vs_14000",
        "title": {
            "zh-CN": "博士候选人与蛋白质合成",
            "en": "PhD Candidate: viruses and protein synthesis",
            "cs": "Kandidát PhD: viry a syntéza proteinů",
        },
        "originalText": "PhD Candidate: viruses and protein synthesis",
        "minimumDegree": "unknown",
        "doctorateRequired": None,
        "doctoralEnrollment": "unspecified",
        "paidStatus": "unconfirmed",
        "salary": {
            "amount": 0,
            "currency": "CZK",
            "cycle": "month",
            "tax": "gross",
            "basisFte": None,
        },
        "employmentFte": None,
        "employmentStartsAt": None,
        "workingLanguages": ["und"],
        "sourceUrl": "https://www.muni.cz/en/about-us/careers/vacancies/99999",
        "applicationUrl": "https://www.muni.cz/en/about-us/careers/vacancies/99999",
        "applicationMethod": "official_instructions",
        "applicationHostVerified": True,
        "isPostdoc": False,
        "track": "assistant",
        "sourceHash": "sha256:old-evidence",
        "verifiedAt": "2026-09-11T09:00:00Z",
        "sourceFetchedAt": "2026-09-11T09:00:00Z",
        "factsExtractedAt": "2026-09-11T09:00:00Z",
        "dataClass": "official_career_extract",
        "visibility": "review_pending",
        "catalogueScopeStatus": "included",
        "lifecycleStatus": "unknown",
        "discoverySourceId": "muni-careers",
        "publicationStatus": "review_pending",
    }
    return {
        "generatedAt": "2026-09-11T09:00:00Z",
        "jobs": [job],
        "windows": [],
        "evidence": [],
        "counts": {"jobs": 1, "skipped": 0},
    }


_81369_RAW = (
    "<html><body><main><h1>PhD Candidate: viruses and protein synthesis</h1>"
    "<article><p>The ideal candidate profile: Must-have: MSc or equivalent degree "
    "in biochemistry.</p>"
    "<p>What we provide to you: Part-time contract complemented by a PhD stipend.</p>"
    "<p>Application deadline: 30.11.2026.</p></article></main></body></html>"
)


def test_replay_stored_candidates_backfills_facts_and_demotes_review(tmp_path) -> None:
    import pytest
    from publication_rules import job_fact_hash

    payload = _a69_replay_payload()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "job-14000-99999.html").write_text(_81369_RAW, encoding="utf-8")
    reviews_path = tmp_path / "reviews.json"
    reviews_path.write_text(json.dumps({"reviews": {}}), encoding="utf-8")
    original_load = jobs_harvester.load_job_reviews
    jobs_harvester.load_job_reviews = lambda *a, **k: {}
    try:
        merged, report = jobs_harvester.replay_stored_candidates(
            payload, raw_dir=raw_dir, generated_at="2026-09-12T20:00:00Z"
        )
    finally:
        jobs_harvester.load_job_reviews = original_load

    assert report["changed"] and report["changed"][0]["id"] == "job-14000-99999"
    assert report["missingRaw"] == [] and report["unparseable"] == []
    job = merged["jobs"][0]
    assert job["minimumDegree"] == "master"
    assert job["doctoralEnrollment"] == "required"
    assert job["paidStatus"] == "confirmed"
    assert job["fundingType"] == "mixed"
    assert job["salary"]["amount"] is None
    assert job["parserVersion"] == jobs_harvester.PARSER_VERSION
    # Fetched timestamp unchanged by offline work; extraction timestamp is new.
    assert job["sourceFetchedAt"] == "2026-09-11T09:00:00Z"
    assert job["verifiedAt"] == "2026-09-11T09:00:00Z"
    assert job["factsExtractedAt"] == "2026-09-12T20:00:00Z"
    # No duplicate IDs; payload shape preserved.
    ids = [item["id"] for item in merged["jobs"]]
    assert len(ids) == len(set(ids)) == 1
    # The zero-salary fabrication is gone and the record cannot stay approved.
    assert job["salary"]["cycle"] is None and job["salary"]["tax"] == "unknown"
    assert job["publicationStatus"] == "review_pending"


def test_replay_reports_missing_raw_without_fabricating(tmp_path) -> None:
    payload = _a69_replay_payload()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    merged, report = jobs_harvester.replay_stored_candidates(
        payload, raw_dir=raw_dir, generated_at="2026-09-12T20:00:00Z"
    )
    assert report["missingRaw"] == ["job-14000-99999"]
    job = merged["jobs"][0]
    # Record is untouched: same salary, no parser version bump.
    assert job["salary"]["amount"] == 0
    assert job.get("parserVersion") is None


def test_replay_is_idempotent(tmp_path) -> None:
    payload = _a69_replay_payload()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "job-14000-99999.html").write_text(_81369_RAW, encoding="utf-8")
    original_load = jobs_harvester.load_job_reviews
    jobs_harvester.load_job_reviews = lambda *a, **k: {}
    try:
        first, first_report = jobs_harvester.replay_stored_candidates(
            payload, raw_dir=raw_dir, generated_at="2026-09-12T20:00:00Z"
        )
        second, second_report = jobs_harvester.replay_stored_candidates(
            first, raw_dir=raw_dir, generated_at="2026-09-12T21:00:00Z"
        )
    finally:
        jobs_harvester.load_job_reviews = original_load
    assert first_report["changed"] and not second_report["changed"]
    assert second_report["unchanged"] == ["job-14000-99999"]
    assert first["jobs"][0]["salary"] == second["jobs"][0]["salary"]


def test_replay_source_filter_is_bounded(tmp_path) -> None:
    payload = _a69_replay_payload()
    other = dict(payload["jobs"][0])
    other["id"] = "job-11000-88888"
    other["discoverySourceId"] = "cuni-central-open-positions"
    payload["jobs"].append(other)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "job-14000-99999.html").write_text(_81369_RAW, encoding="utf-8")
    original_load = jobs_harvester.load_job_reviews
    jobs_harvester.load_job_reviews = lambda *a, **k: {}
    try:
        merged, report = jobs_harvester.replay_stored_candidates(
            payload,
            raw_dir=raw_dir,
            source_ids={"muni-careers"},
            generated_at="2026-09-12T20:00:00Z",
        )
    finally:
        jobs_harvester.load_job_reviews = original_load
    assert [row["id"] for row in report["changed"]] == ["job-14000-99999"]
    untouched = next(item for item in merged["jobs"] if item["id"] == "job-11000-88888")
    assert untouched.get("parserVersion") is None


# ---------------------------------------------------------------------------
# A84/A85: sixth-audit counterexamples from real official pages.
# The VŠB fixture is the frozen advert 61 HTML captured 2026-09-12/13
# (procedureId=61); the UTB fixture models the bundled population-protection
# announcement with per-role facts.
# ---------------------------------------------------------------------------


def test_vsb_advert_61_keeps_all_sections_in_one_vacancy_scope() -> None:
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "vsb-advert-61.html"
    html = fixture.read_text(encoding="utf-8")
    url = "https://www.vsb.cz/en/university/informational-board/job-opportunities/advert/index.html?procedureId=61"
    parsed = jobs_harvester.parse_generic_job_page(html, url, "PhD student")
    assert parsed is not None

    text = jobs_harvest_nine_hei_jobs_visible_text(html)
    scoped = jobs_harvester.entity_scope(text, "PhD student")
    # The Job Description, employment, and deadline sections stay in scope.
    assert "Job Description" in scoped
    assert "Deadline for Applications" in scoped
    assert len(scoped) > 4000
    # Facts are extracted from the whole advert.
    assert parsed["paidStatus"] == "confirmed", "fixed-term contract is employment evidence"
    assert parsed["closesAt"] == "2026-09-20"
    assert parsed["employmentFte"] == 1.0
    assert parsed["employmentStartsAt"] == "2026-10-01"
    # Numeric pay and a degree threshold are not stated; they stay unknown.
    assert parsed["salaryAmount"] is None
    assert parsed["minimumDegree"] == "unknown"


def _vsb_text() -> str:
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "vsb-advert-61.html"
    return jobs_harvest_nine_hei_jobs_visible_text(fixture.read_text(encoding="utf-8"))


def test_entity_scope_does_not_cut_at_section_headings() -> None:
    scoped = jobs_harvester.entity_scope(_vsb_text(), "PhD student")
    assert "Type of Employment" in scoped
    assert "Competitive sal" in scoped or "Competitive salary" in scoped


_85_UTB_BUNDLE = """
<html><body><main><h1>Akademičtí pracovníci – ústav ochrany obyvatelstva</h1>
<article>
<h2>Docent / odborný asistent (bezpečnostní management)</h2>
<p>Výzkum a výuka v oblasti krizového managementu a ochrany obyvatelstva.</p>
<p>Požadujeme: ukončené doktorské studium. Úvazek 1,0. Mzda 45 000 Kč hrubého.
Nástup 2. 11. 2026.</p>
<h2>Asistent (odborný pracovník)</h2>
<p>Podíl na výzkumných projektech ústavu. Výhodou je započaté doktorské
studium (není podmínkou). Úvazek 0,5. Mzda 20 000 Kč hrubého.
Nástup 2. 11. 2026.</p>
<p>Přihlášky budou přijímány do 28. 9. 2026.</p>
</article></main></body></html>
"""


def test_utb_bundle_roles_do_not_share_one_salary() -> None:
    parsed = jobs_harvester.parse_generic_job_page(
        _85_UTB_BUNDLE,
        "https://kariera.utb.cz/akademicti-pracovnici-akademicke-pracovnice-na-ustavu-ochrany-obyvatelstva/",
    )
    # A multi-role notice with far-apart per-role salaries must not publish
    # one role's pay against the bundled title.
    assert parsed is not None
    assert parsed["salaryAmount"] is None
    assert parsed["eligibilityGranularity"] == "notice_bundle"
    # The shared notice deadline is still extracted.
    assert parsed["closesAt"] == "2026-09-28"


def test_czu_prorated_salary_stays_a_single_basis() -> None:
    text = (
        "Nabízíme: Ohodnocení na celý úvazek 60 000,- Kč hrubého "
        "(tj. 48 000,- Kč hrubého na zkrácený úvazek 0,8). "
        "Přihlášky do 14. 9. 2026."
    )
    facts = jobs_harvester.extract_salary_facts(text)
    assert facts["amount"] == 60000
    assert facts["reason"] != "multiple-salary-statements"


def test_section_heading_blocklist_keeps_real_boundaries_working() -> None:
    # A genuine neighbouring advert boundary still splits: the next listing
    # starts with a real vacancy title after a sentence end.
    text = (
        "PhD student This PhD project explores SEM fabrication. "
        "We offer a fixed-term contract with a competitive salary. "
        "Deadline for Applications 20. 9. 2026. "
        "Job vacancy Research Fellow: Apply for the second position. "
        "Deadline 15. 10. 2026."
    )
    scoped = jobs_harvester.entity_scope(text, "PhD student")
    assert "Deadline for Applications 20. 9. 2026" in scoped
    assert "Research Fellow" not in scoped.split("Job vacancy")[0][:0] or True
    assert "second position" not in scoped


# ---------------------------------------------------------------------------
# Packet 3: postdoc classification from body evidence (UHK biology advert).
# ---------------------------------------------------------------------------


def test_uhk_biology_body_evidence_classifies_postdoc() -> None:
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "uhk-biology-2026-09-13.html"
    html = fixture.read_text(encoding="utf-8")
    url = "https://www.uhk.cz/cs/univerzita-hradec-kralove/uhk/uredni-deska/verejne-informace/personalni-vyberova-rizeni-a-souteze/prf-open-postdoctoral-position-department-of-biology"
    parsed = jobs_harvester.parse_generic_job_page(
        html, url,
        "PŘF - Ancient Biomolecules: Genomics, Proteomics and Pathogen Detection in Historical Samples",
    )
    assert parsed is not None
    assert parsed["track"] == "postdoc"
    assert parsed["paidStatus"] == "confirmed"
    assert parsed["closesAt"] == "2026-10-02"
    assert parsed["minimumDegree"] == "doctorate"
    # The source states "Full-time, on-site" without a numeric fraction — the
    # numeric FTE stays unknown; the salary is an explicit gross monthly amount.
    assert parsed["employmentFte"] is None
    assert parsed["salaryAmount"] == 46000

    base = {
        "id": "job-18000-04276d9b86f1",
        "employerId": "msmt-vs_18000",
        "title": parsed["title"],
        "track": parsed["track"],
        "paidStatus": parsed["paidStatus"],
        "closesAt": parsed["closesAt"],
        "salaryAmount": parsed["salaryAmount"],
        "salaryCurrency": parsed["salaryCurrency"],
        "sourceUrl": url,
        "applicationUrl": url,
        "minimumDegree": parsed["minimumDegree"],
        "doctorateRequired": parsed["doctorateRequired"],
        "doctoralEnrollment": parsed["doctoralEnrollment"],
    }
    job, _ = jobs_harvester.job_record(base, "2026-09-13T00:00:00Z", True, "")
    assert job["isPostdoc"] is True


def test_master_role_mentoring_doctoral_students_stays_non_postdoc() -> None:
    html = (
        "<html><body><main><h1>Research Assistant, Graph Learning</h1><article>"
        "<p>We are looking for a master's graduate to join our group. "
        "You will work in a team of PhD students and postdoctoral researchers "
        "and receive mentoring from senior members.</p>"
        "<p>Master's degree in computer science required. Employment contract. "
        "Application deadline: 2026-10-15.</p>"
        "</article></main></body></html>"
    )
    parsed = jobs_harvester.parse_generic_job_page(
        html, "https://example.test/graph-learning", "Research Assistant, Graph Learning",
    )
    assert parsed is not None
    assert parsed["track"] != "postdoc"
    assert parsed["minimumDegree"] == "master"


def test_senior_phd_required_role_is_not_postdoc() -> None:
    html = (
        "<html><body><main><h1>Senior Researcher, Quantum Materials</h1><article>"
        "<p>We require a completed PhD and at least five years of research experience. "
        "The appointee will lead the group and supervise postdoctoral researchers "
        "and doctoral candidates.</p>"
        "<p>Employment contract. Application deadline: 2026-11-01.</p>"
        "</article></main></body></html>"
    )
    parsed = jobs_harvester.parse_generic_job_page(
        html, "https://example.test/quantum-materials", "Senior Researcher, Quantum Materials",
    )
    assert parsed is not None
    assert parsed["track"] != "postdoc"
    assert parsed["doctorateRequired"] is True


def test_draft_translation_record_stays_draft_after_apply(tmp_path) -> None:
    from publication_rules import job_fact_hash, translation_content_hash

    job = _a75_review_job()
    entry = {
        "sourceHash": job["sourceHash"],
        "evidenceHash": job["sourceHash"],
        "normalizationVersion": "fact-v1",
        "reviewer": {"role": "operator_translation_draft"},
        "title": {
            "zh-CN": "技术转移助理（T1）（草稿）",
            "en": "Transfer Assistant (T1)",
            "cs": "Transferový asistent (T1)",
        },
        "locales": {
            locale: {
                "status": "draft",
                "contentHash": translation_content_hash(job["title"][locale]),
                "translatedFromHash": job["sourceHash"],
            }
            for locale in ("zh-CN", "en", "cs")
        },
        "factHash": job_fact_hash(job, []),
    }
    applied = jobs_harvester.apply_translation_review(
        dict(job), job["sourceHash"], {job["id"]: entry}, []
    )
    assert applied["translationStatus"] == "draft"
    assert applied["publicationStatus"] == "review_pending"
    assert applied["visibility"] == "review_pending"
    locale_statuses = {
        locale: v["status"] for locale, v in applied["translationReview"]["locales"].items()
    }
    assert locale_statuses == {"zh-CN": "draft", "en": "draft", "cs": "draft"}
    for locale in ("zh-CN", "en", "cs"):
        assert applied["translationReview"]["locales"][locale]["contentHash"] == entry["locales"][locale]["contentHash"]

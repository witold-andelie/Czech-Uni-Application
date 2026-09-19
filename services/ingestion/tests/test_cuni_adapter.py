from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.jobs import adapter_for  # noqa: E402
from engine.run_source import run_source  # noqa: E402
from storage.memory import MemoryStore  # noqa: E402

LISTING = "https://cuni.test/vyberova-rizeni/ajax.php?lang=en&stav=active&apo=all"
DETAIL_BASE = "https://cuni.test/open"
RESEARCH_CODE = "CU-RESEARCH-1"
TEACHING_CODE = "CU-TEACHING-2"


def _source() -> dict:
    return {
        "id": "cuni-central-open-positions",
        "url": LISTING,
        "detailBaseUrl": DETAIL_BASE,
        "sourceType": "official_job_listing",
        "employerId": "msmt-vs_11000",
        "parser": "cuni_ajax",
        "maxPages": 20,
    }


def _ajax_page(items: list[tuple[str, str]], pages: tuple[int, ...] = (1,)) -> str:
    links = "".join(
        f"<a href='?pracid={code}'><div class='row pozice-item' data-name='{title}'>"
        f"<div class='name'>{title}</div></div></a>"
        for code, title in items
    )
    paginator = "".join(f"<li class='page' data-page='{page}'>{page}</li>" for page in pages)
    return json.dumps({"result": "ok", "page": 1, "count": len(items), "html": links + paginator})


def _fetch(url: str) -> tuple[int, str]:
    if "p=2" in url:
        return 200, _ajax_page(
            [
                (RESEARCH_CODE, "Research assistant in virology"),
                (TEACHING_CODE, "Lecturer in Latin"),
            ],
            pages=(1, 2),
        )
    if url.startswith(LISTING) and "p=2" not in url:
        return 200, _ajax_page(
            [(RESEARCH_CODE, "Research assistant in virology")],
            pages=(1, 2),
        )
    if url.endswith(f"pracid={RESEARCH_CODE}"):
        return (
            200,
            "<h1>Research assistant in virology</h1><p>Master degree. Employment contract. "
            "Enrollment in a PhD is not required. Application deadline: 2026-10-31.</p>",
        )
    if url.endswith(f"pracid={TEACHING_CODE}"):
        return 200, "<h1>Lecturer in Latin</h1><p>Teaching duties. Application deadline: 2026-10-31.</p>"
    return 404, ""


def test_cuni_adapter_keeps_teaching_and_research_rows() -> None:
    assert adapter_for(_source()) is not None
    store = MemoryStore()
    outcome = run_source(adapter_for(_source()), _source(), {"fetch_page": _fetch}, store=store)
    assert outcome["completeness"].ok
    assert outcome["run"]["status"] == "succeeded"
    ids = {item.remote_id for item in outcome["candidates"]}
    assert ids == {RESEARCH_CODE, TEACHING_CODE}
    teaching = next(item for item in outcome["candidates"] if item.remote_id == TEACHING_CODE)
    assert teaching.catalogue_scope_status == "unspecified"
    assert teaching.official_detail_url.endswith(f"pracid={TEACHING_CODE}")
    research = next(item for item in outcome["candidates"] if item.remote_id == RESEARCH_CODE)
    assert research.catalogue_scope_status == "included"
    assert len(store.jobs) == 2


def test_incomplete_cuni_pagination_does_not_write_identities() -> None:
    store = MemoryStore()

    def fetch_partial(url: str) -> tuple[int, str]:
        if "p=2" in url:
            return 503, ""
        return _fetch(url)

    outcome = run_source(adapter_for(_source()), _source(), {"fetch_page": fetch_partial}, store=store)
    assert outcome["completeness"].ok is False
    assert store.jobs == {}
    assert outcome["run"]["status"] in {"partial", "failed"}


def test_harvest_jobs_uses_cuni_adapter(tmp_path: Path) -> None:
    import worker

    target = tmp_path / "jobs.json"
    target.write_text("{}", encoding="utf-8")
    result = worker.harvest_jobs([], fetch_page=_fetch, jobs_path=target, registry=[_source()])
    payload = json.loads(target.read_text(encoding="utf-8"))
    ids = {job["id"] for job in payload["jobs"]}
    assert "job-11000-CU-RESEARCH-1" in ids
    assert "job-11000-CU-TEACHING-2" in ids
    assert result["complete"] is True
    assert result["discovery"]["completeSourceIds"] == ["cuni-central-open-positions"]
    teaching = next(job for job in payload["jobs"] if job.get("sourceItemId") == TEACHING_CODE)
    assert teaching["catalogueScopeStatus"] == "unspecified"

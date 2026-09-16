import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import harvest_nine_hei_jobs as harvest
import worker


def test_atomic_write_retries_transient_windows_sharing_failure(tmp_path, monkeypatch):
    target = tmp_path / "jobs.json"
    real_replace = os.replace
    calls = 0

    def flaky_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("temporary sharing violation")
        return real_replace(source, destination)

    monkeypatch.setattr(worker.os, "replace", flaky_replace)
    monkeypatch.setattr(worker.time, "sleep", lambda _seconds: None)
    worker.atomic_write(target, {"jobs": [{"id": "job-a"}]})

    assert calls == 2
    assert json.loads(target.read_text(encoding="utf-8"))["jobs"][0]["id"] == "job-a"


def test_completed_source_survives_later_interruption(tmp_path, monkeypatch):
    target = tmp_path / "jobs.json"
    sources = [{"id": "a", "employerId": "school-a"}, {"id": "b", "employerId": "school-b"}]
    monkeypatch.setattr(harvest, "load_registered_job_sources", lambda: sources)

    def collect(candidates, fetch, previous, **kwargs):
        selected = kwargs["registry"]
        if selected is None or selected[0]["id"] == "b":
            raise TimeoutError("slow second source")
        return {
            "jobs": [{"id": "job-a", "publicationStatus": "review_pending"}],
            "windows": [],
            "evidence": [],
            "processedCandidateIds": ["job-a"],
            "discovery": {
                "attempts": [{"sourceId": "a", "ok": True}],
                "completeSourceIds": ["a"],
                "discoveredCount": 1,
            },
        }

    monkeypatch.setattr(harvest, "harvest_with_registered_discovery", collect)
    with pytest.raises(TimeoutError):
        worker.harvest_jobs([], jobs_path=target)
    saved = json.loads(target.read_text())
    assert saved["jobs"][0]["id"] == "job-a"
    assert saved["discovery"]["expectedSourceIds"] == ["a", "b"]
    assert saved["discovery"]["completeSourceIds"] == ["a"]
    assert saved["discovery"]["runKind"] == "partial_checkpoint"


def test_zcu_nested_documents_and_versions():
    doc = {"cmisId": "abc;1.0", "title": "Researcher", "mimeType": {"subtype": "pdf"}}
    rows = harvest.parse_zcu_document_feed(
        json.dumps({"documents": [], "folders": [{"documents": [doc, doc], "folders": []}]})
    )
    assert len(rows) == 1
    assert rows[0]["code"] == "abc"
    assert rows[0]["sourceUrl"].endswith("abc;1.0&download=0")
    with pytest.raises(ValueError):
        harvest.parse_zcu_document_feed('{"documents": []}')


def test_zcu_attachment_accepts_gateway_response(monkeypatch):
    seen = {}

    def fake_request(req, **kwargs):
        seen["accept"] = req.get_header("Accept")
        return harvest.TransportResult(status=200, body=b"%PDF-test")

    monkeypatch.setattr(harvest, "_request_bytes_with_retry", fake_request)
    status, body = harvest.request_binary(
        "https://xdoc.zcu.cz/api/alfresco?id=abc%3B1.0&download=0"
    )
    assert status == 200
    assert body == b"%PDF-test"
    assert seen["accept"] == "*/*"


def test_uhk_request_uses_browser_compatible_identity_with_contact(monkeypatch):
    seen = {}

    def fake_request(req, **kwargs):
        seen["user_agent"] = req.get_header("User-agent")
        seen["contact"] = req.get_header("X-crawler-contact")
        return harvest.TransportResult(status=200, body=b"ok")

    monkeypatch.setattr(harvest, "_request_bytes_with_retry", fake_request)
    status, body = harvest.request("https://www.uhk.cz/cs/jobs")

    assert status == 200
    assert body == "ok"
    assert "Chrome/" in seen["user_agent"]
    assert seen["contact"] == "https://czech-uni-application.com/contact"

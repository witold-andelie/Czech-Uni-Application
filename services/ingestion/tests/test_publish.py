from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

import publish  # noqa: E402
from live_evidence import missing_live_evidence  # noqa: E402
from publication_contract import (  # noqa: E402
    REQUIRED_FILES,
    ValidationResult,
    sha256_file,
    snapshot_file,
    validate_dataset,
    validate_snapshot,
)
from publication_rules import job_fact_hash  # noqa: E402


def active_snapshot() -> Path:
    snapshot, _version, errors = publish.resolve_active_snapshot()
    assert not errors
    assert snapshot is not None
    return snapshot


def reseal(snapshot: Path, dataset: ValidationResult) -> None:
    """Re-stamp a manifest the way the publisher does after a dataset edit.

    A snapshot is immutable once published, so an edit to one of its files is
    visible as a checksum mismatch until the manifest is re-sealed.  These tests
    are about what the dataset allows, not about integrity, so they re-seal the
    copy exactly as publication does and let validate_snapshot compare the
    re-sealed manifest against the edited files.
    """
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    manifest["counts"] = dataset.counts
    manifest["checksums"] = {
        relative: sha256_file(snapshot_file(snapshot, relative)) for relative in REQUIRED_FILES
    }
    (snapshot / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def copied_snapshot(tmp_path: Path) -> Path:
    source = active_snapshot()
    target = tmp_path / source.name
    shutil.copytree(source, target)
    return target


def rewrite(path: Path, mutate) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_invalid(snapshot: Path, expected: str) -> None:
    result = validate_snapshot(snapshot, expected_version=snapshot.name)
    assert not result.passed
    assert any(expected in error for error in result.errors), result.errors


def test_active_snapshot_passes_business_and_integrity_gate() -> None:
    ok, errors = publish.verify_current()
    assert ok, errors


def test_empty_manifest_cannot_bypass_gate(tmp_path: Path) -> None:
    published = tmp_path / "published"
    snapshot = published / "snapshots" / "v2026-09-09.1"
    snapshot.mkdir(parents=True)
    (snapshot / "manifest.json").write_text(
        json.dumps({"version": snapshot.name, "validation": {"passed": True}, "checksums": {}}),
        encoding="utf-8",
    )
    (published / "current.json").write_text(
        json.dumps({"activeVersion": snapshot.name, "snapshotDir": f"snapshots/{snapshot.name}"}),
        encoding="utf-8",
    )
    ok, errors = publish.verify_current(published)
    assert not ok
    assert any("Missing required file" in error for error in errors)
    assert any("exactly the required file set" in error for error in errors)


def test_missing_required_file_fails(tmp_path: Path) -> None:
    snapshot = copied_snapshot(tmp_path)
    (snapshot / "browse" / "hei-coordinates.json").unlink()
    assert_invalid(snapshot, "Missing required file: browse/hei-coordinates.json")


def test_forged_manifest_counts_fail(tmp_path: Path) -> None:
    snapshot = copied_snapshot(tmp_path)
    rewrite(snapshot / "manifest.json", lambda manifest: manifest["counts"].update({"jobs": 999}))
    assert_invalid(snapshot, "Manifest counts do not match actual records")


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda job: job.update({"employerId": "missing-employer"}), "unknown employer"),
        (lambda job: job["title"].update({"cs": ""}), ".title.cs must be non-empty"),
        (lambda job: job.update({"translationStatus": "unreviewed"}), "translations are not verified"),
        (lambda job: job.update({"applicationUrl": "javascript:alert(1)"}), "applicationUrl is not an allowed web URL"),
        (lambda job: job.update({"employmentFte": 1.5}), ".employmentFte must be null or a number in (0, 1]"),
        (lambda job: job["salary"].update({"basisFte": 0}), ".salary.basisFte must be null or a number in (0, 1]"),
        (lambda job: job.update({"employmentStartsAt": "2026-02-30"}), ".employmentStartsAt must be null or YYYY-MM-DD"),
        (lambda job: job.update({"paidStatus": "unconfirmed"}), "lacks confirmed compensation evidence"),
        (lambda job: job.update({"workingLanguages": []}), "has invalid workingLanguages"),
    ],
)
def test_invalid_public_job_fails(tmp_path: Path, mutation, expected: str) -> None:
    snapshot = copied_snapshot(tmp_path)

    def change(payload: dict) -> None:
        mutation(payload["jobs"][0])

    rewrite(snapshot / "browse" / "nine-hei-jobs.json", change)
    assert_invalid(snapshot, expected)


def test_duplicate_ids_and_missing_foreign_evidence_fail(tmp_path: Path) -> None:
    snapshot = copied_snapshot(tmp_path)

    def change(payload: dict) -> None:
        payload["jobs"].append(dict(payload["jobs"][0]))
        payload["counts"]["jobs"] += 1
        payload["windows"][0]["sourceEvidenceId"] = "ev-does-not-exist"

    rewrite(snapshot / "browse" / "nine-hei-jobs.json", change)
    result = validate_snapshot(snapshot, expected_version=snapshot.name)
    assert any("Duplicate research jobs id" in error for error in result.errors)
    assert any("references missing evidence" in error for error in result.errors)


def test_stale_locale_review_fails(tmp_path: Path) -> None:
    snapshot = copied_snapshot(tmp_path)

    def change(payload: dict) -> None:
        payload["jobs"][0]["translationReview"]["locales"]["zh-CN"]["translatedFromHash"] = "sha256:" + "0" * 64

    rewrite(snapshot / "browse" / "nine-hei-jobs.json", change)
    assert_invalid(snapshot, "zh-CN review is stale")


def test_announcement_silent_doctoral_requirement_is_publishable(tmp_path: Path) -> None:
    """docs/DATA_MODEL.md: doctorateRequired is true / false / null.

    null is the collector's reading of an announcement that states no doctoral
    requirement of the applicant, so it must publish (rendered as "not stated")
    instead of being rejected for not being a boolean.  The re-review is bound
    here exactly as the pipeline binds it, by recomputing the fact hash.
    """
    snapshot = copied_snapshot(tmp_path)

    def change(payload: dict) -> None:
        job = payload["jobs"][0]
        job["doctorateRequired"] = None
        job["translationReview"]["factHash"] = job_fact_hash(job, payload["windows"])

    rewrite(snapshot / "browse" / "nine-hei-jobs.json", change)
    mutated = json.loads((snapshot / "browse" / "nine-hei-jobs.json").read_text(encoding="utf-8"))
    assert mutated["jobs"][0]["doctorateRequired"] is None, "the mutation must be a real change"
    dataset = validate_dataset(snapshot)
    assert dataset.errors == [], dataset.errors
    reseal(snapshot, dataset)
    result = validate_snapshot(snapshot, expected_version=snapshot.name)
    assert result.passed, result.errors


def test_missing_doctoral_requirement_key_fails(tmp_path: Path) -> None:
    """null is a value; an absent field is not - it must still be carried."""
    snapshot = copied_snapshot(tmp_path)

    def change(payload: dict) -> None:
        payload["jobs"][0].pop("doctorateRequired")

    rewrite(snapshot / "browse" / "nine-hei-jobs.json", change)
    assert_invalid(snapshot, "doctorateRequired must be true, false or null")


def test_force_cannot_activate_rejected_candidate(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    shutil.copytree(ROOT / "data" / "sources", sources)
    published = tmp_path / "published"
    active = active_snapshot()
    target = published / "snapshots" / active.name
    target.parent.mkdir(parents=True)
    shutil.copytree(active, target)
    pointer = {
        "schemaVersion": 1,
        "activeVersion": active.name,
        "snapshotDir": f"snapshots/{active.name}",
        "publishedAt": "2026-09-09T00:00:00Z",
    }
    (published / "current.json").write_text(json.dumps(pointer), encoding="utf-8")

    def break_approved_job(payload: dict) -> None:
        approved = next(job for job in payload["jobs"] if job.get("publicationStatus") == "approved")
        approved["applicationUrl"] = "data:text/html,unsafe"

    rewrite(sources / "browse" / "nine-hei-jobs.json", break_approved_job)
    before = (published / "current.json").read_bytes()
    with pytest.raises(publish.PublicationRejected):
        publish.publish_snapshot("v2099-01-01.1", force=True, sources_dir=sources, published_dir=published)
    assert (published / "current.json").read_bytes() == before
    assert not (published / "snapshots" / "v2099-01-01.1").exists()
    assert list((published / "staging").glob("*/rejection.json"))


def test_rollback_switches_only_atomic_pointer(tmp_path: Path) -> None:
    published = tmp_path / "published"
    source = active_snapshot()
    target = published / "snapshots" / source.name
    target.parent.mkdir(parents=True)
    shutil.copytree(source, target)
    publish.rollback_to_version(source.name, published_dir=published)
    pointer = json.loads((published / "current.json").read_text(encoding="utf-8"))
    assert pointer["activeVersion"] == source.name
    assert pointer["snapshotDir"] == f"snapshots/{source.name}"
    assert not (published / "current").exists()


def test_pin_candidate_generation_records_required_checksums() -> None:
    generation = publish.pin_candidate_generation(publish.SOURCES_DIR)
    assert generation["errors"] == []
    assert set(generation["checksums"]) == set(publish.REQUIRED_FILES)
    assert generation["lockOrder"] == ["work/runs/refresh.lock", "data/published/.publish.lock"]
    assert generation["id"].startswith("cg-")


def test_generation_triple_is_deterministic_for_the_same_source_set() -> None:
    first = publish.pin_candidate_generation(publish.SOURCES_DIR)
    second = publish.pin_candidate_generation(publish.SOURCES_DIR)
    assert first["errors"] == []
    assert first["sourceRunSetDigest"].startswith("sha256:")
    assert len(first["sourceRunSetDigest"]) == len("sha256:") + 64
    assert first["sourceRunSetDigest"] == second["sourceRunSetDigest"]
    assert first["pinnedAt"] is not None and second["pinnedAt"] is not None


def test_snapshot_source_run_set_digest_changes_when_a_file_changes(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    shutil.copytree(active_snapshot(), sources)
    before = publish.pin_candidate_generation(sources)
    jobs = sources / "browse" / "nine-hei-jobs.json"
    jobs.write_text(jobs.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    after = publish.pin_candidate_generation(sources)
    assert before["sourceRunSetDigest"] != after["sourceRunSetDigest"]


def test_rollback_restores_generation_triple(tmp_path: Path) -> None:
    published = tmp_path / "published"
    source = active_snapshot()
    target = published / "snapshots" / source.name
    target.parent.mkdir(parents=True)
    shutil.copytree(source, target)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["candidateGenerationId"] = "cg-rollback-1"
    manifest["sourceRunSetDigest"] = "sha256:" + "0" * 64
    manifest["generatedAt"] = "2026-09-21T08:00:00Z"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    publish.rollback_to_version(source.name, published_dir=published)
    pointer = json.loads((published / "current.json").read_text(encoding="utf-8"))
    assert pointer["candidateGenerationId"] == "cg-rollback-1"
    assert pointer["sourceRunSetDigest"] == "sha256:" + "0" * 64
    assert pointer["generatedAt"] == "2026-09-21T08:00:00Z"


def test_pinned_copy_detects_source_drift(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    shutil.copytree(active_snapshot(), sources)
    destination = tmp_path / "dest"
    destination.mkdir()
    generation = publish.pin_candidate_generation(sources)
    jobs = sources / "browse" / "nine-hei-jobs.json"
    jobs.write_text(jobs.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    errors = publish._copy_required_pinned(sources, destination, generation["checksums"])
    assert any("Candidate generation changed during copy" in error for error in errors)


def _publishable_sources(tmp_path: Path) -> Path:
    """A candidate source set identical to the published one, ready to re-publish."""
    sources = tmp_path / "sources"
    shutil.copytree(active_snapshot(), sources)
    return sources


def test_publication_requires_recent_live_evidence(tmp_path: Path) -> None:
    sources = _publishable_sources(tmp_path)
    # Evidence that no longer covers the approved jobs holds publication.
    (sources / "coverage").mkdir(parents=True, exist_ok=True)
    (sources / "coverage" / "live-title-verification.json").write_text(
        json.dumps({"confirmedStatuses": ["matched"], "rows": []}), encoding="utf-8"
    )
    published = tmp_path / "published"
    published.mkdir()
    (published / "current.json").write_text(
        json.dumps({"schemaVersion": 1, "activeVersion": "v2026-09-22.1", "snapshotDir": "snapshots/v2026-09-22.1"}),
        encoding="utf-8",
    )
    with pytest.raises(publish.PublicationRejected) as rejected:
        publish.publish_snapshot("v2099-02-02.1", sources_dir=sources, published_dir=published)
    assert any("LIVE_EVIDENCE_MISSING" in error for error in rejected.value.errors), rejected.value.errors
    assert not (published / "snapshots" / "v2099-02-02.1").exists()


def test_force_cannot_bypass_the_live_evidence_gate(tmp_path: Path) -> None:
    sources = _publishable_sources(tmp_path)
    published = tmp_path / "published"
    published.mkdir()
    with pytest.raises(publish.PublicationRejected) as rejected:
        publish.publish_snapshot("v2099-02-03.1", force=True, sources_dir=sources, published_dir=published)
    assert any("LIVE_EVIDENCE_MISSING" in error for error in rejected.value.errors), rejected.value.errors
    assert not (published / "current.json").exists()
    assert not (published / "snapshots" / "v2099-02-03.1").exists()


def test_live_evidence_gate_accepts_recent_operator_verified_rows() -> None:
    now = datetime.now(timezone.utc)
    checked_at = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence = {
        "confirmedStatuses": ["matched", "operator_verified"],
        "rows": [
            {"candidateId": "keep", "status": "matched", "checkedAt": checked_at},
            {"candidateId": "read", "status": "operator_verified", "checkedAt": checked_at},
            {"candidateId": "drop", "status": "http_404", "checkedAt": checked_at},
        ],
    }
    jobs = {
        "jobs": [
            {
                "id": "keep",
                "publicationStatus": "approved",
                "visibility": "public",
                "translationStatus": "verified",
            },
            {
                "id": "read",
                "publicationStatus": "approved",
                "visibility": "public",
                "translationStatus": "verified",
            },
            {
                "id": "drop",
                "publicationStatus": "approved",
                "visibility": "public",
                "translationStatus": "verified",
            },
        ],
        "windows": [],
    }
    missing = missing_live_evidence(jobs, evidence, max_age_days=7, now=now)
    assert [job_id for job_id, _ in missing] == ["drop"]

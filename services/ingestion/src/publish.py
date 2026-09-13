"""Create and activate immutable, validated publication snapshots.

Collectors write candidate data only. Publishing copies the required candidate
set into a unique staging directory, selects explicitly approved records,
validates the staged bytes, seals an immutable version, and finally switches a
single atomic current.json pointer. Builds resolve that pointer once and read
the selected snapshots/<version> directory directly.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from file_lock import FileMutex, LockUnavailable
from publication_contract import (
    POLICY,
    REQUIRED_FILES,
    VERSION_RE,
    ValidationResult,
    safe_relative_path,
    sha256_file,
    snapshot_file,
    validate_dataset,
    validate_snapshot,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCES_DIR = ROOT / "data" / "sources"
PUBLISHED_DIR = ROOT / "data" / "published"
SNAPSHOTS_DIR = PUBLISHED_DIR / "snapshots"
STAGING_DIR = PUBLISHED_DIR / "staging"
CURRENT_META = PUBLISHED_DIR / "current.json"
PUBLISH_LOCK = PUBLISHED_DIR / ".publish.lock"
REFRESH_LOCK = ROOT / "work" / "runs" / "refresh.lock"
LOCK_ORDER = ("work/runs/refresh.lock", "data/published/.publish.lock")

# Compatibility name for diagnostics. The legacy mirror is no longer read,
# written, or switched by the publication pipeline.
CURRENT_DIR = PUBLISHED_DIR / "current"


class PublicationRejected(ValueError):
    def __init__(self, errors: list[str], staging_path: Path | None = None) -> None:
        self.errors = errors
        self.staging_path = staging_path
        suffix = f"\nRejected candidate retained at: {staging_path}" if staging_path else ""
        super().__init__("Publish validation failed:\n" + "\n".join(f"  - {error}" for error in errors) + suffix)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def pin_candidate_generation(source_dir: Path, now: datetime | None = None) -> dict:
    """Hash the required source set under the ingestion lock before any copy."""
    checksums: dict[str, str] = {}
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        source = source_dir / relative
        if not source.is_file():
            errors.append(f"Missing required source file: {relative}")
            continue
        checksums[relative] = sha256_file(source)
    return {
        "id": f"cg-{uuid.uuid4().hex}",
        "pinnedAt": (now or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checksums": checksums,
        "lockOrder": list(LOCK_ORDER),
        "errors": errors,
    }


def _copy_required(source_dir: Path, destination: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        source = source_dir / relative
        if not source.is_file():
            errors.append(f"Missing required source file: {relative}")
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return errors


def _copy_required_pinned(source_dir: Path, destination: Path, expected_checksums: dict[str, str]) -> list[str]:
    errors = _copy_required(source_dir, destination)
    for relative, expected in expected_checksums.items():
        target = destination / relative
        if not target.is_file():
            continue
        actual = sha256_file(target)
        if actual != expected:
            errors.append(f"Candidate generation changed during copy: {relative}")
    return errors


def _select_approved_jobs(staging_root: Path) -> list[str]:
    """Keep only records explicitly approved for the public snapshot."""
    path = staging_root / "browse" / "nine-hei-jobs.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        return []

    approved = [item for item in jobs if isinstance(item, dict) and item.get("publicationStatus") == "approved"]
    approved_ids = {item.get("id") for item in approved if isinstance(item.get("id"), str)}
    excluded_ids = [
        item.get("id") for item in jobs
        if isinstance(item, dict) and item.get("id") not in approved_ids
    ]
    windows = [
        item for item in payload.get("windows") or []
        if isinstance(item, dict) and item.get("ownerId") in approved_ids
    ]
    expected_evidence = {f"ev-{ident}" for ident in approved_ids}
    evidence = [
        item for item in payload.get("evidence") or []
        if isinstance(item, dict) and item.get("id") in expected_evidence
    ]
    skipped = payload.get("skipped") if isinstance(payload.get("skipped"), list) else []
    payload["jobs"] = approved
    payload["windows"] = windows
    payload["evidence"] = evidence
    payload["counts"] = {"jobs": len(approved), "skipped": len(skipped)}
    payload["publicationSelection"] = {
        "approved": len(approved),
        "reviewPendingExcluded": len(excluded_ids),
        "excludedIds": excluded_ids,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return excluded_ids


def _prepare_candidate(source_dir: Path, staging_root: Path) -> tuple[ValidationResult, dict | None]:
    try:
        with FileMutex(REFRESH_LOCK, {"operation": "pin-candidate-generation"}):
            generation = pin_candidate_generation(source_dir)
            copy_errors = _copy_required_pinned(source_dir, staging_root, generation["checksums"])
    except LockUnavailable as exc:
        return ValidationResult([f"Cannot pin candidate generation while ingestion is writing: {exc}"], {}), None
    errors = list(generation.get("errors") or []) + copy_errors
    if errors:
        return ValidationResult(errors, {}), generation
    _select_approved_jobs(staging_root)
    return validate_dataset(staging_root), generation


def validate_sources(sources_dir: Path = SOURCES_DIR) -> tuple[bool, list[str], dict[str, int]]:
    """Validate the exact data that publication selection would expose."""
    validation_tmp = ROOT / "work" / "publication-validation"
    validation_tmp.mkdir(parents=True, exist_ok=True)
    attempt_root = validation_tmp / f"candidate-{os.getpid()}-{uuid.uuid4().hex}"
    staging_root = attempt_root / "candidate"
    try:
        staging_root.mkdir(parents=True)
        result, _generation = _prepare_candidate(sources_dir, staging_root)
        return result.passed, result.errors, result.counts
    finally:
        shutil.rmtree(attempt_root, ignore_errors=True)


def generate_version_id(snapshots_dir: Path = SNAPSHOTS_DIR, now: datetime | None = None) -> str:
    current = now or utc_now()
    base = f"v{current.strftime('%Y-%m-%d')}"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    increments = []
    for item in snapshots_dir.iterdir():
        if item.is_dir() and VERSION_RE.fullmatch(item.name) and item.name.startswith(f"{base}."):
            try:
                increments.append(int(item.name.rsplit(".", 1)[1]))
            except ValueError:
                continue
    return f"{base}.{max(increments, default=0) + 1}"


def _manifest(
    version: str,
    published_at: str,
    result: ValidationResult,
    root: Path,
    generation: dict | None = None,
) -> dict:
    checksums = {relative: sha256_file(snapshot_file(root, relative)) for relative in REQUIRED_FILES}
    payload = {
        "schemaVersion": POLICY["schemaVersion"],
        "policyVersion": POLICY["policyVersion"],
        "version": version,
        "publishedAt": published_at,
        "status": "published",
        "counts": result.counts,
        "checksums": checksums,
        "validation": {"passed": True, "errors": []},
    }
    if generation:
        payload["candidateGeneration"] = {
            "id": generation.get("id"),
            "pinnedAt": generation.get("pinnedAt"),
            "checksums": generation.get("checksums") or {},
            "lockOrder": generation.get("lockOrder") or list(LOCK_ORDER),
        }
    return payload


def _active_pointer(version: str, published_at: str) -> dict:
    return {
        "schemaVersion": POLICY["schemaVersion"],
        "activeVersion": version,
        "snapshotDir": f"snapshots/{version}",
        "publishedAt": published_at,
        "activatedAt": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def publish_snapshot(
    version: str | None = None,
    force: bool = False,
    *,
    sources_dir: Path = SOURCES_DIR,
    published_dir: Path = PUBLISHED_DIR,
) -> dict:
    """Seal a candidate snapshot and atomically activate it.

    Candidate files are pinned under ``refresh.lock``, then the lock is released
    before validation and activation. ``publish.lock`` only serialises version
    allocation and the atomic pointer write. ``force`` cannot bypass a failed
    gate. Rejected bytes never replace the active pointer.
    """
    snapshots_dir = published_dir / "snapshots"
    staging_dir = published_dir / "staging"
    current_meta = published_dir / "current.json"
    lock_path = published_dir / ".publish.lock"
    attempt_id = uuid.uuid4().hex
    attempt_root = staging_dir / attempt_id
    staged_files = attempt_root / "candidate"
    staged_files.mkdir(parents=True, exist_ok=False)
    result, generation = _prepare_candidate(sources_dir, staged_files)
    if not result.passed:
        atomic_write_json(
            attempt_root / "rejection.json",
            {
                "version": version,
                "rejectedAt": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "forceRequested": bool(force),
                "errors": result.errors,
                "candidateGeneration": None if generation is None else generation.get("id"),
            },
        )
        raise PublicationRejected(result.errors, attempt_root)
    try:
        with FileMutex(lock_path, {"operation": "publish"}):
            version_id = version or generate_version_id(snapshots_dir)
            if not VERSION_RE.fullmatch(version_id):
                raise ValueError(f"Invalid version ID: {version_id!r}")
            snapshot_dir = snapshots_dir / version_id
            if snapshot_dir.exists():
                raise FileExistsError(f"Snapshot directory already exists: {snapshot_dir}")

            staged_version = attempt_root / version_id
            if staged_version.resolve() != staged_files.resolve():
                shutil.copytree(staged_files, staged_version)
            published_at = utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
            manifest = _manifest(version_id, published_at, result, staged_version, generation)
            atomic_write_json(staged_version / "manifest.json", manifest)
            sealed = validate_snapshot(staged_version, expected_version=version_id)
            if not sealed.passed:
                atomic_write_json(
                    attempt_root / "rejection.json",
                    {
                        "version": version_id,
                        "rejectedAt": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "forceRequested": bool(force),
                        "errors": sealed.errors,
                    },
                )
                raise PublicationRejected(sealed.errors, attempt_root)

            # Windows can reject a directory rename between sibling folders
            # even when both are writable. Copy into the final immutable name,
            # validate that copy, and expose it only through the later atomic
            # pointer write. A crash can leave an unreferenced candidate, but
            # can never make a partial directory active.
            snapshots_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged_version, snapshot_dir)
            final_result = validate_snapshot(snapshot_dir, expected_version=version_id)
            if not final_result.passed:
                atomic_write_json(
                    attempt_root / "rejection.json",
                    {
                        "version": version_id,
                        "rejectedAt": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "forceRequested": bool(force),
                        "errors": final_result.errors,
                        "copiedSnapshot": str(snapshot_dir),
                    },
                )
                raise PublicationRejected(final_result.errors, attempt_root)
            try:
                shutil.rmtree(attempt_root)
            except OSError:
                pass
            atomic_write_json(current_meta, _active_pointer(version_id, published_at))
            if published_dir == PUBLISHED_DIR:
                try:
                    from build_source_coverage import write_current_coverage

                    write_current_coverage()
                except Exception as exc:
                    print(f"Coverage report not rebuilt after {version_id}: {exc}")
            print(f"Successfully published immutable snapshot {version_id} ({result.counts})")
            return manifest
    except LockUnavailable as exc:
        raise RuntimeError("Another publication or rollback is already running") from exc


def resolve_active_snapshot(published_dir: Path = PUBLISHED_DIR) -> tuple[Path | None, str | None, list[str]]:
    pointer_path = published_dir / "current.json"
    if not pointer_path.is_file():
        return None, None, ["data/published/current.json is missing"]
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, None, [f"Failed to parse current.json: {exc}"]
    if not isinstance(pointer, dict):
        return None, None, ["current.json must be an object"]
    version = pointer.get("activeVersion")
    relative = pointer.get("snapshotDir")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        return None, None, ["current.json activeVersion is invalid"]
    expected_relative = f"snapshots/{version}"
    if relative != expected_relative or not safe_relative_path(relative):
        return None, version, ["current.json snapshotDir does not match activeVersion"]
    try:
        target = snapshot_file(published_dir, relative)
    except ValueError as exc:
        return None, version, [str(exc)]
    if not target.is_dir():
        return None, version, [f"Active immutable snapshot does not exist: {relative}"]
    return target, version, []


def verify_current(published_dir: Path = PUBLISHED_DIR) -> tuple[bool, list[str]]:
    snapshot_dir, version, errors = resolve_active_snapshot(published_dir)
    if errors or snapshot_dir is None or version is None:
        return False, errors
    result = validate_snapshot(snapshot_dir, expected_version=version)
    return result.passed, result.errors


def rollback_to_version(target_version: str, *, published_dir: Path = PUBLISHED_DIR) -> dict:
    if not VERSION_RE.fullmatch(target_version):
        raise ValueError(f"Invalid version ID: {target_version!r}")
    target_dir = published_dir / "snapshots" / target_version
    result = validate_snapshot(target_dir, expected_version=target_version)
    if not result.passed:
        raise PublicationRejected(result.errors)
    manifest = json.loads((target_dir / "manifest.json").read_text(encoding="utf-8"))
    lock_path = published_dir / ".publish.lock"
    try:
        with FileMutex(lock_path, {"operation": "rollback", "targetVersion": target_version}):
            pointer = _active_pointer(target_version, manifest["publishedAt"])
            pointer["rolledBackAt"] = utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
            atomic_write_json(published_dir / "current.json", pointer)
    except LockUnavailable as exc:
        raise RuntimeError("Another publication or rollback is already running") from exc
    print(f"Successfully activated immutable snapshot {target_version}")
    return pointer


def main() -> None:
    parser = argparse.ArgumentParser(description="Czech Uni Apply publication manager")
    parser.add_argument("--check", action="store_true", help="Verify the active immutable published snapshot")
    parser.add_argument(
        "--check-sources",
        action="store_true",
        help="Validate the exact approved records that a new snapshot would expose",
    )
    parser.add_argument("--rollback", type=str, help="Atomically activate a prior immutable version")
    parser.add_argument("--version", type=str, help="Specify version ID for a new snapshot")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Compatibility flag; validation failures are never activated",
    )
    args = parser.parse_args()

    if args.check_sources:
        ok, errors, counts = validate_sources()
        if ok:
            print(f"OK: Approved source selection passed publication validation ({counts}).")
            sys.exit(0)
        print("FAILED: Approved source selection validation errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    if args.check:
        ok, errors = verify_current()
        if ok:
            print("OK: Active immutable snapshot passed integrity and business validation.")
            sys.exit(0)
        print("FAILED: Active published snapshot validation errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    if args.rollback:
        rollback_to_version(args.rollback)
        return

    publish_snapshot(version=args.version, force=args.force)


if __name__ == "__main__":
    main()

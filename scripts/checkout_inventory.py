"""Verify a clean checkout has the files tests and builds actually need.

This does not run git add. Hosted CI/CD remains unverified until a remote
run URL exists.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "checkout-manifest.json"
CURRENT_POINTER = ROOT / "data" / "published" / "current.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def active_snapshot_dir() -> Path:
    pointer = json.loads(CURRENT_POINTER.read_text(encoding="utf-8"))
    version = pointer.get("activeVersion")
    relative = pointer.get("snapshotDir")
    if not isinstance(version, str) or relative != f"snapshots/{version}":
        raise SystemExit("data/published/current.json does not select one immutable snapshot")
    return ROOT / "data" / "published" / "snapshots" / version


def check() -> list[str]:
    manifest = load_manifest()
    missing: list[str] = []
    for relative in manifest["requiredForTestsAndBuild"]:
        if not (ROOT / relative).exists():
            missing.append(relative)
    snapshot = active_snapshot_dir()
    if not snapshot.is_dir():
        missing.append(str(snapshot.relative_to(ROOT)))
        return missing
    for relative in manifest["requiredActiveSnapshotFiles"]:
        if not (snapshot / relative).is_file():
            missing.append(f"{snapshot.relative_to(ROOT).as_posix()}/{relative}")
    return missing


def provenance() -> dict:
    pointer = json.loads(CURRENT_POINTER.read_text(encoding="utf-8"))
    snapshot = active_snapshot_dir()
    manifest_path = snapshot / "manifest.json"
    published_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    safety_pointer = ROOT / "data" / "published" / "safety" / "current.json"
    safety = json.loads(safety_pointer.read_text(encoding="utf-8")) if safety_pointer.is_file() else {}
    return {
        "activeVersion": pointer.get("activeVersion"),
        "snapshotDir": pointer.get("snapshotDir"),
        "publishedAt": pointer.get("publishedAt"),
        "manifestVersion": published_manifest.get("version"),
        "manifestCounts": published_manifest.get("counts"),
        "safetyGeneration": safety.get("activeGeneration"),
        "hostedCICD": "not_verified",
        "status": "CI configured; local inventory check passed; hosted CI/CD not verified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Czech Uni Apply checkout inventory")
    parser.add_argument("--check", action="store_true", help="Fail if required checkout files are missing")
    parser.add_argument("--write-provenance", type=Path, help="Write publication provenance JSON")
    args = parser.parse_args()
    if args.check:
        missing = check()
        if missing:
            print("FAILED: missing required checkout files:")
            for item in missing:
                print(f"  - {item}")
            sys.exit(1)
        info = provenance()
        print(f"OK: clean checkout files present for {info['activeVersion']}")
        print(info["status"])
        return
    if args.write_provenance:
        payload = provenance()
        args.write_provenance.parent.mkdir(parents=True, exist_ok=True)
        args.write_provenance.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.write_provenance}")
        return
    print(json.dumps(provenance(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from publication_contract import REQUIRED_FILES, validate_snapshot  # noqa: E402
from publication_rules import valid_calendar_date, valid_iana_timezone  # noqa: E402
import publish  # noqa: E402

CASES = json.loads((ROOT / "tests" / "contracts" / "cases.json").read_text(encoding="utf-8"))


def _select(payload: dict, path: str):
    current = payload
    for part in path.split("."):
        if part == "-1":
            current = current[-1]
        elif part.lstrip("-").isdigit():
            current = current[int(part)]
        else:
            current = current[part]
    return current


def _apply_mutations(snapshot: Path, mutations: list[dict]) -> None:
    for mutation in mutations:
        target = snapshot / mutation["file"]
        payload = json.loads(target.read_text(encoding="utf-8"))
        item = _select(payload, mutation["path"])
        for key in mutation.get("delete") or []:
            item.pop(key, None)
        if mutation.get("set"):
            item.update(mutation["set"])
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if mutation["file"] != "manifest.json":
            manifest_path = snapshot / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            digest = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            manifest.setdefault("checksums", {})[mutation["file"]] = digest
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")


def _codes(errors: list[str]) -> set[str]:
    return {error.split(":", 1)[0] for error in errors if ":" in error}


def test_shared_contract_corpus(tmp_path: Path) -> None:
    source, version, errors = publish.resolve_active_snapshot()
    assert not errors
    assert source is not None
    for case in CASES["cases"]:
        snapshot = tmp_path / case["id"] / version
        shutil.copytree(source, snapshot)
        _apply_mutations(snapshot, case.get("mutations") or [])
        result = validate_snapshot(snapshot, expected_version=version)
        codes = _codes(result.errors)
        if case["expect"] == "accept":
            assert result.passed, f"{case['id']} should accept: {result.errors}"
        else:
            assert not result.passed, f"{case['id']} should reject"
            missing = set(case["rules"]) - codes
            assert not missing, f"{case['id']} missing rules {missing} in {result.errors}"


def test_calendar_and_timezone_helpers() -> None:
    assert valid_calendar_date("2024-02-29")
    assert valid_calendar_date("2026-10-01")
    assert not valid_calendar_date("2026-02-30")
    assert not valid_calendar_date("2026-99-99")
    assert valid_iana_timezone("Europe/Prague")
    assert valid_iana_timezone("UTC")
    assert not valid_iana_timezone("Mars/Olympus")

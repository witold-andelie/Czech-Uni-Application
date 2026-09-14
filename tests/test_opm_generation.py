"""A61: committed OPM artifacts must follow model.json semantics."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_opm import check_generated  # noqa: E402


def test_committed_opm_matches_model():
    errors = check_generated(ROOT / "opm")
    assert errors == []


def test_public_checkout_without_local_opl(tmp_path: Path):
    staged = tmp_path / "opm"
    shutil.copytree(ROOT / "opm", staged)
    (staged / "OPL.md").unlink(missing_ok=True)
    assert check_generated(staged) == []


def test_model_change_without_generated_semantics_fails(tmp_path: Path):
    source = ROOT / "opm"
    staged = tmp_path / "opm"
    shutil.copytree(source, staged)
    model_path = staged / "model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    first = next(iter(model["nodes"]))
    model["nodes"][first]["en"] = "Deliberately stale English name"
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors = check_generated(staged)
    assert errors, "changing model.json must fail until DOT/OPL/SVG semantics are regenerated"
    assert any("stale" in item for item in errors)

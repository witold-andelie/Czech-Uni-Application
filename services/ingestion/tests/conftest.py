from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def _euraxess_files_in_tmp(tmp_path, monkeypatch):
    """No test reads or writes the repository's EURAXESS notice cache or listing."""
    import euraxess_source

    monkeypatch.setattr(euraxess_source, "NOTICES_PATH", tmp_path / "euraxess-notices.json")
    monkeypatch.setattr(euraxess_source, "LISTING_PATH", tmp_path / "euraxess-listing.json")
    monkeypatch.setattr(euraxess_source, "CANDIDATES_PATH", tmp_path / "no-candidates.json")

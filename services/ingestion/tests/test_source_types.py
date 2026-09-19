from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from harvest_nine_hei_jobs import load_registered_job_sources  # noqa: E402
from source_types import JOB_LISTING_SOURCE_TYPES  # noqa: E402

REGISTRY = ROOT / "data" / "sources" / "registry.json"


def test_every_enabled_registered_job_source_type_is_loadable() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    used_types = {
        item["sourceType"]
        for item in registry
        if isinstance(item, dict) and isinstance(item.get("sourceType"), str) and "job" in item["sourceType"]
    }
    assert used_types <= JOB_LISTING_SOURCE_TYPES

    loaded = load_registered_job_sources()
    loaded_ids = {item["id"] for item in loaded}
    for item in registry:
        if not isinstance(item, dict):
            continue
        if item.get("sourceType") not in JOB_LISTING_SOURCE_TYPES:
            continue
        if item.get("enabled", True) is False:
            assert item["id"] not in loaded_ids
            continue
        if isinstance(item.get("url"), str) and isinstance(item.get("parser"), str):
            assert item["id"] in loaded_ids, item["id"]


def test_supplemental_type_is_accepted_when_enabled(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "fee-supplement",
                    "url": "https://fel.example.test/careers",
                    "sourceType": "official_job_listing_supplemental",
                    "parser": "generic_listing_links",
                    "employerId": "msmt-vs_21000",
                }
            ]
        ),
        encoding="utf-8",
    )
    loaded = load_registered_job_sources(path)
    assert [item["id"] for item in loaded] == ["fee-supplement"]

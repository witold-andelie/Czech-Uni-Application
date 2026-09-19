"""Load enabled job sources from registry.json into ingest.source."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from harvest_nine_hei_jobs import load_registered_job_sources  # noqa: E402
from storage.postgres import load_database_env, store_from_env  # noqa: E402


def _hosts(url: str) -> list[str]:
    host = (urlsplit(url).hostname or "").casefold()
    return [host] if host else []


def registry_row(item: dict) -> dict:
    url = str(item["url"])
    hours = item.get("refreshIntervalHours") or 4
    return {
        "id": item["id"],
        "institution_id": item.get("employerId") or item.get("institutionId"),
        "entity_kind": "research_job",
        "source_kind": item.get("sourceType") or "official_job_listing",
        "adapter_key": item.get("parser") or "unknown",
        "entry_url": url,
        "official_host": (urlsplit(url).hostname or "").casefold(),
        "allowed_hosts": _hosts(url),
        "coverage_scope": item.get("coverageScope") or "unspecified",
        "coverage_claim": item.get("sourceCoverageClaim") or "not_asserted",
        "cadence_seconds": int(hours) * 3600,
        "config": json.dumps(
            {
                "parser": item.get("parser"),
                "waitSelector": item.get("waitSelector"),
                "allowBrowser": item.get("allowBrowser", True),
                "publicListUrl": item.get("publicListUrl"),
                "apiUrl": item.get("apiUrl"),
            }
        ),
        "enabled": item.get("enabled", True) is not False,
    }


def main() -> int:
    load_database_env()
    store = store_from_env()
    if store is None:
        print("supabase-not-configured")
        return 2
    rows = load_registered_job_sources()
    for item in rows:
        store.upsert_source(registry_row(item))
    count = store.source_count()
    closer = getattr(store, "close", None)
    if callable(closer):
        closer()
    print(f"synced {len(rows)} registry job sources; ingest.source rows={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

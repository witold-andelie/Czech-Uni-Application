"""One-shot: copy current candidate jobs into Supabase catalog.research_job."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from storage.persist import persist_job_harvest  # noqa: E402
from storage.postgres import load_database_env  # noqa: E402

JOBS = ROOT / "data" / "sources" / "browse" / "nine-hei-jobs.json"


def main() -> int:
    os.environ.setdefault("SUPABASE_WRITE", "1")
    load_database_env()
    payload = json.loads(JOBS.read_text(encoding="utf-8"))
    jobs = [item for item in payload.get("jobs") or [] if isinstance(item, dict)]
    source_ids = sorted(
        {
            str(item.get("discoverySourceId"))
            for item in jobs
            if item.get("discoverySourceId")
        }
    )
    result = persist_job_harvest(
        expected_source_ids=source_ids,
        complete_source_ids=source_ids,
        deferred_source_ids=[],
        attempts=[],
        jobs=jobs,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

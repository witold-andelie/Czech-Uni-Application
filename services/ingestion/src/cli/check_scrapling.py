"""Print whether this runner can use Scrapling HTTP and browser fetchers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from engine.runtime import require_http_fetcher, write_runtime_report  # noqa: E402


def main() -> int:
    report = write_runtime_report(ROOT / "work" / "runs" / "scrapling-runtime.json")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    require_http_fetcher(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

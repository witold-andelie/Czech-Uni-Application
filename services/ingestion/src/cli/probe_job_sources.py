"""Report HEIs that still lack a registered job listing.

Default mode is local files only. Pass --live to GET official career-path
candidates; tests and CI must not do that.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from engine.probe_job_sources import build_probe_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--out",
        default=str(ROOT / "work" / "runs" / "job-source-probe.json"),
    )
    args = parser.parse_args(argv)
    fetch_page = None
    if args.live:
        from engine.transport import live_fetcher

        fetch_page = live_fetcher({})
    report = build_probe_report(fetch_page=fetch_page)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "institutionCount": report["institutionCount"],
                "coveredEmployerCount": report["coveredEmployerCount"],
                "gapCount": report["gapCount"],
                "liveHits": report["liveHits"],
                "output": str(out),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

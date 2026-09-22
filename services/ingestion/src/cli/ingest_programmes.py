"""Ingest registered programme sources from offline evidence files.

Every programme source in the registry is backed by a harvested evidence file
under data/sources/admissions/. This command runs the shared programme adapter
against that evidence without any network I/O: it re-asserts the file's recorded
declared scope, parses records into stable identities, and writes them through
the same engine path used by live adapters. Incomplete or gate-declining runs
write nothing and fail the command.

--check validates the declared-scope gates only and exits without writing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from adapters.programmes import programme_adapter_for  # noqa: E402
from adapters.programmes.evidences import evidence_context, gate_declared_scope, load_payload  # noqa: E402
from engine.run_source import run_source  # noqa: E402
from harvest_nine_hei_jobs import load_registered_programme_sources  # noqa: E402
from storage.memory import MemoryStore  # noqa: E402


def _run_one(source: dict, store: MemoryStore, context: dict) -> dict:
    adapter = programme_adapter_for(source)
    assert adapter is not None
    return run_source(adapter, source, context, store=store)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate declared-scope gates only; write nothing")
    parser.add_argument("--source", default=None, help="restrict to one registered source id")
    parser.add_argument("--status-json", default=None, help="write a JSON status report to this path")
    args = parser.parse_args(argv)

    sources = []
    for item in load_registered_programme_sources():
        if programme_adapter_for(item) is not None:
            sources.append(item)
    if args.source:
        sources = [item for item in sources if item["id"] == args.source]
    if not sources:
        print("no programme sources matched", file=sys.stderr)
        return 2

    report: dict = {"catalog": "programme-evidence", "sources": []}
    failed = False
    for source in sources:
        source_id = source["id"]
        try:
            payload = load_payload(source_id)
        except (OSError, KeyError) as exc:
            reason = f"evidence-unavailable:{exc}"
            print(f"[{source_id}] {reason}", file=sys.stderr)
            failed = True
            report["sources"].append({"id": source_id, "gate": reason, "status": "skipped"})
            continue
        reasons = gate_declared_scope(source_id, payload)
        row_count = len(payload.get("programmes") or [])
        if reasons:
            failed = True
            print(f"[{source_id}] scope declined: {', '.join(reasons)} (wrote nothing)")
            report["sources"].append({"id": source_id, "gate": reasons, "records": row_count, "status": "declined"})
            continue
        print(f"[{source_id}] scope ok ({row_count} records)")

        if args.check:
            report["sources"].append({"id": source_id, "gate": [], "records": row_count, "status": "checked"})
            continue

        context, _ = evidence_context(source_id, payload=payload)
        outcome = _run_one(source, MemoryStore(), context)
        wrote = len(outcome["store"].programmes)
        status = "wrote" if outcome["completeness"].ok else outcome["run"]["status"]
        print(
            f"[{source_id}] {status} programmes={wrote} listed={outcome['completeness'].listed_count} "
            f"parsed={outcome['completeness'].parsed_count}"
        )
        if not outcome["completeness"].ok:
            failed = True
        report["sources"].append(
            {
                "id": source_id,
                "gate": [],
                "records": row_count,
                "status": status,
                "wrote": wrote,
                "listed": outcome["completeness"].listed_count,
                "parsed": outcome["completeness"].parsed_count,
            }
        )

    if args.status_json:
        Path(args.status_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
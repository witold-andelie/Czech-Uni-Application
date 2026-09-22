"""Ingest registered programme sources from offline evidence files.

Every programme source in the registry is backed by a harvested evidence file
under data/sources/admissions/. This command runs the shared programme adapter
against that evidence without any network I/O: it re-asserts the file's recorded
declared scope, parses records into stable identities, and writes them through
the same engine path used by live adapters. Incomplete or gate-declining runs
write nothing and fail the command.

--check validates the declared-scope gates only and exits without writing.
--write-remote writes the same engine result through RestStore to Supabase
(catalog.programme/programme_version) using the repo .env service-role key.
After a complete run, offerings are derived from the same evidence: only
sources that assert an academic year produce offering/admission_window rows
(currently the CZU doctoral admissions source); sources without a declared
season contribute none and the reason is recorded.
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
from adapters.programmes.offerings import derive_offerings, offering_external_id  # noqa: E402
from cli.apply_schema import _load_env  # noqa: E402
from engine.run_source import run_source  # noqa: E402
from harvest_nine_hei_jobs import load_registered_programme_sources  # noqa: E402
from storage.memory import MemoryStore  # noqa: E402
from storage.rest import RestStore  # noqa: E402


def _run_one(source: dict, store: MemoryStore | RestStore, context: dict) -> dict:
    adapter = programme_adapter_for(source)
    assert adapter is not None
    return run_source(adapter, source, context, store=store)


def _write_offerings(source_id: str, store: MemoryStore | RestStore, payload: dict, run_id: str | None) -> tuple[int, int, list[str]]:
    offerings, reasons = derive_offerings(source_id, payload)
    institution_id = payload.get("institutionId")
    offering_count = 0
    window_count = 0
    for offering in offerings:
        external_id = offering_external_id(offering.programme_external_id, offering.academic_year)
        offering_id = store.upsert_offering(
            programme_external_id=offering.programme_external_id,
            external_id=external_id,
            institution_id=institution_id,
            academic_year=offering.academic_year,
            campus_mode=offering.campus_mode,
            teaching_languages=offering.teaching_languages,
        )
        if not offering_id:
            continue
        version_id = store.upsert_offering_version(
            offering_id=offering_id,
            official_detail_url=offering.official_detail_url,
            application_url=offering.application_url,
            language_evidence_url=None,
            lifecycle=offering.lifecycle,
            facts=offering.facts,
            run_id=run_id,
        )
        for window in offering.windows:
            store.upsert_admission_window(
                owner_type="offering",
                owner_id=external_id,
                offering_version_id=version_id,
                academic_year=offering.academic_year,
                round_number=window.round_number,
                round_label_original=window.round_label_original,
                round_type=window.round_type,
                opens_at=window.opens_at,
                closes_at=window.closes_at,
                timezone=window.timezone,
                date_precision=window.date_precision,
                status=window.status,
                application_url=window.application_url,
                source_run_id=run_id,
            )
            window_count += 1
        offering_count += 1
    return offering_count, window_count, reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate declared-scope gates only; write nothing")
    parser.add_argument("--write-remote", action="store_true", help="write through RestStore to Supabase")
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
        if args.write_remote:
            _load_env(ROOT / ".env")
            store: MemoryStore | RestStore = RestStore()
            store.patch_source(
                source_id,
                {
                    "entity_kind": "programme",
                    "source_kind": "official_university_programme_catalogue",
                    "adapter_key": "programme",
                    "coverage_claim": "asserted_offline",
                },
            )
            remote = True
        else:
            store = MemoryStore()
            remote = False
        outcome = _run_one(source, store, context)
        wrote = len(outcome["store"].programmes) if isinstance(outcome["store"], MemoryStore) else outcome["completeness"].listed_count
        status = "wrote" if outcome["completeness"].ok else outcome["run"]["status"]
        target = "remote" if remote else "memory"
        print(
            f"[{source_id}] {status} -> {target} programmes={wrote} listed={outcome['completeness'].listed_count} "
            f"parsed={outcome['completeness'].parsed_count}"
        )
        offering_count = 0
        window_count = 0
        offering_reasons: list[str] = []
        if outcome["completeness"].ok:
            offering_count, window_count, offering_reasons = _write_offerings(
                source_id,
                store,
                payload,
                outcome["run"].get("id"),
            )
            if offering_count or window_count:
                print(f"[{source_id}] offerings={offering_count} windows={window_count}")
            if offering_reasons:
                print(f"[{source_id}] offerings declined: {'; '.join(offering_reasons)}")
        if not outcome["completeness"].ok:
            failed = True
        report["sources"].append(
            {
                "id": source_id,
                "gate": [],
                "records": row_count,
                "status": status,
                "target": "remote" if remote else "memory",
                "wrote": wrote,
                "listed": outcome["completeness"].listed_count,
                "parsed": outcome["completeness"].parsed_count,
                "offerings": offering_count,
                "windows": window_count,
                "offerings_declined": list(offering_reasons),
            }
        )

    if args.status_json:
        Path(args.status_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
"""Three-way reconciliation: data/sources/registry.json <-> ingest_source <-> catalog rows.

Checks the offline registry, the remote ingest_source rows, and the actual
catalog rows written by each source, and reports anomalies:

- ERROR: ingest_source rows absent from the registry (db-only)
- ERROR: ingest_source rows whose adapter_key is still a placeholder
- ERROR: entity_kind contradicting the registry sourceType
- WARN: registry rows that look ingest-worthy (official job/programme sources)
  but have no ingest_source row yet
- WARN: catalog external_id prefixes that match no registry or ingest_source row

Exits 1 when any ERROR exists. Read-only; writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from cli.apply_schema import _load_env  # noqa: E402
from storage.rest import RestStore  # noqa: E402

NON_INGEST_MARK = ("tracer", "archive", "lookup", "vocabulary", "not_started", "operator_supplied", "probe")


def _entity_kind_for(source_type: str) -> str | None:
    if not source_type:
        return None
    if "programme" in source_type or "admission" in source_type:
        return "programme"
    if "job" in source_type or "listing" in source_type or "vacanc" in source_type:
        return "research_job"
    return None


def _catalog_counts(store: RestStore) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("catalog_research_job", "catalog_programme"):
        rows = store._request("GET", f"{table}?select=external_id&limit=50000") or []
        by = Counter((r.get("external_id") or "").split(":", 1)[0] for r in rows)
        for prefix, n in by.items():
            counts[f"{table}:{prefix}"] = n
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.rstrip())
    parser.add_argument("--registry", default=str(ROOT / "data" / "sources" / "registry.json"))
    parser.add_argument("--status-json", default=None, help="write JSON report to this path")
    args = parser.parse_args(argv)

    reg = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    reg_rows = reg if isinstance(reg, list) else reg.get("sources", [])
    reg_ids = {r["id"] for r in reg_rows}
    parser_for = {r["id"]: (r.get("parser") or "") for r in reg_rows}
    kind_for = {r["id"]: _entity_kind_for(r.get("sourceType") or "") for r in reg_rows}
    status_for = {r["id"]: (r.get("collectionStatus") or "").lower() for r in reg_rows}
    enabled_for = {r["id"]: bool(r.get("enabled", True)) for r in reg_rows}

    _load_env(ROOT / ".env")
    store = RestStore()
    db_rows = store._request("GET", "ingest_source?select=id,entity_kind,source_kind,adapter_key,enabled&limit=5000") or []
    db = {r["id"]: r for r in db_rows}
    counts = _catalog_counts(store)

    errors: list[str] = []
    warnings: list[str] = []

    for sid in sorted(db.keys() - reg_ids):
        errors.append(f"db-only ingest_source: {sid}")

    for sid in sorted(reg_ids - db.keys()):
        st = status_for.get(sid, "")
        if any(mark in st for mark in NON_INGEST_MARK):
            continue
        if enabled_for.get(sid) and kind_for.get(sid) in ("programme", "research_job"):
            warnings.append(
                f"registry ingest-worthy without ingest_source: {sid} (sourceType={next(r.get('sourceType') for r in reg_rows if r['id'] == sid)})"
            )

    for sid in sorted(reg_ids & db.keys()):
        row = db[sid]
        adapter = row.get("adapter_key") or ""
        if adapter in ("unknown", "missing"):
            errors.append(f"placeholder adapter_key: {sid} -> {adapter}")
        if parser_for.get(sid) and adapter and adapter != parser_for[sid]:
            warnings.append(f"adapter_key vs registry.parser: {sid} (db={adapter}, parser={parser_for[sid]})")
        expected = kind_for.get(sid)
        if expected and row.get("entity_kind") not in (None, expected):
            errors.append(f"entity_kind mismatch: {sid} db={row.get('entity_kind')} expected={expected}")

    prefixes = set()
    known = set(reg_ids)
    known |= {r.get("employerId") for r in reg_rows if r.get("employerId")}
    known |= {r.get("institution_id") for r in db_rows if r.get("institution_id")}
    for tbl_sid, n in counts.items():
        _, sid = tbl_sid.split(":", 1)
        prefixes.add(sid)
        if sid not in known:
            warnings.append(f"catalog rows with unknown prefix: {tbl_sid} n={n}")

    print(f"registry={len(reg_ids)} ingest_source={len(db)} catalog_research_job+catalog_programme rows by prefix={len(counts)}")
    for line in errors:
        print(f"ERROR: {line}")
    for line in warnings:
        print(f"WARN:  {line}")

    if args.status_json:
        Path(args.status_json).write_text(
            json.dumps(
                {"registry": len(reg_ids), "ingest_source": len(db), "catalog-prefixes": dict(counts), "errors": errors, "warnings": warnings},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
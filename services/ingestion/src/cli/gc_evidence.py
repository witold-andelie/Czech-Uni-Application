"""Preview or apply unreferenced evidence deletion. Default is preview."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "ingestion" / "src"))

from cli.apply_schema import _load_env  # noqa: E402
from storage.budgets import EVIDENCE_GRACE_DAYS  # noqa: E402
from storage.postgres import load_database_env, rest_configured  # noqa: E402
from storage.retention import (  # noqa: E402
    MAX_DELETE_FRACTION,
    apply_evidence_gc,
    evidence_gc_blocked,
    preview_evidence_gc,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Garbage-collect unreferenced source-evidence objects")
    parser.add_argument("--apply", action="store_true", help="delete the previewed keys (off by default)")
    parser.add_argument("--grace-days", type=int, default=EVIDENCE_GRACE_DAYS)
    parser.add_argument(
        "--max-delete-fraction",
        type=float,
        default=MAX_DELETE_FRACTION,
        help="refuse to apply when more than this share of the bucket is unreferenced",
    )
    args = parser.parse_args()
    _load_env(ROOT / ".env")
    load_database_env()
    if not rest_configured():
        raise SystemExit("SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY required")
    from storage.evidence import EvidenceStore
    from storage.rest import RestStore

    store = RestStore()
    evidence = EvidenceStore()
    # A real deletion reads every reference table or stops (strict).
    preview = preview_evidence_gc(store, evidence, grace_days=args.grace_days, strict=args.apply)
    blocked = evidence_gc_blocked(preview, max_delete_fraction=args.max_delete_fraction) if args.apply else None
    if args.apply and not blocked:
        preview = apply_evidence_gc(evidence, preview)
    printable = dict(preview)
    printable["unreferenced"] = printable.get("unreferencedCount")
    printable["blocked"] = blocked
    print(json.dumps(printable, ensure_ascii=False, indent=2), flush=True)
    if blocked:
        raise SystemExit(f"evidence GC refused, nothing deleted: {blocked}")
    if args.apply and preview.get("failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

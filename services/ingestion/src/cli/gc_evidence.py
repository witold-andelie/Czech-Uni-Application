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
from storage.retention import apply_evidence_gc, preview_evidence_gc  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Garbage-collect unreferenced source-evidence objects")
    parser.add_argument("--apply", action="store_true", help="delete the previewed keys (off by default)")
    parser.add_argument("--grace-days", type=int, default=EVIDENCE_GRACE_DAYS)
    args = parser.parse_args()
    _load_env(ROOT / ".env")
    load_database_env()
    if not rest_configured():
        raise SystemExit("SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY required")
    from storage.evidence import EvidenceStore
    from storage.rest import RestStore

    store = RestStore()
    evidence = EvidenceStore()
    preview = preview_evidence_gc(store, evidence, grace_days=args.grace_days)
    if args.apply:
        preview = apply_evidence_gc(evidence, preview)
    printable = dict(preview)
    printable["unreferenced"] = printable.get("unreferencedCount")
    print(json.dumps(printable, ensure_ascii=False, indent=2), flush=True)
    if args.apply and preview.get("failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

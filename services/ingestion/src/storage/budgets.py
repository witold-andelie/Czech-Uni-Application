"""Internal free-tier headroom, not Supabase official quotas.

Official free-plan limits are about 500 MB database and 1 GB file Storage,
counted separately. These watermarks leave room so a collector can stop
non-durable uploads before the project turns read-only. They are never a
reason to drop still-open vacancies or shrink HEI coverage (A101).
"""

from __future__ import annotations

DB_WARN_BYTES = 300 * 1024 * 1024
DB_HIGH_BYTES = 400 * 1024 * 1024
STORAGE_WARN_BYTES = 600 * 1024 * 1024
STORAGE_HIGH_BYTES = 800 * 1024 * 1024
EVIDENCE_GRACE_DAYS = 30
KEEP_LAST_COMPLETE_RUN = True


def watermark(used: int, warn: int, high: int) -> str:
    if used >= high:
        return "high"
    if used >= warn:
        return "warn"
    return "ok"

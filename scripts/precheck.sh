#!/usr/bin/env bash
# Run what CI runs (.github/workflows/ci.yml), locally, before a push.
# 2026-10-02..04: 17 CI runs failed on checks that were never run locally
# (lint scope, web unit and contract tests, browser acceptance).
#   scripts/precheck.sh            data + Go + web + browser acceptance
#   scripts/precheck.sh --no-e2e   skip the Playwright browser run
set -euo pipefail
cd "$(dirname "$0")/.."
# Windows ships a "python" store alias that exists but does not run.
PY="${PYTHON:-$(python -c "import sys" >/dev/null 2>&1 && echo python || echo py)}"
E2E=1
[[ "${1:-}" == "--no-e2e" ]] && E2E=0

step() { printf '\n== %s\n' "$1"; }

step "Data and ingestion"
"$PY" -m pytest services/ingestion/tests tests/test_opm_generation.py tests/test_checkout_inventory.py -q
"$PY" -m ruff check services scripts tests
"$PY" scripts/checkout_inventory.py --check
"$PY" scripts/sync_locales.py
"$PY" services/ingestion/src/publish.py --check
"$PY" services/ingestion/src/publish.py --check-sources
"$PY" services/ingestion/src/check_programme_link_coverage.py
"$PY" services/ingestion/src/check_job_coverage.py
"$PY" scripts/check_framework.py

step "Go services"
(cd services/catalog && go test ./...)
(cd apps/api && go test ./...)

step "Web checks and static build"
(cd apps/web && npm test && npm run check && npm run verify:published && npm run build)

if [[ "$E2E" == 1 ]]; then
  step "Browser acceptance"
  (cd apps/web && npm run test:e2e)
fi

printf '\nprecheck: all CI checks passed locally\n'

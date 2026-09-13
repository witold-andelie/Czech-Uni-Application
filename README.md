# Czech University Application

A three-language (简体中文 / English / Čeština) anonymous browse platform for
study programmes and paid research positions at Czech public universities,
built for applicants evaluating Czech higher education.

**Live beta:** <https://witold-andelie.github.io/Czech-Uni-Application/>

## What it does

- **Degree programmes**: 5,019 register-recorded programmes across all 54
  MŠMT-baseline institutions, filtered teaching-language-first
  (English/Czech), with application windows, tuition where officially
  published, and official application links.
- **Paid research & doctoral positions**: reviewed vacancies harvested from
  official university career boards. Every published record passed
  evidence-bound fact review and real zh-CN/en/cs translation review.
  Postdocs are excluded from master's-entry and funded-doctoral filters by
  design.
- **Map**: all 54 institutions on MapLibre/OpenStreetMap with an offline
  bundled fallback.
- **Honest boundaries**: unknown facts (degree thresholds, salaries, dates)
  stay visibly unknown. The catalogue is a reviewed snapshot, not a claim of
  complete national vacancy coverage.

## Current release

- Publication `v2026-09-13.5`: **27 reviewed public jobs** (CZU 4, MUNI 4,
  Charles University 2, UHK 7, OSU 9, TUL 1), 4 reviewed admissions excerpts,
  54 baseline institutions, map coverage for all 54.
- Candidate pipeline: 150+ records under evidence-based per-record
  disposition (expired / blocked with reasons / awaiting trilingual review) —
  never silently dropped, never published without review.

## Architecture

| Layer | Technology | Runs where |
|---|---|---|
| Public site | TypeScript + Astro static output, Svelte islands | GitHub Pages (this repo) |
| Publication validation | Python + Node dual contract checks | offline / CI |
| Ingestion | Python (Scrapling) registry-driven discovery | offline, scheduled |
| Scheduler / API design | Go + PostgreSQL | separate deployment (planned) |

The public static site needs no database and stores no user data (anonymous
browsing only — no accounts, no tracking). Durable state for the future
refresh service is planned to run on **Supabase** (PostgreSQL) once that
deployment happens.

## Local development

```bash
cd apps/web
npm ci
npm run dev        # dev server, root-relative paths
npm test           # unit + contract tests
npm run check      # astro-check type gate
npm run build      # production build with base "/"
# Pages build with the repository prefix:
MSYS_NO_PATHCONV=1 SITE_BASE=/Czech-Uni-Application npm run build
node tests/pages-smoke.mjs   # browser smoke of dist under the prefix
```

Ingestion tests (Python 3.11+; deps in `services/ingestion/requirements-ci.txt`):

```bash
py -3 -m pytest services/ingestion/tests tests/test_opm_generation.py -q
```

## Deployment

GitHub Actions (`.github/workflows/ci.yml`) validates data, Go, web, and
browser acceptance on every push/PR. On `main`, a dedicated job rebuilds with
the repository prefix (`SITE_BASE=/Czech-Uni-Application`), runs a real
browser smoke **under that prefix**, then deploys the tested artifact to
GitHub Pages (source: GitHub Actions).

## Status and limits

- Public beta: data coverage is partial — a subset of institutions is fully
  reviewed; the per-school assessment and candidate-disposition pipeline is
  expanded release by release with per-record evidence.
- The refresh scheduler is **not** deployed; data updates are reviewed manual
  releases until the Go scheduler + Supabase state store ship.
- Mainland-China network paths and real-device checks are not yet verified.

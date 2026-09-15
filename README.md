# Czech University Application

A three-language (简体中文 / English / Čeština) anonymous browse platform for
study programmes and paid research positions at Czech higher education institutions,
built for applicants evaluating Czech higher education.

**Deployment:** Cloudflare Pages + custom domain; account setup pending.
GitHub hosts the source code and CI, not the public website.

## What it does

- **Degree programmes**: 5,019 register-recorded programmes across 53 of the 54
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
| Public site | TypeScript + Astro static output, Svelte islands | Third-party static host + custom domain (pending) |
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
# Production domain: set SITE_URL to the purchased domain's HTTPS origin.
# Keep SITE_BASE unset for a domain-root deployment.
```

Ingestion tests (Python 3.11+; deps in `services/ingestion/requirements-ci.txt`):

```bash
py -3 -m pytest services/ingestion/tests tests/test_opm_generation.py -q
```

## Deployment

GitHub Actions (`.github/workflows/ci.yml`) validates data, Go, web, and
browser acceptance on every push/PR. After all checks pass on `main`, it
retains the exact tested root-path build as `production-site-<commit>` for
14 days. Download and extract that artifact for third-party deployment;
`publication-provenance.json` identifies the commit and data snapshot.
GitHub Pages deployment has been removed.

Set the repository variable `SITE_URL` to the purchased domain's HTTPS origin
before the production build. The host must serve `index.html` for directory
URLs and the bundled `404.html` with HTTP status 404 for unknown URLs.
Do not enable a single-page-app catch-all rewrite.

### Connect Cloudflare Pages

Create a **Direct Upload** Pages project named `czech-uni-application` (not a
Worker, and not a second automatic Git build). In GitHub repository Settings →
Secrets and variables → Actions, configure:

| Type | Name | Value |
|---|---|---|
| Variable | `CLOUDFLARE_PAGES_PROJECT` | Actual Pages project name |
| Variable | `CLOUDFLARE_ACCOUNT_ID` | Account owning that project |
| Secret | `CLOUDFLARE_API_TOKEN` | Token scoped to that account, Pages Edit |
| Variable | `SITE_URL` | HTTPS temporary Pages URL, then purchased domain |

Run CI manually on main after saving the settings. The deploy job uses the
exact artifact that passed browser acceptance. It is skipped while the project
variable is unset; configuration alone is not proof of a live deployment.
Set the Pages production branch to `main`. Bind the purchased domain in the
Pages Custom domains screen and follow its DNS instructions. The requested
name is `czech-uni-application.online`; registration and payment remain pending.
Never commit API tokens or paste them into issues or logs.

### Scheduled collection

`refresh.yml` wakes twice per hour and executes only tasks due under the
existing 1/4/2-hour and five-day policies. A tick is bounded to 35 minutes;
individual tasks have a 15-minute ceiling. Source failures and deferred tasks
remain visible as failures and retain retry state. GitHub scheduling is best
effort, not an exact timing SLA. Paused/inactive workflows and exhausted quotas
require operator intervention.

The last two scheduler checkpoints are retained as Actions artifacts.
Candidate/evidence bundles expire after three days; download them for review
before expiry. They are not deleted on the next scheduler tick. Artifact storage
usage must be monitored against the account quota. Candidate files do not
overwrite source reviews in main. New jobs and
programme changes still need the existing evidence-bound three-language review
and immutable snapshot publication. Verified closure/status overlays can be
committed automatically, explicitly dispatch CI, and reach the same gated host
deployment. A bot push alone does not trigger another Actions push workflow.
No failed request becomes a closure. A concurrent main update rejects the bot
push rather than force-overwriting it; the next run retries from current main.

The frontend stays anonymous and static; no Supabase account or database is
required for this initial deployment. No paid hosting plan is enabled by these
workflows. Artifact/runner quotas still apply.

## Status and limits

- Public beta: data coverage is partial — a subset of institutions is fully
  reviewed; the per-school assessment and candidate-disposition pipeline is
  expanded release by release with per-record evidence.
- GitHub scheduled collection is configured; its first hosted result must be
  checked before claiming automatic collection is operational. New records
  require review; the persistent Go/Supabase service remains a later option.
- Mainland-China network paths and real-device checks are not yet verified.

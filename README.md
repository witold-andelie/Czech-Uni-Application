# Czech University Application

A three-language (简体中文 / English / Čeština) anonymous browse platform for
study programmes and research positions at Czech higher education institutions,
built for applicants evaluating Czech higher education.

**Deployment:** Cloudflare Pages at https://czech-uni-application.com.
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
- **Map**: all 54 institutions on a first-party Czech SVG basemap (14 kraje);
  MapLibre OSM tiles are an optional retry, not required for first paint.
- **Honest boundaries**: unknown facts (degree thresholds, salaries, dates)
  stay visibly unknown. The catalogue is a reviewed snapshot, not a claim of
  complete national vacancy coverage. Owner rule 2026-09-27 (A101): keep
  expanding coverage; do not drop still-open official vacancies when changing
  harvest, filters, publish or CI. Verified closures and dated expiry may
  leave the public list. New jobs still need trilingual review before a
  snapshot.

## Current release

- Publication **`v2026-09-27.6`**: 54 institutions, 5,019 register offerings,
  **2,889** with a school-owned programme page (matched rows, not a claim that
  every page was title-verified this run). 134 approved job records in the
  snapshot extract (unchanged; 6 withheld by live-evidence, not reported as
  closed), 4 reviewed admissions excerpts. The default jobs list count
  follows the visitor's clock.
- Harvest runs daily on GitHub Actions (`refresh.yml` full tick). That writes
  Supabase and a 3-day artifact; it does not switch the public snapshot.
  Official job sources are registered for part of the 54-university baseline;
  “no central listing found” is not “this university has no jobs.” No source
  currently supports an exhaustive institution-wide coverage claim.

## Architecture

| Layer | Technology | Runs where |
|---|---|---|
| Public site | TypeScript + Astro static output, Svelte islands | Cloudflare Pages + custom domain |
| Publication validation | Python + Node dual contract checks | offline / CI |
| Ingestion | Python (Scrapling) registry-driven discovery | offline, scheduled |
| Scheduler | GitHub Actions daily tick; Go scheduler optional later | GitHub-hosted |
| Admin console | Not built (owner 2026-09-27) | Review stays in git files |

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
`publication-provenance.json` identifies the commit, data snapshot, and GitHub
Actions run whose final result records the deployment outcome.
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
Pages Custom domains screen and follow its DNS instructions. The active
production domain is `czech-uni-application.com`.
Never commit API tokens or paste them into issues or logs.

### Scheduled collection

`refresh.yml` wakes once per day at 02:17 UTC in full mode and executes only tasks due under the
existing 1/4/2-hour and five-day policies. Manual **Run workflow** defaults to
`adapters` (about 8–15 minutes): it harvests registered HTML job adapters into
Supabase and skips programme catalogues and shards. Choose `full` only when you
need the complete tick. Each tick installs Scrapling 0.4.9
fetchers plus Playwright Chromium (`scrapling[fetchers]` then
`playwright install chromium`) so hard official pages use the same HTTP then
browser escalation as a local machine. A tick is bounded to 35 minutes;
individual tasks have a 15-minute ceiling. Source failures stay in the scheduler retry queue and the tick summary;
they do not fail the GitHub job after the checkpoint is saved. GitHub scheduling is best
effort, not an exact timing SLA. Paused/inactive workflows and exhausted quotas
require operator intervention.

Ingest keeps catalog identities and fact versions. Each source keeps only the
latest 14 process runs and their listing observations (`INGEST_KEEP_RUNS`).
Official HTML is hashed, not stored in Postgres, so the free-plan database
cannot grow with every daily harvest. HTML listing parsers share the adapter
engine; `python services/ingestion/src/cli/probe_job_sources.py` reports HEIs
still missing a registered job source without fetching the network unless
`--live` is passed.

The last two scheduler checkpoints are retained as Actions artifacts.
Candidate/evidence bundles expire after three days; download them for review
before expiry. They are not deleted on the next scheduler tick. Artifact storage
usage must be monitored against the account quota. Candidate files do not
overwrite source reviews in main. New jobs and
programme changes still need the existing evidence-bound three-language review
and immutable snapshot publication. Verified closure/status overlays are
committed automatically only from `main`; a feature-branch tick keeps them in
the candidate-review artifact and does not push to `main`. On `main` the bot
commit explicitly dispatches CI and reaches the same gated host deployment. A
bot push alone does not trigger another Actions push workflow.
No failed request becomes a closure. A concurrent main update rejects the bot
push rather than force-overwriting it; the next run retries from current main.

The public site stays anonymous and static. The GitHub Actions collector
writes durable ingest state to Supabase over **HTTPS Data API** (no dedicated
IPv4, no extra paid networking). Set repository secrets `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY`. Never put those values in `PUBLIC_*` variables
or browser JavaScript. Do not enable the paid Dedicated IPv4 add-on.
No paid hosting plan is enabled by these workflows. Artifact/runner quotas
still apply.

## Status and limits

- Public beta: data coverage is partial — published records are reviewed, but no institution
  has a verified exhaustive vacancy inventory; the per-school assessment and candidate-disposition pipeline is
  expanded release by release with per-record evidence.
- GitHub scheduled collection is configured with bounded tasks, persisted
  retry state, and per-source vacancy checkpoints. New records require review;
  the persistent Go/Supabase service remains a later option.
- Mainland-China network paths and real-device checks are not yet verified.

## Search discovery

Production builds emit `robots.txt` and `sitemap.xml` from generated localized
HTML, excluding legacy redirects and error pages. Set `SITE_URL` to the canonical
public origin (currently https://czech-uni-application.com). Shared pages emit
absolute canonical URLs, equivalent-language links, and factual WebPage metadata.
Submit `/sitemap.xml` through Google Search Console and Bing Webmaster Tools after
verifying domain ownership. Crawl eligibility does not guarantee indexing, ranking,
or citation by an AI service. No special AI-only content or fabricated reviews are used.

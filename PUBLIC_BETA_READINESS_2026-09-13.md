# Post-round-six review and GitHub public beta plan

Date: 2026-09-13. Scope: independent repair review and a short path to a public test site. No production code, source data, repository visibility, remote, or deployment was changed by this review.

## Decision

Proceed toward a **GitHub Pages static public beta** after the small release blockers below. Do not wait for a perfect national vacancy catalogue before testing the public UI, but do not describe this beta as comprehensive or continuously refreshed. Keep the full coverage work active as the first data iteration.

The existing Astro application is static. Anonymous browsing, client-side filtering, programme/job details and map fallback can run without a deployed Go API or PostgreSQL. Python acquisition remains offline. GitHub Pages serves the built files; it does not run the Go scheduler, API, database, or crawler. First deploy the reviewed snapshot through the existing publication gates. Deploy the background service separately when automated refresh is required.

## What improved, and what did not

| Area | Current review |
|---|---|
| Type error A89 | Independently rerun: 0 errors, warnings or hints |
| Web tests | Independently rerun: 101 passed |
| Ingestion + OPM tests | Independently rerun: 194 passed |
| Immutable publication | Integrity/business validation passes; still v2026-09-12.6 |
| Map height | The overriding min-height:0 was removed; independent two-worker browser run: 79 passed, including the new visibility tests. These do not explicitly prove both renderer modes after transition or actual MapLibre wheel zoom; strengthen the smoke checks accordingly. |
| Safety conflict handling | Same-generation conflicting content now preserves accepted closures; freshness aging still has a gap, B1 below |
| VŠB detail | Existing candidate is enriched rather than duplicated; still awaiting review/publication |
| UTB bundle | Conservative quarantine improved, but salary-ratio heuristic is not a role parser, B4 below |
| Source coverage | Unchanged: 13 registered/executed, 9 registered/no successful execution, 32 not assessed; not 54 completed university scans |
| Public results | Unchanged: 10 jobs across CZU/MUNI/Charles, plus 4 reviewed admissions excerpts |
| Assessment/disposition tables | Useful operational starting point, not completed human source assessment or review |
| CI/deployment | CI workflow exists locally; no Git remote; hosted runs and deployment not verified |

Evidence: `work/predeploy-2026-09-13/{astro,web,python,build,e2e}.log`, current `data/sources/coverage/job-source-assessment.json`, active publication pointer. The sixth-round audit remains historical evidence and was not rewritten.

## Remaining findings

### B1 — Fix before beta: accepted fresh heartbeat never ages on identical replies

In `apps/web/src/lib/safetyStatus.ts`, the equal-generation/equal-content branch calls `fire(accepted, lastStale)`. It does not reevaluate the heartbeat against the current clock. The independent `work/predeploy-2026-09-13/safety-aging.mjs` probe accepts a heartbeat at 10:00, advances to 10:31 with the same payload and obtains `stale:false` twice. This violates the configured 30-minute threshold.

Recompute heartbeat expiry on every poll/focus observation. Preserve conflict and failure conditions deliberately; do not restore the earlier behavior of clearing stale merely because HTTP succeeds. Add a deterministic test: initial fresh -> identical reply after threshold -> stale; valid newer verified generation -> fresh. Keep closures through all errors. Update the stale baseline comments that still describe the superseded exemption.

The checked-in overlay has sourceCheckedAt=null. This must remain “verification unavailable” until real official checks occur. Do not manufacture a current timestamp at build/deploy time. Reconcile the configured heartbeat tolerance with the one-hour status-check target during scheduler deployment; a 30-minute threshold cannot represent a healthy one-hour source-check cycle without an explicitly defined heartbeat contract.

### B2 — Fix for the chosen Pages address: root-relative routing and data fetches

`astro.config.ts` has no site/base configuration. Examples of root assumptions:

- `loadCatalogClient.ts` fetches `/data/published/<version>/...`.
- `safetyStatus.ts` fetches `/data/safety-status.json`.
- `nav.ts` creates `/<locale>/<page>`.
- `localePath.ts` interprets the first path segment as the locale.

For a project site at `https://OWNER.github.io/REPOSITORY/`, these escape the repository prefix; setting Astro base alone is insufficient. Account-root hosting at `https://OWNER.github.io/` avoids the prefix migration for the fastest beta, if that account's root site is available. A custom domain also avoids it but is unnecessary for this first test.

Once the owner/repository is known, choose one route strategy explicitly:

1. Account-root site: repository named OWNER.github.io, base `/`, correct site URL. Verify the existing root site is not being replaced.
2. Project site: centralize base-aware internal URLs, apply to navigation, locale switching, assets, JSON fetches, redirects, error routes and deep-link recovery. Keep external official URLs untouched. Test under the actual nonempty prefix, including query preservation.

Official Astro guidance confirms project sites need base-prefixed internal links: [Astro GitHub Pages deployment](https://docs.astro.build/en/guides/deploy/github/).

### B3 — Fix before push: local file presence is not a reproducible Git checkout

The current branch is main, with no configured remote. `git ls-files` returned no tracked entries for `.github`, `data/published/current.json`, or `apps/web/src/lib/safetyStatus.ts`; these critical additions appear as untracked files. `checkout_inventory.py --check` tests filesystem presence, not membership in the intended commit. Its success is not proof that a fresh GitHub checkout builds.

Prepare a reviewed commit containing runtime source, pinned dependency files, fixtures required by tests, workflow, required source/review data, active immutable snapshot and safety data. Exclude raw crawl output, local binaries including server.exe~, process locks, temporary staging, caches and arbitrary work scripts. Some tests may depend on fixtures currently under work; move deliberate fixtures to tests/fixtures or explicitly document them before excluding work wholesale. Inspect staged paths and repository size; do not use a blind add-all on this workspace.

Run CI-equivalent commands in a fresh checkout of that exact commit. A reviewed commit plus clean-checkout pass is the release input, not the dirty developer directory. Do not publish the whole repository as the Pages artifact; upload only `apps/web/dist` after testing it.

### B4 — Follow-up data fix: numerical similarity cannot establish role identity

The bundle mitigation uses a salary ratio below 0.7 to identify distinct statements. A probe with assistant A at 40,000 CZK/month and assistant B at 50,000 CZK/month returns a single 40,000 amount and no ambiguity reason. Conversely, one role can legitimately have a wider range or FTE-dependent pay.

Use role/section identity and evidence spans, not amount ratio, to associate pay, start date, FTE and qualifications. Keep unresolved bundles out of formal publication. This should not block serving the existing reviewed snapshot, but must be resolved before publishing newly split UTB-like records.

### B5 — Follow-up operator fix: ledger blockers conflate unknown facts with publication rules

`build_disposition_ledger.py` marks every unspecified doctoral enrollment and unknown degree as a blocker. It also calls missing catalogueScopeStatus “unspecified scope,” even where legacy publication semantics may differ. Unknown enrollment is a truthful field state, not automatically proof a job is ineligible for every public category. Public membership short-circuits all blockers, so the ledger also cannot independently detect stale candidate reviews for already public IDs.

Separate actual publisher gate failures, reviewer warnings, and eligibility for the master's/funded filters. Derive strict blockers from the same validation contract as publication, preserve unknowns, and report candidate-vs-publication fact differences explicitly. Sort by measured underrepresentation if that prioritization is claimed; current ordering is deadline, employer ID, candidate ID. The current ledger is a starting queue, not 80 completed review decisions.

## Minimal deployment sequence

1. **Resolve B1 and the final URL strategy.** Obtain the GitHub owner/repository and whether source visibility should be public. GitHub Free supports Pages from public repositories; private-repository Pages depends on plan. Do not change visibility implicitly. [GitHub Pages availability and limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
2. **Prepare a clean release commit (B3).** Run unit/type/data checks and build; test the actual URL prefix. Confirm only the reviewed publication enters browser assets. Check that no runtime call depends on localhost or a nonexistent API.
3. **Extend the existing CI, preserving its gates.** After data, Go, web and browser checks pass, download the already-tested site artifact, package it with upload-pages-artifact and deploy with deploy-pages. Configure Pages source as GitHub Actions. Use a github-pages environment, job-scoped pages:write/id-token:write, and main-only deployment. PRs validate without deploying production. Pin official actions to verified commit SHAs when implementing. See [GitHub custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
4. **Deploy the tested artifact once.** Do not use a second untested build for deployment. Record commit SHA, active publication, safety generation, Actions run and returned page URL. Preserve the prior good release for rollback. Ensure cancelled/older deployments cannot overtake newer successful releases.
5. **Run public smoke checks.** Root entry and all three locales; English/Czech programme separation; nonempty inventory fetch; CZU/MUNI search; funded filter; direct programme/job links; official application buttons; map at phone/desktop with tiles working and blocked; actual wheel zoom without Ctrl; 404 recovery; legacy saved/compare routes; no accounts; no console/data-request errors. Verify dates/coverage notices under the real hosting URL. Check a phone and mainland network when available, otherwise label those unverified.
6. **Start short feedback iterations.** Use a small issue template: URL, locale, device, expected/actual result and publication version. Give testers the public URL; no account system or feedback database is needed. Keep developer issues in GitHub. Patch through PR -> checks -> main -> Pages, rerun public smoke after each release.
7. **Expand data in the next iteration.** First execute the nine registered/no-success schools and assess ZČU, then complete all remaining baseline institutions. Review near-deadline cross-school opportunities and CZU in parallel operational priority, without bypassing trilingual review. Publish through immutable snapshots and show per-school before/after counts with unresolved reasons.
8. **Deploy refresh separately.** To meet the requested 1h/4h/2h/120h policies without relying on a personal computer, deploy the Go scheduler plus offline Python workers and durable state. Until then, manual acquisition/review/release is acceptable for beta only and must be described honestly. Do not silently replace the specified Go scheduling design with an unverified GitHub cron workflow or claim Pages makes data live.

## Capacity and iteration cost

The independently rebuilt dist measured **203,546,792 bytes (~194 MiB), 15,335 files**. Build succeeded with 15,299 pages in 1m38s; browser acceptance passed all 79 cases in 33.3s at two workers. That is below Pages' **1 GB published-site limit**. Page count does not by itself require an architecture rewrite before beta. Pages also documents deployment timeout and bandwidth limits; measure the real Actions deployment and public transfer rather than extrapolating from total site size. [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).

Most visitors load only a few pages, not the entire build. Defer build-size refactoring until actual build/deploy or browser measurements justify it. Avoid bundling raw acquisition archives into the site. Preserve immutable asset versioning and show snapshot/verification timestamps separately.

## Owner input still required for actual deployment

GitHub account or repository URL, source visibility preference if creating a repository, and availability of the account-root Pages site. This review has not created a remote repository, pushed code, changed visibility or deployed. Once the target is known, the URL-specific configuration and final release workflow can be prepared and reviewed concretely.

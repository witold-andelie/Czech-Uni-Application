# Czech Uni Apply — Sixth comprehensive audit

Audit date: **13 September 2026, Europe/Budapest**. Evidence timestamps immediately after local midnight are **12 September UTC**, not inconsistent dates.

Audience: implementation agents and the project owner. This is an evidence-based handoff, **not an implementation or deployment approval record**. The active publication inspected is `v2026-09-12.6`. This audit changed no production parser, source registry, publication, or application code. Existing uncommitted work was preserved.

## 1. Direct answer: why are paid jobs concentrated in a few universities?

**The project has not demonstrated a complete Czech university vacancy scan.** It has a national university/programme baseline, but its vacancy acquisition and publication coverage remain partial. These are separate systems and must never share a completeness claim.

| Pipeline measure | Observed result | Meaning |
|---|---:|---|
| MŠMT institution baseline | 54 | All baseline institutions exist locally; not proof their careers sites were scanned |
| Institutions with registered official job sources | 22/54 (40.7%) | Connection only; not whole-university assessment |
| Institutions without registered job sources | 32 | Vacancy availability unknown |
| Registered institutions with no scheduler success timestamp | 9/22 | No successful scan demonstrated by this state |
| Fully assessed institutional job scopes | 0 | No documented complete faculty/lab/channel inventory |
| Registered official listing sources | 24 | Includes faculty/network scopes; not 24 distinct universities |
| Latest candidate discovery complete-source set | CZU only | Cannot establish all-source completion |
| Last all-source success | null | No durable proof of an all-registered-source successful sweep |
| Stored candidate records | 128 | Includes historical/archived records |
| Current candidates | 90 | Operational non-closed/non-archived predicate; not 90 confirmed open vacancies |
| Current supported-scope candidates | 77 | Of these, coverage reports 69 review-pending and 8 approved |
| Current unspecified-scope candidates | 13 | Must be investigated, not silently discarded |
| Published jobs, all tracks | 10 | CZU 4, MUNI 4, Charles University 2 |
| Published paid bachelor/master-scope jobs | 8 | CZU 4 and MUNI 4; Charles jobs are postdocs |

The coverage report's **8 approved** is scoped to its 77 supported candidates; the immutable snapshot's **10 public** includes both Charles postdocs. Do not describe this as 69 out of all 90 or assume every pending candidate qualifies for publication.

The previous fixes made a real improvement: public jobs doubled from five to ten, and the four MUNI examples now appear. However, **all five additions came from already-prioritized universities**. Expanding a reference sample is not a national recall strategy. Concentration reflects at least four bottlenecks: missing source registration, incomplete execution, extraction losses, and concentrated review throughput. Genuine differences in hiring volume may also exist, but this dataset cannot measure them reliably.

Evidence: [independent inventory and input hashes](work/audit6-2026-09-13/inventory.json), [54-school matrix](work/audit6-2026-09-13/school-matrix.md), [active pointer](data/published/current.json), [coverage report](data/sources/coverage/source-coverage.json). Matrix generation reads the active immutable snapshot, not the obsolete legacy current directory.

## 2. Scope, method, and limits

Read the project/product/data/crawling/UI/i18n/acceptance and OPM rules, the fifth audit and progress notes, current implementation, candidate data, source registry, scheduler state, immutable publication, CI workflow and browser tests. Independently ran the checks below, replayed the live generic parser against saved official pages, and captured constrained map screenshots.

Five official pages were fetched successfully with installed Scrapling into the audit directory, with timestamp and SHA-256 evidence: UTB bundled vacancy, UTB scientific vacancies index, VŠB doctoral advert 61, VŠB QUESTING announcement, and TUL careers index. See [fetch manifest and parser outputs](work/audit6-2026-09-13/official-probe.json). These are **targeted samples**, not a newly executed 54-university crawl. A HTTP 200 is neither an open vacancy determination nor proof of all pages being exhausted. No application forms were submitted.

The scan conclusion follows the registry and operational evidence; it does not assert that no earlier ad hoc request to a missing institution ever happened. No production deployment, hosted GitHub run, branch protection, uptime, or live Go scheduler was verified. Several old temporary directories are unreadable under the workspace sandbox. Do not infer successful historic execution from an inaccessible directory or from source registration alone.

## 3. Fifth-round repair assessment

“Verified for examples” means the tested examples pass; it does not mean every institution's pages are covered.

| Fifth finding | Sixth-round disposition |
|---|---|
| A67 Salary number parsing | Improved: separators/ranges and unspecified cycle now supported; published example values no longer show the old zero/default-month defect. New bundled-role association problem remains, A85. |
| A68 Doctoral enrollment/funding | Improved for MUNI examples; generic full-body scoping still loses another university's facts, A84. |
| A69 Candidate replay | Replay/provenance implementation and tests exist. Reprocessing old HTML does not discover absent URLs or update source freshness. |
| A70 Review/publication backlog | Five targeted additions verified, national backlog unresolved, A83. |
| A71 CZU alias/search | CZU/ČZU and MUNI positive-set unit tests pass; funded filter exists. Not sufficient browser or cross-university recall evidence, A90. |
| A72 Institution source map | Not completed: 22/54 registered, zero fully assessed, A82. |
| A73 Funded doctoral admission routes | Not completed nationally. Keep admission/funding/job relationships explicit rather than counting programmes as vacancies. |
| A74 Clock-sensitive cooldown | Injected-clock tests pass in the 183-test Python suite. |
| A75 Review rebinding | Guard and changed-evidence tests pass; preserve this gate when expanding publication. |
| A76 Safety status | Partial repair followed by regression: older-generation rejection exists, but same-generation content/age handling is unsafe; also a type-check failure, A87/A89. |
| A77 Coverage metrics | Source attribution and claim wording improved. Actual latest per-source run records remain empty; timestamps are not run completeness, A86. |
| A78 Browser/content tests | Broader suite exists and passes at two workers. It misses zero-height maps and hard-codes the mutable publication's example IDs, A90. |
| A79 Selected-school clipping | The tested CZU card is now in normal flow on small/short screens; old clipping is improved. New zero-height interactive map reproduced, A88. |
| A80 Anonymous browse only | Navigation/actions/legacy routes pass removal tests. Documentation still promises accounts and asks for compare/save acceptance, A91. |
| A81 Crawl orchestration | Comprehensive origin scheduling/conditional refresh/coverage work not delivered. Do not replace the crawler merely to change libraries. |

## 4. New or continuing release-blocking findings

### A82 — P0: national vacancy coverage is still not an executed deliverable

**Evidence:** 32 institutions lack a registered job source. This includes Západočeská univerzita v Plzni (ZČU), the four public art academies, all 26 private institutions, and Police Academy. Among registered institutions, UJEP, VETUNI, OSU, UHK, SLU, TUL, VŠPJ, VŠTE and University of Defence have no successful scheduler timestamp. The institution matrix enumerates all 54, including legitimate zero/unknown states.

**Impact:** The public search cannot support a national completeness claim. Adding central URLs alone will not resolve faculty, laboratory, grant-network and doctoral funding channels. Neither a rankings list nor a list of English sites is an acceptable denominator.

**Required outcome:** a versioned 54-row assessment plus per-institution scoped source graph and executed run receipts. Record “no separate careers portal found after documented assessment” and “verified zero listings in this scope” separately from “not assessed,” “failed,” and “partial.” A failed fetch must never become zero vacancies.

### A83 — P0: publication throughput remains focused on three institutions

**Evidence:** 69 current supported candidates remain review-pending; 13 current candidates have unspecified scope. Examples with current candidate records but no public jobs include CTU (17), VUT (10), JCU (9), UTB (8), UCT (7), VŠB (5), UPCE (4), MENDELU (4), UPOL (2) and VŠE (1). These counts include uncertainty and are not promises that all can be published.

**Required outcome:** a candidate disposition ledger with one decision per record: accepted, excluded with evidence, expired/closed, duplicate, facts missing, translation missing, or blocked by a source failure. Prioritize close deadlines and underrepresented institutions while preserving CZU attention. Publication gates must still verify evidence-bound facts and zh-CN/en/cs review. Never copy Czech/English text into three locale fields and call it reviewed. Do not weaken pay/eligibility gates to make the public count rise.

### A84 — P0: a VŠB doctoral candidate lacks its detail link, and generic scoping truncates its facts

Official sample: [VŠB advert, procedureId=61](https://www.vsb.cz/en/university/informational-board/job-opportunities/advert/index.html?procedureId=61). The fetched advert describes a PhD research role involving SEM and 2D materials, a fixed-term full-time contract, competitive salary, English working language, and a 20 September 2026 application deadline. Exact pay and a completed-degree threshold are not stated clearly enough to invent. Its detail URL is absent from the candidate file and public snapshot. However, existing candidate job-vsb-cnt-phd has the same PhD title, CNT laboratory and 20 September deadline, strongly suggesting it is the same opportunity. It points only to the generic English job index, remains paid-unconfirmed/review-pending and is not public. Resolve identity and enrich it; do not create a duplicate.

Current `parse_generic_job_page` produces `paidStatus=unconfirmed`, null deadline, null FTE/start, and unknown degree. The full visible text is **8,140 characters**, while `entity_scope(..., 'PhD student')` returns **1,123**. It cuts at the same advert's **Job Description** section; the pay, contract and deadline are later. The heuristic treats an internal section as a neighbouring vacancy boundary. This is a deterministic extraction defect, not a missing translation.

Evidence: [official probe](work/audit6-2026-09-13/official-probe.json), [truncated scope](work/audit6-2026-09-13/vsb-scoping.txt), [parser](services/ingestion/src/harvest_nine_hei_jobs.py). **Do not claim the exact discovery failure is localized:** the registered source is Czech, this positive sample is English, and a full current bilingual listing traversal was not run here. Verify language variants, card pagination, sub-unit sources and detail URL selection. Replay of an old index cannot substitute for fetching and linking the current detail. The old candidate already contains a deadline; the null deadline described above is the fresh generic parser output, not the stored window.

### A85 — P1: multi-position announcements still lose role-specific facts

Official sample: [UTB population protection recruitment](https://kariera.utb.cz/akademicti-pracovnici-akademicke-pracovnice-na-ustavu-ochrany-obyvatelstva/). One announcement contains a completed-doctorate role and assistant roles where starting doctoral study is advantageous rather than mandatory. It associates different FTEs, salaries and start dates with those roles, with a shared 28 September 2026 deadline. Do not convert “university education” to a proven master's minimum without evidence.

Candidate `job-28000-52bc40c455e4` is a `notice_bundle`: degree/enrollment remain unknown, but salary is a single 20,000 CZK gross amount and employment start is 2 November 2026. This combines only one role's values with a multi-role title. The existing quarantine/unknown-degree approach is safer than publishing false eligibility, but leaves recall unresolved.

**Required outcome:** distinguish notice identity, role identity and explicitly stated number of openings. Split only where sections support stable, separately attributable facts. Retain shared evidence, application target and deadline. Never label a bundled salary as applying to every role; never multiply list cards solely to inflate vacancy totals. Add a rule for ambiguous bundles to remain reviewable with explicit blockers.

### A86 — P0: configured refresh intervals are not fresh execution evidence

`work/runs/schedule-state.json` was last updated 11 September 20:25:25 UTC. Coverage reports discovery success at that time and known-job recheck success at 19:43:39, roughly **27 and 28 hours old** at audit observation, against 4h/1h targets. Programme sources were last successfully refreshed around 19:30–19:34 that day against 2h targets. The safety overlay has `sourceCheckedAt=null`. Source replay on 12 September must not reset these acquisition clocks. Full-shard success timestamps are null in the inspected state.

There is also a code-level completeness gap in `worker.py` around the discovery source-result aggregation: success is based on all *observed attempts* being OK and `failed_sources` being empty; the success branch can assign `lastAllSourceSuccessAt` without proving expected IDs equal complete IDs and that deferred IDs are empty. An empty or incomplete successful-attempt set must not advance all-source success. This is a static control-flow finding; add the explicit counterexample tests before changing behavior.

**Required outcome:** independent durable receipts for each source and run, complete/deferred/failed sets, pagination exhaustion, actual source-check timestamps and last all-source coverage. Preserve partial success without claiming global completion. Connect the existing Go scheduling design to real executed service evidence before advertising automated freshness. Browsers should show unavailable/stale verification honestly, not imply “live” because a static JSON file responds.

### A87 — P0: same-generation safety replies can erase closure and clear staleness

The independently executed [safety probe](work/audit6-2026-09-13/safety-probe.mjs) yields [these events](work/audit6-2026-09-13/safety-results.json):

1. A day-old initial generation containing a closed job is reported `stale=false`.
2. An empty payload with the **same generation ID** replaces it, dropping the closed entity.
3. An older-timestamp higher generation is first `stale=true`, then the identical repeated response becomes `stale=false`.

`subscribeSafetyOverlay` rejects lower generations but assigns `accepted=parsed` for equal generations and treats first/equal replies as fresh. Reachability proves transport success, not a recent university recheck. Static closure events may legitimately persist for days; distinguish their age from a source-verification heartbeat rather than aging everything or disabling aging entirely.

**Required outcome:** immutable generation/content binding; equal generation with conflicting content must preserve closures and signal an error. Define freshness from a validated independently advancing source-check heartbeat, including null/invalid/future timestamps and per-source failures. A repeated body cannot clear a stale-source condition. Keep prior known closures through errors. Test initial stale content, equal-conflicting content, lower generation, delayed higher generation, heartbeat expiry and recovery separately.

### A88 — P1: the mobile interactive map collapses to zero height

At **390×844, Czech locale, valid stubbed tiles**, the actual renderer is MapLibre but `.map-viewport-container` height is **0**. The selected CZU card is visible and page width remains 390; the map itself has disappeared. See [full-page screenshot](work/audit6-2026-09-13/map-cs-390-844-stub.png) and [geometry](work/audit6-2026-09-13/map-results.json). This was visually inspected, not inferred from a test count.

In `InstitutionMap.svelte` around lines 915–925, the same rule declares a `min-height: clamp(...)` and then `min-height: 0`. The latter wins. MapLibre's absolute child gives an auto-height grid track no intrinsic floor on the narrow layout. The SVG fallback has intrinsic content and can conceal this defect. Desktop row stretching can also hide it.

**Required outcome:** one effective responsive nonzero map height rule; normal-flow selected card on small/short screens; no clipping/overflow. Test renderer area **and** the card, before and after selecting/closing, at all three locales and 390×844, 1280×500, 1440×600, 1440×900. Stub tile success and force tile failure separately. Verify actual mouse-wheel zoom without Ctrl in both modes; code currently sets `scrollZoom:true` and `cooperativeGestures:false`, but this audit did not separately measure wheel-induced zoom changes.

In the short-screen probe some hit-test points lie below the viewport after scrolling the map into view. That alone is **not occlusion**: the card is now normal-flow and scrollable. Do not “fix” ordinary scrolling by moving everything back into a clipped overlay. The old map integration decision is respected.

### A89 — P0: current type check fails, so the release is not green

`npm run check` fails with TS2345 at `apps/web/src/lib/safetyStatus.ts:242`: `[string, number] | null` is passed to `isGenerationAtLeast`. The boolean alias `isInitialAccept` does not narrow the mutable nullable value for this call. `buildJobViews` also has an unused-import hint in the published search test. Production build succeeds because it is not a substitute for the type-check gate.

**Required outcome:** narrow a stable non-null local explicitly; do not silence with `as`, `!`, or disable checks. Rerun unit tests and Astro check, including the repaired A87 semantics. CI already invokes the failing check. PROGRESS's earlier “zero errors” must not be reused as current verification.

### A90 — P1: acceptance tests do not measure the core recall and visibility outcomes

The 54-test browser suite passes with two workers while A88 is present. The constrained-map test asserts a selected card, not visible map area. Some tests click an SSR-visible element before its client handler is ready: the initial high-concurrency run lost selections/drawer opening. Exact-ID “golden” assertions in `jobSearchPublished.test.ts` read the changing active publication but pin time to 12 September and assume fixed MUNI/funded result sets. A legitimate additional funded position or closure can break CI, while omitted other-school vacancies do not.

**Required outcome:** immutable dated HTML/catalog fixtures for exact regression sets; separate active-publication integrity checks and live-audit disposition checks. Browser assertions must exercise actual search URLs/filters and compare expected IDs under a fixed fixture. Add a hydration-ready behavior contract and slow-client test rather than arbitrary sleep or repeated clicks. Fix PowerShell CLI argument forwarding in documented test commands. A green test suite must include the A84/A85/A88 counterexamples.

### A91 — P2: documentation and delivery claims drift from the product

README still describes v2026-09-12.4 with five jobs. PRODUCT still promises account synchronization; I18N_RULES still asks users to complete comparison and saving. Those contradict the owner's anonymous browse-only decision. UI removal tests pass, but another agent following these documents could reintroduce forbidden scope.

The GitHub workflow checks/builds/tests and uploads a delivery artifact; **it has no public deployment step**. This is useful CI/delivery configuration, not demonstrated continuous deployment or a running refresh service. Hosted execution was not checked. Preserve honest status and provide release/run evidence rather than changing the label to “CI/CD complete.”

## 5. Detailed next-round implementation instructions

Execute in this order. Work on small reviewable changes. Do not repeatedly polish the same five sample vacancies and call the national goal complete. Each task must include its evidence file and acceptance result in the handoff. If parallel agents are used by the next operator, assign disjoint file ownership and one publication integrator; this audit itself did not delegate work.

### Task 0 — Establish a reproducible baseline and restore release gates

1. Read AGENTS and the required documentation in order, then PROGRESS and this report. Record HEAD, dirty paths, active pointer and the input hashes. Preserve the current user's modifications; do not reset or stage unrelated work.
2. Fix A89 with explicit null narrowing, then A87 with deterministic fake-clock tests. Keep the prior closed overlay when responses conflict or fail.
3. Fix A88's actual height collapse; verify MapLibre and SVG separately. Save before/after screenshots and measured map/card rectangles.
4. Run the affected tests, Astro check and immutable-publication validation. Do not publish while any required gate fails.
5. Correct scope documents per A91 and synchronize OPM object/state/process relations and requirement traceability if changed behavior requires it. Never reintroduce accounts, comparison or saving.

**Exit:** type check green, safety counterexamples pass, map area nonzero on the full stated matrix, published snapshot unchanged unless an intentional reviewed release follows.

### Task 1 — Build the missing national source assessment, not another URL list

1. Seed exactly the 54 baseline IDs from the appended matrix. Keep ownership and canonical domains. Mark existing registered sources as unassessed until their scope is demonstrated.
2. For each institution inspect official Czech and English careers pages, faculty/research-centre units, notice boards, doctoral admission/funding calls and externally hosted recruitment systems linked from the official website. Use the faculty register to enumerate units; do not assume a central board aggregates every lab.
3. Begin with the nine registered/no-success institutions and ZČU, while maintaining CZU and short-deadline sources. Complete art/private/state assessments as well; they are not optional because expected yields are lower.
4. Record each official URL, parent/authority evidence, source type, scope, language, adapter, pagination method, rate constraints, last assessment and next check. Separate university research employment from student/employer job boards and non-university AVČR sources.
5. For no detected jobs, retain scoped negative evidence, including pages exhausted and check time. For blocked sites record error/retry; use installed Scrapling as required. Do not fabricate a source or claim full coverage from a search-engine snippet.
6. Commit the assessment artifact and source registry changes together, with explicit unresolved units. Every one of 54 rows must have a supported assessment or named blocker. A connection-only metric must remain separate.

**Exit:** 54/54 assessment rows; no unlabelled institution; source graph and adapters sufficient to attempt each supported scope. This is necessary but still not completion of a crawl.

### Task 2 — Turn source assessment into executed, auditable scans

1. Snapshot the expected source IDs at run start. Allocate a run ID and per-source start/completion timestamps; retain registry/parser version.
2. Fetch each source with per-origin throttling, bounded concurrency and persisted cooldown/retry. Prefer public JSON/API/RSS where the official site links or uses it; use static HTML then targeted browser rendering as needed. Keep requests outside the online user search path.
3. Follow pagination to a proven terminal state. Record response/item counts and visited URLs; detect repeated page tokens, silent parser-zero pages and unexpectedly missing sections. Support ETag/Last-Modified where safe, but only accept 304 against a known successful cached representation/parser context.
4. Fetch full details and linked official attachments where qualifications reside. Canonicalize Czech/English/portal URLs before deduplication, preserving source provenance. Do not infer that different language listings have identical vacancy sets.
5. A complete all-source result requires expected IDs all accounted for as complete, no deferred/failed work, and completed detail scope. Explicit scoped zeros are allowed. Missing IDs/zero attempts cannot advance all-source success. Add those worker tests.
6. Store receipts atomically under the existing locking convention. Keep per-source successes through partial failures; preserve last all-source success until another complete sweep actually finishes.
7. Demonstrate one real sweep and a repeat incremental run with evidence, then show execution of 1h status/4h job discovery/2h volatile programme schedules and the 120h baseline policy. If the service is not deployed, state that these are local runs only.

**Exit:** each assessed source has a current terminal result or explicit blocker; observed discovery recall can be traced from listing item through details to candidate IDs. No national freshness claim while blockers or overdue sources remain unreported.

### Task 3 — Repair extraction with real missing-school counterexamples

1. Freeze the VŠB advert HTML from this audit as a dated fixture. Add a failing test that retains Job Description, employment, salary and deadline sections within one vacancy. Use DOM-level article/section boundaries rather than flattened generic words to delimit adverts.
2. Expect confirmed paid employment evidence, full-time 1.0, 2026-09-20 deadline and 2026-10-01 start where supported. Leave numeric pay and unproven degree unknown. Verify source closure/window separately before any publication.
3. Investigate the current VŠB listing graph in both languages, prove where advert 61 is discovered and map its canonical ID. Add an end-to-end saved listing → detail → candidate test; a standalone parser test is insufficient.
4. Freeze the UTB bundle fixture. Segment role facts and retain a shared notice parent. Assert doctorate requirement only on the correct role, “doctoral study advantageous” is not required, and pay/FTE/start values do not cross between roles.
5. Reprocess affected stored raw pages with the new parser version. Generate a facts diff and invalidate only reviews whose bound facts/evidence changed. Preserve original sourceFetchedAt. Discover and associate detail URLs in a real scan; do not confuse replay with acquisition.
6. Add negatives: unrelated navigation words, closed results, another advert's deadline, no numeric salary, multiple roles with different dates, and legitimate unknown minimum degree. Keep page/headcount/role counts distinct.

**Exit:** both official positive examples have explainable candidate dispositions and correct fact extraction; previously reviewed MUNI/CZU regressions still pass.

### Task 4 — Clear the publishable backlog across institutions

1. Export the 90 current candidates plus newly discovered records into a disposition ledger; separately identify the 77 currently supported and 13 unspecified rows. Recompute counts at task start, as this audit's numbers will age.
2. For each record verify live official availability, paid evidence, minimum education, doctorate possession and enrollment, working language, official application target, deadlines/rounds and whole-opportunity closure.
3. Review underrepresented schools and near deadlines first, alongside CZU. Review full original facts and provide actual zh-CN/en/cs text with evidence-bound hashes. Never auto-approve or rebind a changed fact hash merely to pass the publisher.
4. Keep supported but uncertain records visibly blocked in the operator ledger. Do not expose fake completeness to public users. Record exclusions and duplicates so low public counts remain explainable.
5. Build a candidate publication; run --check-sources, immutable validation and three-locale search/detail acceptance. Produce a per-school before/after table: discovered, current, eligible, reviewed, public, excluded, unresolved, overdue.
6. Activate only through the established atomic publication path and record manifest/version/rollback target. Avoid direct edits to immutable snapshots. Closure status must propagate without waiting for new translation work.

**Exit:** no candidate silently abandoned; every missing official positive has a reason or reviewed public result. Success is truthful recall with evidence, not a preset total or uniform distribution across schools.

### Task 5 — Include funded doctoral pathways without conflating them with jobs

1. Assess doctoral school, lab recruitment and grant-network channels for each relevant institution. Preserve the evidence for institutional affiliation and funding.
2. Distinguish employment, stipend and mixed funding; general admission availability is not a salaried vacancy. Keep programme, opening/role and funding-call identities linked but separate.
3. Evaluate registration requirements from the full advert. R1, “PhD” in a title and a degree programme name are not sufficient alone.
4. Map application rounds and funding conditions to the correct call. A past priority deadline with “until filled” needs current evidence rather than an invented open flag.
5. Test the public funded filter against controlled fixtures and add cross-school examples only when supported. Keep working-language conditions separate from programme teaching languages.

**Exit:** a source-backed pathway can be found in the appropriate public category without double-counting a programme as a job or implying a stipend is a salary.

### Task 6 — Close the loop with CI and operational evidence

1. Keep frozen fixture recall tests separate from assertions on the changing active snapshot. Active checks validate consistency and review contracts, not forever-fixed MUNI counts.
2. Run the actual CI-equivalent command set; capture exit codes, versions and active publication. On Windows use the direct Playwright CLI command below so worker arguments are not dropped.
3. Require positive map dimensions, wheel zoom behavior, hydration readiness, exact fixture search results, empty/error/retry paths and closure handling. Do not rely only on text presence.
4. Open a reviewable change with results and remaining blockers. Verify hosted GitHub jobs and deployment only where access/authorization exists; record public URL, deployed commit/publication and safety status version after deployment. Uploading an artifact alone is not deployment.
5. For the refresh service record actual process/service state, heartbeat, scheduled runs and failures. Short cadence configuration without execution cannot satisfy real-time freshness.
6. Rewrite PROGRESS's latest handoff around measured outcomes, including unresolved sources and review workload. Stop iterating when the stated acceptance passes; do not initiate an unrelated UI redesign.

## 6. Independent verification results

| Check | This audit's result | Evidence |
|---|---|---|
| Python ingestion + OPM tests | 183 passed | [python.log](work/audit6-2026-09-13/python.log) |
| Web unit/contract tests | 97 passed | [web.log](work/audit6-2026-09-13/web.log) |
| Astro/TypeScript | **1 error**, 1 unused-import hint | [astro.log](work/audit6-2026-09-13/astro.log) |
| Go catalog/API | Both pass (cached) | [catalog.log](work/audit6-2026-09-13/catalog.log), [api.log](work/audit6-2026-09-13/api.log) |
| Checkout required files | Pass | [checkout.log](work/audit6-2026-09-13/checkout.log) |
| Locale parity | 352 identical non-empty keys per locale | [locales.log](work/audit6-2026-09-13/locales.log) |
| Framework/OPM | Pass; 12 diagrams; reports 337 keys under its own check scope | [framework.log](work/audit6-2026-09-13/framework.log) |
| Active snapshot and next source selection | Both pass; 10 jobs, 4 reviewed offerings | [publish.log](work/audit6-2026-09-13/publish.log), [sources.log](work/audit6-2026-09-13/sources.log) |
| Static build | Pass, 15,299 pages | [build.log](work/audit6-2026-09-13/build.log) |
| Browser, direct CLI, actual 2 workers | 54 passed | [e2e-two-workers.log](work/audit6-2026-09-13/e2e-two-workers.log) |
| Initial npm-wrapper browser run | 47 passed / 7 failed; requested worker argument was not forwarded | [e2e.log](work/audit6-2026-09-13/e2e.log) |
| Custom safety counterexamples | Defects reproduced | [safety-results.json](work/audit6-2026-09-13/safety-results.json) |
| Map geometry/screenshots | Mobile MapLibre height 0 reproduced | [map-results.json](work/audit6-2026-09-13/map-results.json) |
| Official samples | 5/5 HTTP 200 using Scrapling; field interpretation checked separately | [official-probe.json](work/audit6-2026-09-13/official-probe.json) |
| Hosted CI/deployment/continuous refresh | **Not verified** | No production completion claim |

Initial sandbox test errors were environment failures (Node spawn EPERM/Python temporary-directory permissions), rerun outside the sandbox. The final Astro error remains after that rerun and is a real current code failure. The first browser run was not counted as a two-worker failure. Passing its two-worker rerun does not resolve the custom map/safety counterexamples.

Useful reproduction commands from repository root unless a working directory is noted:

```powershell
py -3 work/audit6-2026-09-13/evidence.py
py -3 -m pytest services/ingestion/tests tests/test_opm_generation.py -q
py -3 services/ingestion/src/publish.py --check
py -3 services/ingestion/src/publish.py --check-sources
py -3 scripts/check_framework.py
node --experimental-strip-types work/audit6-2026-09-13/safety-probe.mjs
# Working directory: apps/web
npm test
npm run check
npm run build
node node_modules/@playwright/test/cli.js test --workers=2
```

The custom safety probe currently records the defect; it is not a production regression test that should remain expecting broken behavior. Preserve this audit's evidence before rerunning acquisition scripts, which overwrite their own audit output files.

## 7. Release and next-audit completion criteria

The next handoff should include: all 54 institution assessments; scoped source graph; executed run receipts and overdue-source list; cross-institution candidate disposition ledger; before/after per-school public results; resolved VŠB/UTB counterexamples; source-bound three-locale review; passing type/safety/map/browser checks; and honest hosted deployment/scheduler status.

Do not close the coverage task just because the candidate count, public count, registered-source count, or number of passing tests increased. No defensible exact national recall percentage exists yet: the external official vacancy denominator has not been established. Use measured recall against a dated, manually audited official sample and disclose the sample scope. Keep the national assessment completeness metric separate.

## Appendix A — All 54 institutions

The following is a point-in-time matrix. “Success” means a stored scheduler timestamp, **not independently verified whole-institution coverage**. Public counts are all tracks, including postdocs. Source URLs and timestamps for every registered row are in inventory.json. A zero without complete source evidence remains unknown.

| Institution | Type | Registered sources | Scheduler sources with success* | Current candidates | Public jobs |
|---|---|---:|---:|---:|---:|
| Univerzita Karlova (`msmt-vs_11000`) | public | 1 | 1 | 13 | 2 |
| Jihočeská univerzita v Českých Budějovicích (`msmt-vs_12000`) | public | 1 | 1 | 9 | 0 |
| Univerzita Jana Evangelisty Purkyně v Ústí nad Labem (`msmt-vs_13000`) | public | 1 | 0 | 0 | 0 |
| Masarykova univerzita (`msmt-vs_14000`) | public | 1 | 1 | 5 | 4 |
| Univerzita Palackého v Olomouci (`msmt-vs_15000`) | public | 1 | 1 | 2 | 0 |
| Veterinární univerzita Brno (`msmt-vs_16000`) | public | 1 | 0 | 0 | 0 |
| Ostravská univerzita (`msmt-vs_17000`) | public | 1 | 0 | 0 | 0 |
| Univerzita Hradec Králové (`msmt-vs_18000`) | public | 1 | 0 | 0 | 0 |
| Slezská univerzita v Opavě (`msmt-vs_19000`) | public | 1 | 0 | 0 | 0 |
| České vysoké učení technické v Praze (`msmt-vs_21000`) | public | 2 | 2 | 17 | 0 |
| Vysoká škola chemicko-technologická v Praze (`msmt-vs_22000`) | public | 1 | 1 | 7 | 0 |
| Západočeská univerzita v Plzni (`msmt-vs_23000`) | public | 0 | 0 | 0 | 0 |
| Technická univerzita v Liberci (`msmt-vs_24000`) | public | 1 | 0 | 0 | 0 |
| Univerzita Pardubice (`msmt-vs_25000`) | public | 1 | 1 | 4 | 0 |
| Vysoké učení technické v Brně (`msmt-vs_26000`) | public | 1 | 1 | 10 | 0 |
| Vysoká škola báňská – Technická univerzita Ostrava (`msmt-vs_27000`) | public | 1 | 1 | 5 | 0 |
| Univerzita Tomáše Bati ve Zlíně (`msmt-vs_28000`) | public | 1 | 1 | 8 | 0 |
| Vysoká škola ekonomická v Praze (`msmt-vs_31000`) | public | 1 | 1 | 1 | 0 |
| Česká zemědělská univerzita v Praze (`msmt-vs_41000`) | public | 1 | 1 | 5 | 4 |
| Mendelova univerzita v Brně (`msmt-vs_43000`) | public | 1 | 1 | 4 | 0 |
| Akademie múzických umění v Praze (`msmt-vs_51000`) | public | 0 | 0 | 0 | 0 |
| Akademie výtvarných umění v Praze (`msmt-vs_52000`) | public | 0 | 0 | 0 | 0 |
| Vysoká škola uměleckoprůmyslová v Praze (`msmt-vs_53000`) | public | 0 | 0 | 0 | 0 |
| Janáčkova akademie múzických umění (`msmt-vs_54000`) | public | 0 | 0 | 0 | 0 |
| Vysoká škola polytechnická Jihlava (`msmt-vs_55000`) | public | 1 | 0 | 0 | 0 |
| Vysoká škola technická a ekonomická v Českých Budějovicích (`msmt-vs_56000`) | public | 1 | 0 | 0 | 0 |
| AMBIS vysoká škola, a.s. (`msmt-vs_61000`) | private | 0 | 0 | 0 | 0 |
| University College Prague - Vysoká škola mezinárodních vztahů a Vysoká škola hotelová a ekonomická s.r.o. (`msmt-vs_63000`) | private | 0 | 0 | 0 | 0 |
| University of New York in Prague, s.r.o. (`msmt-vs_6d000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola evropských a regionálních studií, z. ú. (`msmt-vs_6k000`) | private | 0 | 0 | 0 | 0 |
| Filmová akademie Miroslava Ondříčka v Písku, o.p.s. (`msmt-vs_6n000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola tělesné výchovy a sportu PALESTRA, spol. s r.o. (`msmt-vs_6p000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola NEWTON, a.s. (`msmt-vs_6q000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola logistiky o.p.s. (`msmt-vs_6r000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola zdravotnická, o.p.s. (`msmt-vs_6s000`) | private | 0 | 0 | 0 | 0 |
| Anglo-americká vysoká škola, a. s. (`msmt-vs_6u000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola Sting, o.p.s. (`msmt-vs_73000`) | private | 0 | 0 | 0 | 0 |
| Metropolitní univerzita Praha, o. p. s. (`msmt-vs_75000`) | private | 0 | 0 | 0 | 0 |
| Pražská vysoká škola psychosociálních studií, s.r.o. (`msmt-vs_79000`) | private | 0 | 0 | 0 | 0 |
| Moravská vysoká škola Olomouc, o.p.s. (`msmt-vs_7c000`) | private | 0 | 0 | 0 | 0 |
| CEVRO Univerzita z.ú. (`msmt-vs_7d000`) | private | 0 | 0 | 0 | 0 |
| Unicorn Vysoká škola s.r.o. (`msmt-vs_7e000`) | private | 0 | 0 | 0 | 0 |
| Evropská výzkumná univerzita, z.ú. (`msmt-vs_7j000`) | private | 0 | 0 | 0 | 0 |
| Prague City Vysoká Škola s.r.o. (`msmt-vs_7l000`) | private | 0 | 0 | 0 | 0 |
| ARCHIP s.r.o. (`msmt-vs_7m000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola aplikované psychologie, s.r.o. (`msmt-vs_7n000`) | private | 0 | 0 | 0 | 0 |
| Škoda Auto Vysoká škola o.p.s. (`msmt-vs_7p000`) | private | 0 | 0 | 0 | 0 |
| ART & DESIGN INSTITUT, s.r.o. (`msmt-vs_7r000`) | private | 0 | 0 | 0 | 0 |
| Panevropská univerzita, a.s. (`msmt-vs_7s000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola kreativní komunikace, s.r.o. (`msmt-vs_7t000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola finanční a správní, a.s. (`msmt-vs_7u000`) | private | 0 | 0 | 0 | 0 |
| Vysoká škola ekonomie a managementu, a.s. (`msmt-vs_7v000`) | private | 0 | 0 | 0 | 0 |
| Policejní akademie České republiky v Praze (`msmt-vs_94000`) | state | 0 | 0 | 0 | 0 |
| Univerzita obrany (`msmt-vs_95000`) | state | 1 | 0 | 0 | 0 |

*Scheduler timestamps are claims, not proof of complete faculty/laboratory coverage. Zero candidates without a successful scoped run means unknown, not no vacancies.

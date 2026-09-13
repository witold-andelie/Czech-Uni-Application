# Czech Uni Apply — Fourth comprehensive audit and agent execution guide

Audit date: 2026-09-12. Workspace: `D:\chatgpt\Czech_Uni_Apply`.

**Verdict: a useful local prototype with substantial reliability improvements, but not yet a comprehensively translated, continuously maintained public opportunity service.** The principal remaining problems are incomplete content review, gaps in the business validation contract, disconnected publication/status delivery, and inaccurate operational summaries. More parser code and more passing tests alone will not resolve these problems.

This report is an implementation handoff. Each finding states its evidence level, relevant code, repair sequence, verification, and stopping condition. The audit itself does not implement these repairs, change official source data, activate a snapshot, commit code, or deploy a website.

## 1. Scope, authority, and evidence rules

The audited object is the **working tree**, including untracked implementation files. Git HEAD is `a9d6baaecbfb0ef06b6f390a520394af257c8ba0`; that commit alone does not reproduce this workspace. No Git remote is configured. The selected publication is `v2026-09-12.2`, published at `2026-09-12T12:47:09Z`.

Read `AGENTS.md`, `README.md`, `docs/PRODUCT.md`, `docs/UI_RULES.md`, `docs/I18N_RULES.md`, `docs/DATA_MODEL.md`, `docs/CRAWLING_RULES.md`, `docs/ACCEPTANCE.md`, `docs/REFRESH_POLICY.md`, `opm/README.md`, and `opm/OPL.md` before implementing a ticket. Use this report together with the current files, not instead of them. Function names are supplied because line numbers will move.

Preserve the user's decisions:

- The early map integration was an explicit user decision for evaluating the integrated experience. It is **not** an unauthorized merge defect. Do not restore that allegation from round three.
- Ordinary mouse-wheel map zoom must work without Ctrl or Command. Retain the existing fallback and keyboard improvements.
- Teaching language remains the first programme choice. UI locale, teaching language, and working language remain independent.
- CZU is a priority across English, Czech, bachelor/master, doctoral, and paid-role sources. Priority does not justify invented dates, qualifications, or translation approvals.
- Stable sources retain a 120-hour coverage objective. High-volatility jobs/status/programme sources have separately authorized shorter intervals. Short intervals are not proof of real-time publication.
- Python is offline ingestion; Go is the intended deployed scheduling/API layer; PostgreSQL is the intended durable state layer; Astro/Svelte serves browsing. Do not move crawling or translation into visitor requests.
- Do not purchase hosting, register a domain, submit applications, or send email as a side effect of a repair. Prepare the concrete deployment first and use the session's actual authorization for its activation.

Evidence labels used below:

| Label | Meaning |
|---|---|
| Reproduced | A new isolated test or browser run demonstrated the behavior in this audit. |
| Inspected | The implementation or stored data establishes the stated behavior; no production incident is claimed. |
| Previous evidence | An earlier saved run exists; it was not rerun in this audit. |
| Not verified | Requires a target environment, external service, real device, or a broader test not performed here. |

Severity: P1 is a correctness/product-release blocker for the affected capability; P2 is a significant usability, maintainability, or verification gap. No P0 incident was demonstrated. A P1 finding against a future API does not imply that the current static preview exposes that API publicly.

Audit evidence lives in [work/audit4-2026-09-12](work/audit4-2026-09-12/). Modified test snapshots are confined to its `isolated/` directory. Their checksums were intentionally recomputed, so the probes test **business acceptance after serialization**, not simple byte-tampering detection. They are never candidates for publication.

## 2. Verified baseline and corrected counts

| Layer | Current evidence | Interpretation |
|---|---|---|
| Active formal snapshot | 54 institutions, 54 portals, 5,019 register offerings, 53 inventory schools, 54 coordinates, 6 jobs | Not 5,019 open admissions opportunities. |
| Default reviewed paid/master job scope | 4 CZU jobs | Two additional published jobs are CUNI postdoctoral roles. |
| CZU compensation | Salary basis 1.0 FTE; actual A2/A1/D1/T1 workloads 1.0/0.5/1.0/0.8; possible start 2026-10-01 | The latest field separation is useful and must be preserved. No automatic part-time salary calculation is authorized by this evidence. |
| Current source registry, recomputed | **15 official job-listing sources, 13/54 HEIs, 24.1%, 41 HEIs without a registered source** | Replaces the stale current-state claim of 10 sources, 8/54, and 46 missing. AVCR is separate from the HEI denominator; CTU has an additional faculty source. |
| Explicit whole-institution completeness claims | 0 | A central aggregator connection is not proof of all faculty/centre jobs. |
| Candidate file | 128 total; 77 non-archived records explicitly `catalogueScopeStatus=included`, 73 of those review-pending | This is the precise predicate used by the previous progress narrative. It is not identical to the coverage builder's predicate. |
| Recomputed coverage builder | 90 `currentCandidates`, 22 paid/master candidates | Its `is_current_job` excludes archived/closed/expired/unavailable but does not require explicit inclusion. Do not present 77 and 90 as the same metric. |
| Stored coverage report | Generated 2026-09-11; points at `v2026-09-09.1`, 4 published jobs, 10 job sources | Historical evidence, not the current release dashboard. |
| Inventory school missing from rows | `msmt-vs_7l000` | Absence needs a recorded explanation; do not fabricate offerings to force 54/54. |

The new coverage recomputation was written only to [coverage-recomputed.json](work/audit4-2026-09-12/coverage-recomputed.json), at `2026-09-12T13:35:27Z`. It also exposes `lastRunCompleteSources=1`, because the candidate file's discovery summary contains the latest CZU-only refresh, while scheduled discovery success refers to a broader earlier run. That is a scope/provenance problem, not proof that fourteen sources failed.

Saved candidate-source claims remain: DZS 5,137 UUIDs; CZU English bachelor/master 36; CZU Czech portal bachelor/master 129; CZU doctoral baseline 60. These are **stored run results**, not fresh live-web confirmations in this audit. Do not sum overlapping sources. In particular the two CZU bachelor/master sources overlap and disagree on some identities/titles.

## 3. Checks performed in this round

| Check | Result and limitation |
|---|---|
| Python ingestion suite | 143 passed. First sandboxed run had 142 passes and a Windows `os.replace` permission failure; normal-permission isolated rerun passed all 143. Do not report that environment error as a proven parser regression. |
| Web Node suite | 76 passed. |
| Astro/Svelte/TypeScript | 48 files; zero errors, warnings, or hints. |
| Go catalog | `go test ./...` passed, cached. |
| Go API | Command exited successfully but package reports **no test files**. This is not HTTP/API acceptance. |
| New contract probes | Baseline passes both implementations. Nine invalid variants pass both; an impossible start date is rejected by Python but accepted by Node. See section 4. |
| Browser matrix | 6 route types × 3 locales × 3 widths = 54 loads; all HTTP 200, no pageerror, no unexpected horizontal overflow. External HTTP requests blocked. |
| Mobile drawer interaction | Focus escape and failure to restore focus reproduced. |
| Job detail content | Raw salary enums reproduced; screenshot inspected. |
| Retry-After | Mocked HTTP 429 with 3,600-second server delay still slept only 3 and 12 seconds. No university was requested by this probe. |
| Coverage | Recomputed from current registry/source files into the audit directory; exposed stale stored version and mismatched scope. |
| Static build | Previous same-day evidence: 15,278 pages. Not rebuilt in this audit because no product code changed. Browser checks used the existing local static preview. |
| Map wheel/fallback | Previous same-day browser evidence exists; no new map regression run in this audit. |
| Hosted CI, deployment, real Mainland China/mobile performance | Not verified; no remote/hosting target. |

Browser route types were home, English-filtered programmes, jobs, one CZU job detail, empty comparison, and empty saved list. This matrix is a useful smoke check, **not** a completed populated compare/save/locale-switch end-to-end test, a full accessibility audit, or coverage of every detail/error route.

## 4. New contract counterexamples

Reproduce with `py -3 work/audit4-2026-09-12/probe_contract.py`. Read [contract-results.json](work/audit4-2026-09-12/contract-results.json). It executes Python and Node validators against independent copies of the active snapshot.

| Mutation | Python | Node |
|---|---|---|
| Unchanged baseline with regenerated checksums | Accept | Accept |
| Job window date `2026-99-99`, deadline `yesterday`, timezone `Mars/Olympus` | Accept | Accept |
| Remove job source URL, job application URL, and its evidence URL | Accept | Accept |
| Change stored original text while retaining prior review | Accept | Accept |
| Change Chinese title while retaining prior review | Accept | Accept |
| Change a CZU salary to a different structurally valid amount, retain prior review | Accept | Accept |
| Change evidence sourceHash to differ from the job sourceHash | Accept | Accept |
| Salary -60000 with unsupported period/tax values | Accept | Accept |
| Employment start `2026-02-30` | Reject | Accept |
| Mark a tracer offering review-pending/unreviewed | Accept | Accept |
| Corrupt nested tracer window date, timezone, evidence reference while top-level windows remain valid | Accept | Accept |

`originalText` in a published CZU job is only the original title, not the canonical vacancy body. The changed-original-text probe must not be described as proof that a stored full body was rehashed incorrectly. The stronger demonstrated problems are mismatched evidence hashes, changed translated output, and changed structured salary surviving the same review record. The published evidence does not contain enough canonical content to independently reconstruct the reviewed fact bundle.

## 5. Execution order and stop rules

Do not restart the project or re-audit the whole repository after each change. Use bounded tickets, each ending in a changed behavior that a reviewer can see.

| Batch | Tickets | Required deliverable before moving on |
|---|---|---|
| 1: prevent incorrect acceptance | A52, A53, A55 | New counterexamples fail in both validators; current content is either newly reviewed or explicitly held back. |
| 2: make priority content useful | A54, A56, A62 | Reviewed CZU programme slice reaches three-language pages with actual windows, fees, requirements, and source links; job details explain qualifications. |
| 3: make the site stay correct | A58, A59, A60, A65 | Defined release/status handoff, production-safe API startup, reproducible CI artifact, durable scheduler plan and local integration evidence. |
| 4: expand reach with measured coverage | A57, A64, A66 | School/source gaps decrease through tested adapters; scope and freshness metrics are coherent. |
| 5: complete interaction assurance | A61, A63 | Browser flows run in CI; mobile drawer keyboard behavior is correct. Do A63 earlier if working in the shared filter UI. |

There are dependencies across batches: A52/A53 define the record contract used by A54/A56; A60 establishes the deployable revision; A58 needs a deployment/status path but can be tested locally before hosting. A57 starts from existing adapters rather than adding duplicate sources. This table is a sequencing guide, not an instruction to delay an easy user-visible fix until all infrastructure is complete.

Every agent handoff must provide: ticket ID; reproduction; changed files; before/after behavior; exact tests and exit status; publication version if changed; screenshot or HTTP response where relevant; remaining external dependency. Use statuses `inspected`, `reproduced`, `implemented`, `locally verified`, `hosted verified`, `operationally observed`. A green unit suite cannot skip those stages.

## A52 — P1 — Validate the complete rendered business schema

**Evidence: reproduced.** Relevant files: `services/ingestion/src/publication_contract.py` (`_urls`, `_validate_jobs`, `_validate_tracer`, `valid_iso_datetime`); `apps/web/scripts/published-contract.mjs` (`urls`, `isoDateTime`, `validateDataset`); `apps/web/src/lib/buildBrowseCatalog.ts` (`tracerWindows`). Related acceptance: A06, A07, A24, A32, A51.

Both validators omit date validity/order and real timezone checks for windows. `_urls` validates only fields present, so required evidence links can disappear. Salary strings need only be nonempty. The Node employment date check uses `Date.parse`, which normalizes some impossible calendar dates. Tracer validation walks top-level `windows`, while the renderer takes `offering.windows` or `offering.window`; those nested records can disagree and escape validation.

Implementation steps:

1. Copy each counterexample into a permanent, small shared fixture corpus under a proposed `tests/contracts/` directory. State expected rule/error identifiers, not implementation-specific sentence text.
2. Inventory every field consumed by `buildBrowseCatalog`, `LiveWindows`, job/programme detail pages, and the API. Record which fields are required, nullable, enum-constrained, or source-dependent. Do not make unknown facts mandatory by inventing them.
3. Define one window representation. Prefer top-level windows referenced by ID; if legacy nesting remains during migration, require exact equivalence and validate the representation actually rendered. Check owner type/ID, evidence ID, round number/type, localized applicant scope, conditional flags, date precision, dates, timezone, and start/end ordering.
4. Implement strict calendar parsing in both languages. Validate year/month/day by round-trip, require timezone/offset policy for timestamps, support true nullable and month-precision states, and reject nonexistent IANA zones. Define behavior for DST ambiguity rather than silently guessing.
5. Distinguish required URLs from optional ones. Require an official source evidence URL for published facts. Require either a verified job-specific application target or verified official instructions for a public job. Keep permitted missing programme targets explicitly typed as unknown/general-portal, not mislabeled direct application.
6. Validate finite nonnegative monetary values and controlled currency/cycle/tax codes. Preserve null amounts with confirmed compensation evidence. Validate tuition variants and their scope/evidence too. Do not broaden the FTE range merely to make a failing input pass; if a real source needs a range, model a range with evidence.
7. Run the shared corpus through Python and Node and compare outcomes. Keep independent implementations but remove independent interpretations of the contract.
8. Run source-selection and immutable-snapshot checks. If existing data fails, produce a migration/review list and a new valid snapshot; do not weaken the validator or edit an old snapshot to recover a green build.

Acceptance: all section-4 schema failures are rejected by both engines; valid leap day, missing start, future second round, conditional supplement, null salary, and preserved multiple rounds remain valid. A deliberately invalid nested window cannot reach a page after passing validation. Stop after the focused corpus and relevant existing suites pass.

## A53 — P1 — Bind review to facts, translated output, and retrievable evidence

**Evidence: reproduced and inspected.** Locations: `harvest_nine_hei_jobs.py::apply_translation_review`, `data/sources/reviews/job-translations.json`, `_validate_translation_review`, and the independent Node review checks. Related: A08, A32, A39.

Current approval binds several strings to a sourceHash, but does not bind the reviewed structured facts or translated bytes. A valid salary edit or Chinese-title edit keeps approval. A job and its evidence can carry different source hashes. Locale entries retain dates/status but no reviewer identity; current CZU review records contain titles and sourceHash, with no explicit structured fact review. This does not prove the six current jobs are factually false. It proves the gate cannot enforce the review claim it makes.

Implementation steps:

1. Define a canonical review payload with stable field ordering and explicit normalization version. Include eligibility, paid evidence, currency/period/tax, workload, language requirements, contract/role summary, application method/target, and content-relevant windows. Separate harmless fetch metadata from reviewed facts.
2. Persist the canonical source excerpt or an immutable evidence reference that the publisher can resolve locally. Bind URL, source language, extraction locator, acquisition timestamp, parser version, and hash. Do not use a title-only `originalText` as the vacancy body.
3. Add a fact-review record with entity ID, canonical fact hash, evidence hash, reviewer identity/role, review timestamp, decision, and explicit notes for unknowns/conflicts. An agent may create drafts; it must not invent a human reviewer or claim human review that did not occur.
4. Add per-locale translated-content hash, translated-from fact/source version, reviewer, and timestamp. Preserve legitimate identical proper names; compare reviewed payload hashes rather than banning matching text heuristically.
5. Invalidate approval when reviewed facts or translated output change, even if the raw page hash is unchanged. Ensure parser upgrades cannot silently change structured qualification or salary while reusing old approval.
6. Require evidenceHash equality across the job/evidence/review linkage. Validate factual evidence existence separately from compensation enum values. Missing body evidence must create a pending task, not a green flag.
7. Re-review the currently published six jobs under the migrated model. Keep an explicit decision for source-language/working-language uncertainty and for the two CUNI records; do not infer that four CZU examples validate all jobs.
8. Keep safety closure updates on the separate path in A58; do not require new marketing translations before stopping an invalid application link.

Acceptance: source/evidence mismatch, changed Chinese title, changed salary, changed doctoral requirement, missing reviewer, and missing evidence each invalidate the relevant approval. An unchanged reviewed payload remains publishable after a fetch timestamp update. Deliver a review bundle another reviewer can inspect without reconstructing hidden chat context.

## A54 — P1 — Programme translations and tracer publication lack equivalent review gates

**Evidence: inspected and reproduced.** Locations: `expandInventory.ts::localizedOriginal/expandInventory`, `buildBrowseCatalog.ts`, `_validate_inventory`, `_validate_tracer`, `config/publication-policy.json`. Related: A03, A05, A08, A39.

`localizedOriginal` puts the same source string into zh-CN/en/cs. All 5,019 compact rows enter that path before the small tracer overlay. Most titles are consequently original-source labels, not reviewed localized content. `verifiedAt` is generated from a catalogue generation date. Tracer records marked `tracer_not_published` are nevertheless part of required snapshot files and rendered overlays; setting a tracer to review-pending does not block it. Provenance labels disclose some limitation, but they do not satisfy the project's core trilingual publication rule.

Implementation steps:

1. Define the product distinction between official register inventory and reviewed admissions offerings. Preserve the inventory for internal discovery and accounting. Formal localized opportunity pages require review; do not relabel duplicated strings as reviewed translations.
2. Add programme/offering translation and fact-review records using A53's common contract. Include source title, reviewed display title, tuition applicability, language requirements, admissions requirements, materials, and instructions.
3. Replace `localizedOriginal` as the source of formal localized display content. A proper-name exception must be explicit and reviewed; arbitrary Czech programme names are not all proper-name exceptions.
4. Stop deriving `verifiedAt` from `generatedAt`. Expose source fetchedAt, facts reviewedAt, and publishedAt with distinct labels. Unknown review dates stay unknown.
5. Make snapshot selection enforce approved programme/offerings as it does jobs. Resolve the legacy tracer classification: approve it with evidence or keep it out of formal admissions overlays. No double standard for older tracer records.
6. Preserve stable inventory IDs and aliases while enriching records, so favourites/comparisons do not break. Avoid merging programmes solely on a normalized title; use institution, official ID/code, faculty, degree, language, year and track evidence.
7. Migrate CZU first through A56, then the other institutions in bounded review batches. Keep coverage counts for inventory and reviewed admissions separate throughout migration.

Acceptance: an unreviewed tracer or missing locale cannot enter formal admissions pages; the same reviewed offering in all three locales has equal factual values and useful localized requirements. Do not report 5,019 fully translated programmes until the review manifest supports that number.

## A55 — P1 — CSCSE reference labels overstate the available evidence

**Evidence: inspected and visible in the CZU screenshot.** Locations: `services/ingestion/src/apply_cscse_list.py::apply`, `mergeBrowseCatalog.ts::institutionFromBaseline`, `InstitutionTags.astro`, `_validate_baseline`. Related: A22, A23.

The importer explicitly says its source is an operator-supplied name list, not a live official lookup. It converts matches to `listed`, and every nonmatch to `not_found`. The frontend displays official-lookup wording and a lookup date, while `evidenceId` is set to null. An operator list's omission does not establish an official negative lookup. A footer saying individual recognition is not guaranteed does not correct the positive evidence claim.

Implementation steps:

1. Retain the operator list as a discovery/matching input with its actual provenance. Do not erase it or pretend it came from an official query.
2. Separate `operatorListed`/candidate matching metadata from official `lookupStatus`. Without official evidence, public status must be `unverified` (or an explicitly labeled operator reference if separately authorized); it must not mean official `not_found`.
3. For positive/negative official lookups, collect a retrievable official result, query date, exact awarding institution match and reviewer. Preserve aliases/campus differences and any risk notices.
4. Add publication rules requiring the supporting evidence for official lookup claims. Distinguish school ownership evidence from recognition lookup evidence.
5. Render the evidence link and provenance in institution details and accessible compact disclosures. Keep the individual-recognition disclaimer in addition to, not in place of, provenance.
6. Rebuild a new snapshot after correcting records. Update recognition filters and counts so they do not continue using the old `cscseLookupStatus` shortcut.

Acceptance: an operator-only positive or omitted name cannot appear as an official confirmed result. A synthetic positive with missing evidence fails publication. All three locales explain the same evidence status. This audit makes no claim about any institution's actual current recognition outcome.

## A56 — P1 — CZU admissions extraction has no complete path to reviewed public content

**Evidence: inspected.** Sources: `data/sources/admissions/czu-english-programmes.json`, `czu-czech-programmes.json`, `czu-doctoral-programmes.json`, their three harvesters, `config/publication-policy.json`, and `loadCatalogClient.ts`. Related: A37, A42, A47–A49.

The useful dates and fees exist in candidates, but the formal publication policy only contains legacy register/tracer inputs. Reading 36/129/60 records repeatedly cannot improve pages that do not consume approved versions of those records. A review queue is a correct safety boundary; an indefinite queue without an editorial/export path is an incomplete product.

Implementation steps:

1. Generate an editorial worklist from existing candidate IDs, with source freshness, upcoming window, missing fields, cross-source conflict, and review status. Prioritize the next relevant CZU cycle based on a new verified run at execution time; the saved September 14/15 dates are historical evidence, not evergreen constants.
2. Build an explicit CZU crosswalk from English portal IDs and Czech-portal URLs to register offerings and degree/language/faculty/year. Keep the double-degree discrepancy and title variants as conflicts requiring a decision, not duplicates automatically dropped.
3. Choose a small representative first delivery: English bachelor, English master, Czech-taught programme, and doctoral offering where evidence allows. This is a vertical acceptance slice, not the final coverage target.
4. Populate trilingual titles, material requirements, tuition basis, official round dates, applicant scope and source links. Keep unknown starting dates unknown; preserve conditional FTZ stages and guarded scan transcription evidence.
5. Produce approved normalized records under a versioned schema, select them through A54/A53, add them to the manifest policy, and export them through the same immutable build path. Never import mutable `data/sources` directly into the browser to accelerate delivery.
6. Show project-specific UIS links only where supported. General UIS portals remain explicitly general. Verify that UI locale switching does not silently select another application target or language track.
7. Demonstrate list → filter → detail → save → compare → official source in all locales. Then process remaining records in batches with measurable pending/approved/blocked counts.
8. After the CZU pipeline works, reuse its review/export mechanism for DZS-backed discoveries and other schools, while preserving school/faculty authority over admissions windows.

Acceptance: a newly reviewed candidate that was previously invisible becomes visible with its correct window and source. A rejected/untranslated candidate remains excluded. A source change returns the affected fields to review. Report the exact reviewed records added and remaining coverage, not just another successful crawl count.

## A57 — P1 — School job coverage remains incomplete; use the current registry, not stale progress text

**Evidence: recomputed stored data, no fresh all-school crawl.** Locations: `data/sources/registry.json`, `build_source_coverage.py`, `harvest_nine_hei_jobs.py`, `worker.py::discover_all_jobs`. Related: A19, A37, A45.

Actual registered coverage is 13/54 HEIs with 15 listing sources, not the 8/54 quoted in PROGRESS. JCU, UPCE, UTB, VSE and MENDELU are already represented; do not implement duplicate onboarding tickets for them. There are still 41 schools without a registered source and zero whole-institution completeness claims.

Implementation steps:

1. Read the current registry and generate one row per baseline institution: ownership, source URLs, source scope, official linkage evidence, parser, latest source-run ID, status, and unresolved department gaps.
2. Export the exact missing-41 list from the recomputed report. Distinguish an unresearched school from one with an official statement that no public vacancies are posted. Lack of an English site is not an exclusion.
3. Review existing source parsers first, including the five already-added schools. Confirm whether each entry's runtime path is supported and its tests exercise discovery through the production entrypoint.
4. Add missing institutions in bounded batches, for example five schools, using official structured endpoints/HTML/PDF and required Scrapling escalation for difficult public pages. Save observed pagination, counts, redirects, details and failures.
5. For major universities, document whether a central portal includes faculty/centre jobs. Register supplemental faculty pages when necessary; do not infer completeness from a central URL.
6. Test a new stable job ID not in seed constants; duplicates; second-page results; unreadable attachments; empty verified listing versus parser failure; complete disappearance versus partial failure; supported research/technical roles versus excluded administration.
7. Feed new jobs into the same fact/translation review queue, publish a reviewed batch, and verify a closure path. Source onboarding is not complete merely when registry coverage increases.

Acceptance: each batch has attributable evidence and a reproducible parser; partial failure does not archive jobs. Report registered-school coverage and reviewed-public opportunity coverage separately. Stop a batch after its real workflow works; do not add dozens of speculative URLs before validating any of them.

## A58 — P1 — Closure evidence does not automatically reach a deployed public release

**Evidence: inspected gap; no production closure incident claimed.** Locations: `worker.py::_recheck_open_jobs_unlocked`, `publish.py`, `apps/web/src/lib/clock.ts`, `LiveWindows.svelte`, `.github/workflows/ci.yml`. Related: A20, A25, A46.

The worker deliberately changes only candidate data. Public pages use a fixed snapshot, and browser clock updates recompute known dates only. They cannot learn an employer's new early closure. No deployed process currently validates and activates a safety update, invalidates cache, or verifies three-locale propagation. Therefore an hourly scrape interval is not an hourly public-state guarantee.

Implementation steps:

1. Write an explicit state-delivery contract: confirmed closure is supported by entity-specific evidence; network failure is not closure; new reopening requires positive evidence; future rounds do not override an explicit whole-role closure.
2. Select one mechanism: a small versioned safety-status overlay served through the public data/API path, or an expedited new snapshot/build/deploy. Document why it meets the five-minute propagation objective after verified closure. Do not weaken ordinary content review.
3. Bind a safety update to entity ID, observed source version, closure time/precision, reason/evidence and status generation. Enforce allowed monotonic transitions; a stale code rollback must not reopen a newly closed job.
4. Update public lists, detail views, saved items, search indexes and apply actions across all locales. Retain historical records/tombstones so existing bookmarks explain the closure rather than disappearing without context.
5. Define cache headers/invalidation and last-known-safe behavior if the status endpoint fails. Separate source-check age from status-publication age in monitoring.
6. Use a local integrated test: publish job → observe it in three locales and saved items → inject verified closure into isolated ingestion → activate safety update → verify absence from public results and disabled application actions. Include an already-open tab and a cold/no-JS request where applicable.
7. Test one round closing while another remains open, whole-role closure overriding future dates, network 503, and rollback after closure.
8. Once hosting exists, repeat against the actual cache/CDN and record observed propagation timestamps. Local success remains local until then.

Acceptance: all public surfaces converge within the defined budget after a verified status update; a publication rollback cannot undo a later safety closure; failures preserve evidence without fabricating closed status.

## A59 — P1 before API exposure — Go API defaults to fixture data

**Evidence: inspected.** `apps/api/cmd/server/main.go:142`, `defaultSnapshot`; `services/catalog/catalog.go::LoadSnapshot`. The default path is `data/fixtures/catalog.json`. That file has 6 institutions, 8 offerings and 7 jobs, unlike the formal 54/5,019/6 snapshot. API startup loads once; no publication manifest binding is shown. The API test command has no HTTP tests.

Implementation steps:

1. Make production startup require an explicit validated publication artifact/selection. Refuse fixture `dataClass` unless an explicit development/demo flag is enabled.
2. Define a Go-consumable catalogue export generated only from the selected immutable release, using the same normalized offering/window/job model as the browser. Do not point the API at an arbitrary single JSON and call that the nine-file publication contract.
3. Validate checksums, schema, IDs, review eligibility and version before becoming ready. Return version/freshness in readiness and responses.
4. Select restart-on-release or validated atomic in-memory refresh; retain the prior valid release on corrupt updates. Integrate the A58 status generation.
5. Add `httptest` coverage for default production startup, invalid artifact, empty results, filters, locale validation, pagination and method errors. Test API/UI parity at a fixed clock.
6. Cover new salary/workload/start fields in the Go DTO/export. A static UI fix does not automatically migrate the Go model.
7. Add server shutdown/timeouts and deployment-specific resource bounds based on measured usage, then run A17 performance tests. Avoid an unrelated framework rewrite.

Acceptance: production cannot serve fixtures accidentally; API version and record counts match the selected public artifact; corrupted activation leaves the last good release available. Do not describe the current static frontend as contaminated by this unexposed API.

## A60 — P1 for operational release — CI artifact configuration is not hosted CD

**Evidence: inspected.** `.github/workflows/ci.yml`, `.github/dependabot.yml`, `.gitignore`, `README.md`, Git remote output. Good existing controls: read-only default token, full-SHA Action pins, PR/main triggers, job dependency gates, locked npm installation, and main-only artifact upload. These should remain. Full-SHA pinning is consistent with [GitHub's official guidance](https://docs.github.com/en/actions/reference/security/secure-use).

The workflow currently produces an artifact but does not deploy, prove a clean checkout is complete, enforce branch protection, or start a scheduler. Many required files are untracked in the audited working tree. That is a handoff/reproducibility state, not evidence that an attempted hosted run failed.

Implementation steps:

1. Inventory the intended deliverable files with Git status and check-ignore. Separate source code, lockfiles, required data/review artifacts and deliberate audit fixtures from runtime locks, owner sidecars, staging, raw bulk captures, caches and backup executables. Do not run `git add --all` over this workspace blindly.
2. Define what a clean checkout needs for every test and build. Either version the active immutable data and evidence needed for validation or fetch them from a pinned, integrity-checked release store. Never fetch mutable `latest` during CI.
3. Establish the authorized remote repository and default branch. Prepare the exact revision and PR/commit without overwriting the existing work. Activate remote operations only under actual session authorization.
4. Run hosted CI for the intended revision; retain run URL and artifact digest. Compare artifact publication version against `current.json` and the build manifest, not just a green status.
5. Configure required checks/branch protection once repository capabilities and policy are known. Record what was actually enabled, including any platform limitations.
6. Add the chosen deployment job/environment. Promote the already-tested artifact, rather than rebuilding different bytes in an unrelated environment. Use minimal deployment credentials and avoid privileged execution of untrusted PR code.
7. Add post-deploy HTTP probes for three locale routes, release metadata, versioned data assets, correct 404 behavior, official links and safety-state handling. Define rollback to an existing artifact with A58 safety-state preservation.
8. Deploy ingestion/scheduling separately; static hosting cannot run the Python worker or Go scheduler merely because it serves the site. Link deployment status to A65.

Acceptance: a known revision produces a verified artifact and, once authorized, an observable deployed version. Until then report `CI configured; local checks passed; hosted CI/CD not verified`. Domain purchase is not a prerequisite for preparing this work.

## A61 — P2 — CI does not enforce browser acceptance or model generation consistency

**Evidence: inspected.** `ci.yml` has unit/type/build checks but no browser job. `scripts/check_framework.py` checks readable JSON, locale key equality, links, and nonempty OPM files; it does not prove that generated diagrams/OPL match `model.json`. Related: A01–A17, A40–A44, A50.

Implementation steps:

1. Move reusable browser acceptance into a maintained proposed `apps/web/tests/e2e/` suite; pin browser/test dependencies. Audit scripts in `work/` are evidence, not a durable CI contract.
2. Test the built artifact, not only the development server. Start it on a fixed local port, wait on HTTP readiness, and guarantee cleanup on success/failure.
3. Add a representative three-locale matrix at 390/768/1440 widths: teaching-language choice, populated list/detail, compare two items, save/restore, locale preservation, clear filters, empty result, 404, data-request failure/retry, and mobile drawer keyboard interaction.
4. Stub external map tiles deterministically and separately test blocked tiles. Keep real map/network performance out of deterministic CI; add scheduled/manual environment checks instead.
5. Upload screenshots, browser console/network failures and traces on failure. Assert meaningful behavior, not merely that an element exists.
6. Add an OPM check mode that regenerates into a temporary directory or compares deterministic semantic outputs. Validate relationship types/trace IDs and fail for stale generated artifacts. Account for image/render-tool metadata rather than requiring unexplained byte equality across Graphviz versions.
7. Run negative CI-path exercises: invalid fixture blocks build; browser failure blocks deploy; missing artifact fails upload. Do not claim branch protection from YAML alone.

Acceptance: breaking language preservation or drawer focus fails CI, and changing `opm/model.json` without updating required generated semantics is detected. The 54-load audit matrix can seed this work but is not sufficient by itself.

## A62 — P1 content completeness / P2 presentation — Job detail lacks actionable explanation and salary localization

**Evidence: browser reproduced and code inspected.** `JobResults.svelte`, `research-jobs/[id].astro`, `format.ts`, `LiveWindows.svelte`. Screenshot: [CZU detail](work/audit4-2026-09-12/czu-job-zh-detail.png). Related: A05, A07, A10, A21, A24, A51.

Cards display an amount without its salary period. The detail renders `60000 CZK / month (gross)` in Chinese and Czech. The salary heading is always the gross label rather than following the tax field. The detail has high-level eligibility flags but little explanation of duties, required skills, degree evidence, contract, or application materials. No-window CZU records have unknown status, which is conservative and should not be changed to open merely because a possible employment date is known. Official-instructions roles lose that helpful action wording in the generic unknown-window fallback.

Implementation steps:

1. Extend the reviewed content bundle with short role summary, responsibilities, required qualification evidence, skill/experience conditions, contract term, materials and application instructions where the source provides them. Mark unknowns explicitly.
2. Add one shared salary formatter for amount/currency/period/tax and salary-basis versus position FTE. Use localized messages and currency formatting, with a clear monthly/annual/hourly label. Do not multiply a full-time basis into a promised part-time salary without explicit evidence.
3. Make list and detail use that formatter. Remove raw `month/gross` enum rendering; show net/gross/unspecified accurately rather than always using the gross heading.
4. Render job-specific evidence excerpts/review dates near the eligibility conclusion. “Master eligible” means the degree threshold, not automatic eligibility for every required skill.
5. Preserve `official_instructions` wording in the appropriate fallback branch, making clear that opening the notice is not submitting an application. Keep the direct official title link and secondary on-site explanation.
6. Distinguish source language from translated English title. The disclosure currently chooses `title.en || title.cs`; use actual source title/language instead.
7. Validate all three locales using one CZU part-time role, one full-time role, salary unknown, and a synthetic net/hourly salary fixture. Include date unknown and actual closed state.

Acceptance: a user can tell the pay period, tax basis, actual workload, degree threshold, other required conditions, and how to apply without reading raw enum names. Unsupported facts remain unknown. New field content must pass A53 review before publication.

## A63 — P2 — Mobile filter drawer does not manage keyboard focus

**Evidence: reproduced at 390px.** `JobResults.svelte` and the analogous sheet in `ProgrammeResults.svelte`; global filter-sheet CSS. On opening, focus stays on the trigger; the next Tab goes to a job title behind the overlay; Escape closes the sheet without returning focus to the trigger. Browser evidence records the exact focused element.

Implementation steps:

1. Extract a shared drawer/dialog component for the two filters so fixes do not diverge.
2. Use a native modal dialog or equivalent semantics with an accessible localized name, correct focus entry, inert background and contained Tab/Shift+Tab order. Follow the [W3C modal-dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).
3. Save the trigger element before opening. Move focus to the appropriate heading or first control, and return it on Escape, close button, backdrop close, and “view results”.
4. Keep the filter form usable on desktop; when resizing across breakpoints, restore overflow, remove inert state and leave a valid focus target.
5. Preserve live-result updates and URL state without closing unexpectedly. Ensure the mobile results action is reachable without a pointer.
6. Test repeated Tab and reverse Tab, Escape, breakpoint resize, scroll lock cleanup and focus restoration in all three locales. Check 200% zoom and long Czech labels.

Acceptance: while modal, focus never reaches a background job link; all close paths restore focus; desktop behavior remains nonmodal. Opening a visible overlay with no errors is not sufficient acceptance.

## A64 — P2 — Retry logic ignores server Retry-After

**Evidence: reproduced with a local mock.** `harvest_nine_hei_jobs.py::_request_bytes_with_retry`. The mock sends HTTP 429 and `Retry-After: 3600`; the code retries after 3 and 12 seconds. `docs/CRAWLING_RULES.md` requires respecting server delay. HTTP Retry-After supports a date or delay-seconds, as defined in [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after).

Implementation steps:

1. Preserve response headers in the transport result, including HTTPError responses. Keep source requests idempotent and bounded.
2. Parse both supported Retry-After formats against an injected UTC clock. Define behavior for absent, invalid, and past values.
3. Respect a valid server delay as the earliest retry. If too long for an in-process retry, return a deferred result to source scheduling rather than sleeping for an hour or immediately retrying.
4. Apply the deferred deadline to the source/host state and all entrypoints that could hit the same endpoint. One alternate task must not evade the source's cooldown.
5. Retain last-good content, partial-run status and SLA accounting. Do not classify throttling as opportunity closure.
6. Add deterministic transport/scheduler tests for delay-seconds, HTTP-date, 503 delay, missing header, malformed header and process restart.

Acceptance: no request occurs before a valid server deadline; absent headers retain bounded local backoff; long delays become observable scheduled retries. The audit did not measure actual upstream throttling or claim that a university blocked this project.

## A65 — P1 for operations — Durable deployed scheduling and coherent candidate capture remain incomplete

**Evidence: inspected design gaps.** `worker.py`, `schedule.py`, `file_lock.py`, `publish.py::_copy_required/_prepare_candidate/publish_snapshot`, `docs/REFRESH_POLICY.md`, `refresh_shards.py`.

The current Python file-backed scheduler is useful locally; it is not the deployed Go/PostgreSQL task system. There is also a narrower consistency risk: publication holds `.publish.lock`, while candidate mutation uses the worker's refresh lock. `_copy_required` copies files one by one without a shared candidate-generation transaction. Validating the copied directory prevents invalid bytes from becoming active, but cannot detect every structurally valid combination of different source generations. This is **not** a newly reproduced pointer-atomicity failure; the improved atomic publication pointer should remain.

Implementation steps:

1. Define durable task/source/run tables and a candidate generation ID before writing the Go runner. Include lease owner/token, attempt, last success, retry deadline, expected source set, complete/partial result, and artifact digest.
2. Make Go schedule the existing Python commands as offline jobs with explicit timeouts and result contracts. Do not rewrite every parser in Go. Separate long stable crawls from short safety checks, while preserving mutual exclusion for overlapping writes.
3. Use database transactions/fencing for deployed ownership and a consistent state snapshot. Test two runners, process death, lease expiry and stale-owner completion. Existing local OS-lock tests are a useful base, not deployment evidence.
4. For current file-based publication, capture an immutable candidate generation under the shared ingestion lock, then release the lock before expensive validation/build. Alternatively pin an already-sealed generation manifest. Document lock ordering to avoid deadlocks.
5. Bind every selected file to its generation/hash and record intentional cross-source versions. Do not assume all sources refresh together, but require the selected combination to be explicit and reviewable.
6. Resolve refresh-policy documentation contradictions: the document says missed shards wait for the next same-modulo day, while `get_pending_tasks` queues overdue catch-up. Preserve the user-required 120-hour objective and explicitly describe outage recovery. The sorted-index modulo assignment also changes when the baseline set changes; test/migrate assignments or stop saying each school keeps one shard forever.
7. Deploy persistent state, backups and restart policy after the environment exists. Prove short-period scheduling independently and observe a real stable 120-hour cycle before claiming sustained coverage.

Acceptance: publication sees one declared candidate generation; stale workers cannot overwrite newer results; failures do not advance success; lease/retry survives restarts. A full 120-hour real-world observation cannot be compressed into a unit test or promised as already complete.

## A66 — P2 — Coverage, freshness, and progress summaries are not synchronized or scope-consistent

**Evidence: reproduced by recomputation and inspected predicates.** `build_source_coverage.py::is_current_job/build_coverage`, stored `source-coverage.json`, `PROGRESS.md`, candidate `discovery` metadata, schedule state. Related: A35, A43, A45, A50.

The current stored report references an old publication and 10 sources. Recomputing produces 15 sources and 13 schools, but its last-run field uses a CZU-only result alongside the broader scheduled task timestamp. Its candidate predicate yields 90 whereas explicit supported/non-archived yields 77. Neither should be silently substituted for the other. The discrepancy also explains why repeated agent summaries can sound contradictory.

Implementation steps:

1. Define metrics precisely: inventory rows; discovered candidates; supported candidates; review-pending; approved; public; current-open; unknown-status; source-connected schools; fully assessed school scope. Store predicate/schema versions with metrics.
2. Persist source-run results by run ID and source ID. Keep single-source refreshes separate from all-source runs; record expected and completed source sets for every run.
3. Generate a release-bound coverage report after successful activation, using the selected publication version and explicit source-generation references. Historical reports retain their old timestamps and labels.
4. Include observedAt, fetchedAt, factReviewedAt, translationReviewedAt, publishedAt, lastStatusCheckedAt and nextDueAt as distinct values. Display only the dates that help the user assess freshness; keep operational details in the operator report.
5. Add stale/mismatch checks: a current report referencing an old active version must be labeled historical or regenerated; a single-source refresh cannot become an all-source success count; missing scope status must be classified explicitly.
6. Update PROGRESS from this evidence after each completed delivery. Keep historical runs in dated sections; remove stale current-state claims without rewriting old evidence.
7. Add alerts/visible backlog for delayed source runs and review queues. Reporting more frequent fetches is insufficient when review-to-publication age keeps rising.

Acceptance: every number has a denominator, timestamp, predicate and data layer; regenerating twice against the same pinned inputs gives the same factual counts; single-source CZU updates preserve the meaning of the last complete all-source run.

## 6. Secondary observations and limits for the next agent

These are inspected follow-up risks, not additional fully reproduced release blockers. Address them when touching the relevant path; do not use them to start an unrelated refactor.

- `storage.ts` catches malformed stored lists but write operations and preference reads can throw when storage is denied/full. Add a user-visible trilingual fallback and a denied-storage browser test when completing save/compare E2E. Current empty-page smoke tests do not cover this.
- `LocaleSwitcher.svelte` reads the URL, while search text is synchronized after a 300ms debounce. Test typing then immediately changing locale; do not claim unsynchronized input preservation without that interaction test.
- `formatDate` formats all datetime values in Europe/Prague rather than accepting each window's timezone. Test a non-Prague fixture if the data model permits it, or explicitly constrain the contract; do not let model and renderer disagree.
- `cityFromBaseline` treats the whole Jihomoravský region as Brno and falls back to a region label as city. This is an inference rule worth removing when location data is revised; this audit did not demonstrate a currently mislocated institution caused by it.
- Ordinary HTML request bodies have no explicit byte cap in the inspected generic fetch path, unlike some PDF paths. Add resource limits when consolidating transport; measure realistic sizes before choosing limits.
- Candidate/report publication could grow repository/artifact size substantially. Measure actual compressed browser payload, not only static page count. No new LCP/INP/p95, Mainland network, dependency-vulnerability database, penetration test, or formal ISO certification was performed.
- Current UI lacks many deeper product fields and complete operational tooling. Do not add accounts, reminders, payments, or an AI chat feature before the opportunity maintenance workflow works.

## 7. Round-three disposition

| Earlier item | Fourth-round disposition |
|---|---|
| A31 snapshot/browser bypass | Earlier fix retained; pinning regression tests pass. No renewed source-import bypass demonstrated. |
| A32 business publication gate | Significantly improved, but **partial**. A52–A55 demonstrate remaining acceptance gaps. |
| A33 atomic publish/rollback | Pointer and immutable selection improved; preserve them. A65 addresses candidate capture consistency, not a demand to revert the solution. |
| A34 multi-round job recheck | Existing regressions pass. No new whole-role false-closure case reproduced here. |
| A35 attempts/failures/retry | Existing tests pass; A64 finds Retry-After omission and A66 finds reporting scope problems. |
| A36 locks/leases | Existing independent-process tests pass locally. Deployed durable ownership still requires A65. |
| A37 dynamic discovery | Production adapters exist and registry has expanded to 15 sources. Full discovery-review-publication-closure workflow remains incomplete. |
| A38 qualification boundaries | Existing negative/multi-role tests pass. No fresh all-source factual recall/precision audit was performed; do not claim every candidate is correct. |
| A39 trilingual review | Source-string matching exists, but edited facts/translations and programme inputs are insufficiently bound. A53/A54 remain P1. |
| A40 map integration | User-authorized decision; not an audit violation. Documentation must continue matching the raster implementation. |
| A41 map fallback/keyboard | Prior browser evidence supports improvement. Broader mobile keyboard issue is in filter drawers, A63. Mainland/real-device acceptance remains unverified. |

## 8. Concrete first-agent assignment

Recommended first assignment: **A52 plus the minimum A53 review binding needed to protect edited facts**. Deliver a reviewable patch and counterexample corpus; do not attempt all fifteen product improvements at once.

1. Record `git status --short`, the current pointer, and the relevant file hashes. Preserve all unrelated dirty changes.
2. Run the baseline contract probe and read the JSON outcomes. Copy only the minimal failing input shapes into maintained regression fixtures; do not copy the entire audit's repeated snapshots into normal tests.
3. Agree the strict window/URL/salary and review-payload rules in the data contract. Use null/unknown where facts are absent; do not invent fields to satisfy validation.
4. Implement Python and Node checks together against the same corpus. Include the nested tracer representation actually used by rendering.
5. Generate a migration report for existing records that now fail. Keep old immutable snapshot directories unchanged. Build a new candidate only from corrected/reviewed records.
6. Run relevant unit tests, publication checks and type checks once. If they pass and no new concern appears, proceed to the required build/browser demonstration rather than repeating the same suite indefinitely.
7. Update acceptance trace entries and OPM only for changed behavior. Regenerate required diagrams/OPL and retain stated ISO mapping limitations.
8. End with a concise handoff: counterexamples now rejected, legitimate unknown/multi-round cases preserved, files changed, exact checks, migration state, and next bounded ticket.

Then assign **A56's first reviewed CZU programme slice** using the new contract. Its completion criterion is visible useful content in the webpage. A new parser function or another full raw crawl is not that completion criterion.

## 9. Commands and evidence index

Commands below run from the repository root unless a working directory is stated. Audit probes modify only the audit evidence directory. Production publish/rollback commands are intentionally not part of this audit replay.

```powershell
py -3 work/audit4-2026-09-12/probe_contract.py
py -3 work/audit4-2026-09-12/operational_probe.py
py -3 services/ingestion/src/build_source_coverage.py --output work/audit4-2026-09-12/coverage-recomputed.json
py -3 services/ingestion/src/publish.py --check
py -3 services/ingestion/src/publish.py --check-sources
py -3 -m pytest services/ingestion/tests -q
py -3 scripts/sync_locales.py
```

From `apps/web`: `npm ci`, `npm test`, `npm run check`, `npm run verify:published`, and, after implementation, `npm run build`. Run a local preview of that artifact before `py -3 work/audit4-2026-09-12/browser_audit.py` from the root. The audit browser script expects port 4321 and blocks all external HTTP requests.

From `services/catalog` and `apps/api`, separately run `go test ./...`. Go API's current “no test files” output must not be rewritten as endpoint verification.

| Artifact | Purpose |
|---|---|
| [contract-results.json](work/audit4-2026-09-12/contract-results.json) | Both validators' actual results for each new counterexample. |
| [probe_contract.py](work/audit4-2026-09-12/probe_contract.py), [probe_node.mjs](work/audit4-2026-09-12/probe_node.mjs) | Reproduction using isolated snapshots and regenerated checksums. |
| [operational-results.json](work/audit4-2026-09-12/operational-results.json) | Snapshot/candidate metrics, historical coverage metadata, mocked Retry-After, Git HEAD and fixture counts. Its `jobSchoolSourceCoverage` is explicitly taken from the historical stored report; use the recomputation for current coverage. |
| [coverage-recomputed.json](work/audit4-2026-09-12/coverage-recomputed.json) | Current registry and publication recomputation; 15 sources, 13 HEIs. |
| [browser-results.json](work/audit4-2026-09-12/browser-results.json), [browser_audit.py](work/audit4-2026-09-12/browser_audit.py) | 54-page smoke matrix and drawer keyboard reproduction. |
| [czu-job-zh-detail.png](work/audit4-2026-09-12/czu-job-zh-detail.png), [jobs-cs-mobile.png](work/audit4-2026-09-12/jobs-cs-mobile.png) | Captured local UI evidence. |
| [czu-job-zh-detail.txt](work/audit4-2026-09-12/czu-job-zh-detail.txt) | Rendered text for content inspection. |

Completion of this report means an audit and execution guide were delivered. It does not mean A52–A66 are repaired, the site is deployed, all schools are covered, or all official facts have been freshly revalidated.

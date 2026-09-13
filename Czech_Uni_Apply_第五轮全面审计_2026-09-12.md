# Czech Uni Apply — Fifth Audit and Agent Execution Guide

Audit date: 2026-09-12. Official-page capture: approximately 18:10–18:11 UTC (20:10–20:11 Europe/Budapest). Workspace: `D:\chatgpt\Czech_Uni_Apply`. Active publication: `v2026-09-12.4`.

**Owner addendum incorporated during this audit:** the public product is browse-only. Remove **My shortlist / 我的清单** and **Compare / 比较**. Do not introduce private user registration/accounts. This explicit decision supersedes the older project requirements for saving/comparing and future account synchronization. Historical test results below describe the current implementation, not a requirement to retain these features. See A80. The reported map obstruction is covered by A79, and the requested GitHub/guanfu.online strategy research by A81 and section 10.

## 1. Decision for the owner

**网页搜出的带薪科研与带薪博士机会明显不足。第四轮修改改善了发布契约、审核绑定、CZU 招生内容、弹窗和自动测试，但尚未解决本项目最重要的“真实机会能被完整搜到”。**

本次先核验学校官网，再回放现有解析器、检查候选及正式快照，最后实际打开构建后的网页。确认：

- 当前正式岗位 **5 条**，默认硕士可申请 **3 条**，要求博士注册的正式结果 **0 条**。
- MUNI 官网核实的 **4 条目标机会全部已进入候选库，却全部未发布**。其中 3 条为明确的博士招聘／资助机会，另一条为硕士可申请的实验研究岗位。
- MUNI 81701 官方金额为 **30,000 CZK net**；候选库却是 **0 CZK / month / gross**。错误仍可用当前代码重现，幸而审核门禁阻止了公开。
- 搜索 `CZU` 实际返回 **0 条**；搜索 `Czech University of Life Sciences` 返回 **3 条**。这是站内检索漏检，与官网有没有岗位无关。
- CZU 中央公开列表本次读取 **6 条公告**，与同站正文接口对应成功；**5 条研究／技术候选**中含 4 条硕士门槛的 transfer-assistant 公告及 1 条博士学位门槛岗位，另 1 条行政公告被正确排除。这不代表六学院博士资助机会全部覆盖。
- 注册表有 **24 个岗位来源，连接 22/54 所高校（40.7%）**；这不是岗位召回率。32 所高校尚无注册岗位来源，全校完整性声明仍为 0。

下一阶段优先级应是：**修正提取 → 重放已抓正文 → 完成真实三语审核 → 发布一批可逐条核对的机会 → 修复别名检索 → 扩大来源覆盖并持续测量漏检**。不能靠放松审核、编造开放日期、批量绑定旧审核或把博士项目目录全部算成带薪岗位来增加数量。

This report is an audit and implementation specification. It does not approve or publish the audited candidates. The audit scripts write only under `work/audit5-2026-09-12/`; normal build/check commands also regenerate their usual derived artifacts. No business-code fix, source refresh merge, publication activation, commit, or remote deployment was performed by this audit.

## 2. Evidence, scope, and baseline

### 2.1 Authoritative local artifacts

Read [PROGRESS.md](PROGRESS.md), the required project documents, and the [fourth audit](Czech_Uni_Apply_第四轮全面审计_2026-09-12.md), but assess claims against current code and execution evidence.

| Artifact | Purpose |
|---|---|
| [official-probe.json](work/audit5-2026-09-12/official-probe.json) | Official GET attempts, timestamps, saved response hashes, MUNI parser outputs, CZU listing/body correspondence |
| [probe.py](work/audit5-2026-09-12/probe.py) | Reproducible official-source probe using installed Scrapling 0.4.9 |
| [local-results.json](work/audit5-2026-09-12/local-results.json) | Actual immutable-publication counts, candidate/publication comparison, isolated review-rebinding reproduction |
| [local_probe.py](work/audit5-2026-09-12/local_probe.py) | Offline replay of captured MUNI pages through the current discovery-to-record pipeline |
| [muni-replay.json](work/audit5-2026-09-12/muni-replay.json) | Full offline replay output, including records, windows, evidence and incomplete-source information |
| [browser-results.json](work/audit5-2026-09-12/browser-results.json) | Actual browser queries, card counts and visible main text from the newly built site |
| [browser_probe.py](work/audit5-2026-09-12/browser_probe.py) | Local built-artifact browser probe; no submissions or remote mutations |
| [CZU search screenshot](work/audit5-2026-09-12/czu.png) | `CZU` query yields zero despite three published CZU jobs |
| [Doctoral-filter screenshot](work/audit5-2026-09-12/doctoral.png) | Required doctoral enrollment yields zero |
| [safety-results.json](work/audit5-2026-09-12/safety-results.json) | New closure generation replaced by older empty generation; initial fetch failure reported non-stale |
| [safety-probe.mjs](work/audit5-2026-09-12/safety-probe.mjs) | Isolated browser-subscription state reproduction |

**Resolve `data/published/current.json`, then its `snapshotDir`. Do not count `data/published/current/`.** That legacy directory still contains a different, older job set. The site uses the immutable alias; the active five-job count here comes from `snapshots/v2026-09-12.4`, not the legacy directory. A successful local file-presence check is not proof of a clean Git checkout.

The source/candidate file has 128 records. Under the broad current predicate (not archived and lifecycle not closed/expired/unavailable), 90 remain: 5 approved and 85 review-pending. Under the narrower included-scope predicate, the existing coverage report reports 77, including 74 pending and 3 approved. These are different denominators; neither 90 nor 77 means independently verified open paid vacancies. In particular, `unknown` is included.

### 2.2 Boundaries

This is a focused official-source recall audit plus broad regression review of the fourth-round changes. It is not a census of all Czech vacancies. MUNI's four positive examples are a deliberately selected diagnostic sample, not a statistically representative recall estimate. The MUNI English landing page exposed eight vacancy links; the current title filter retained five. The three rejected links were not all fully audited, so this report does not call all three false negatives.

CZU's central source was checked live through Scrapling GET, WP Job Manager public pagination and its same-site public REST bodies. All eight requests in the saved probe returned 200 after an initial sandbox-proxy failure was rerun with authorized network access. A JavaScript browser was unnecessary for this successful public-interface cross-check. This does not independently prove the accuracy of every extracted qualification or the completeness of every CZU faculty channel.

The remaining 22 registered job sources were not all live-crawled in this audit. No claim of a successful all-source refresh is made. Hosted GitHub execution, branch protection, deployment, scheduler operation, CDN propagation, accessibility certification, mainland-China connectivity and real-device behavior remain unverified.

## 3. Official university verification first

### 3.1 MUNI positive reference set

All four links were visible on the [official MUNI careers page](https://www.muni.cz/en/about-us/careers) and their individual bodies were fetched for this audit. The source facts below are deliberately concise; preserve full local raw evidence separately.

| Official vacancy | Verified facts relevant to inclusion | Existing stored candidate | Current replay / publication consequence |
|---|---|---|---|
| [81701 — Fully Funded PhD, eukaryotic translation control](https://www.muni.cz/en/about-us/careers/vacancies/81701) | MSc/equivalent; doctoral research; ERC-funded salary starting at 30,000 CZK net; deadline 2027-01-08 with rolling review. The retrieved salary sentence does not explicitly state payment cycle. | `job-14000-81701`; minimum degree unknown; paid confirmed; amount 0, month, gross; pending | Full record replay now recognizes master and required enrollment, but retains wrong monetary facts. Not published. |
| [81652 — Ph.D. Fellowship, RECETOX](https://www.muni.cz/en/about-us/careers/vacancies/81652) | MSc/equivalent; four-year financially supported doctoral programme; 0.5 FTE employment, 20 hours/week; deadline 2026-09-20; funding details linked to RECETOX. | `job-14000-81652`; qualification unknown; paid unconfirmed; enrollment unspecified; pending | Replay improves master eligibility, but still misses paid status, enrollment and FTE. Not published. |
| [81369 — PhD Candidate, viruses and protein synthesis](https://www.muni.cz/en/about-us/careers/vacancies/81369) | MSc/equivalent; part-time contract plus PhD stipend; deadline 2026-11-30; English required; negotiated February 2027 start. | `job-14000-81369`; qualification unknown; paid unconfirmed; enrollment unspecified; pending | Replay improves master eligibility; funding and enrollment remain missing. Not published. |
| [81700 — Research Specialist, structural biology](https://www.muni.cz/en/about-us/careers/vacancies/81700) | M.A./Ph.D. alternatives; laboratory experiments and potential independent research; compensation described; English required; deadline 2027-01-08. No numerical pay inference needed. | `job-14000-81700`; master, doctorate false, paid confirmed, included scope, pending | Still pending, despite useful eligibility already extracted. Not published. |

For this four-record set: **discovered 4/4; publicly available 0/4**. For its three explicit doctoral opportunities: **publicly available 0/3**. This demonstrates an extraction/editorial/publication bottleneck even before expanding source discovery. Do not describe it as a demonstrated 0% nationwide recall rate.

A subtle but important distinction: `parse_generic_job_page()` alone truncates eligibility input to 4,000 characters and misses 81701's MSc requirement. The subsequent `job_record()` replay reads full scoped text and repairs that particular qualification. The stored candidate still contains the older unknown result. Therefore there are **two** issues: an inconsistent intermediate contract, and previously harvested records not replayed after parser changes. Removing the 4,000-character slice alone will not repair stored records or publish them.

### 3.2 CZU: central vacancies and doctoral funding are separate channels

The [central CZU jobs site](https://jobs.czu.cz/) exposes a public WP Job Manager result set. The captured result contained IDs 1605, 1604, 1603, 1602, 1601 and 1598. The same IDs were fetched from the site's public REST endpoint; public titles and URLs matched.

| Source IDs | Audit disposition | Active publication |
|---|---|---|
| 1604 T1, 1603 D1, 1602 A1 | Current parser returns master threshold, doctorate false, paid confirmed; individually distinct technical transfer roles | All three published |
| 1601 A2 | Same broad target eligibility; current public source still contains it | Not published; PROGRESS records changed evidence hash and pending re-review |
| 1598 FLD assistant, forest bioeconomy/circular economy | Parser reports doctorate required; must inspect full qualification before any new classification | Not published; not a master-entry doctoral vacancy merely because the title contains assistant |
| 1605 administrative role | Correctly quarantined outside research/technical scope | Not published |

Do not reverse A2's invalidation by copying the old review hash. Compare old/new scoped evidence, identify material changes, and complete a new review. A source still appearing in a listing is not independent proof that every term or deadline remains unchanged.

Doctoral financing also appears in institutional/faculty documents, outside central employee vacancies. The [CZU scholarship regulations page](https://www.czu.cz/cs/r-7210-o-czu/r-7702-oficialni-dokumenty/r-7810-vnitrni-predpisy-univerzity/r-8734-vnitrni-predpisy-podle-zakona-o-vysokych-skolach/stipendijni-rad-czu.html) links the version effective from 2026-01-06 and older superseded versions. This is a **funding-policy source**, not a current individual vacancy. The audit did not establish eligibility or amounts for a new CZU doctoral applicant from that document. The next agent must inspect the effective source and applicable faculty rules, then join them to a real recruitment/admission opportunity. Do not multiply 60 doctoral register offerings into 60 paid jobs.

### 3.3 CTU: why discovering a page is not enough

The official [AIC doctoral pathway](https://www.aic.fel.cvut.cz/careers/phd-in-artificial-intelligence) describes master's entry, scholarship plus project work, and an approximate combined financial package. It is useful evidence for a funded doctoral pathway; it should not be split into an invented number of funded seats or treated as a newly dated vacancy.

The [AIC optimization PhD notice](https://www.aic.fel.cvut.cz/careers/phd-near-real-time-optimization) contains a monthly salary description but also a deadline of 2026-02-25 **or until filled**. In September, that needs a reviewed rolling/availability interpretation and current listing evidence. This audit does not certify it as presently open. Do not automatically archive the whole opportunity based solely on the first date, or automatically declare it open because the URL returns 200.

The registered recurring CTU sources are its central notice board and FEE careers listing. AIC's own careers collection is not separately registered as a recurring listing adapter. Historic AIC seeds do not establish continuing discovery of new laboratory opportunities.

## 4. Fourth-round repair assessment

| Prior item | Fifth-round assessment | Evidence / remaining limitation |
|---|---|---|
| A52 publication contract | Substantial verified improvement | Python/Node shared malformed-data corpus runs; active and next-source selection checks pass. This validates contracts, not source truth. |
| A53 hash-bound review | Partially repaired; reopen | Old review no longer automatically matches changed facts at the publication gate, but `--bind-review-payloads` can silently rebind changed facts while retaining reviewed statuses/dates. See A75. |
| A54 tracer/programme review gate | Improved in local implementation | Explicit approval required in browse overlays; contract tests pass. Full multilingual content quality is not established by hashes. |
| A55 CSCSE claims | Correct direction implemented | Official reference is unverified without official evidence; operator-list membership is separate. No new official-recognition verification performed here. |
| A56 CZU reviewed programmes | Visible content increment delivered | Four reviewed offerings and five windows are in the immutable snapshot. They are a small reviewed slice, not complete CZU admissions. |
| A57 job coverage | Partial, core outcome still failing | Registry grows to 24 sources/22 HEIs, yet five public jobs and zero required-enrollment results. Five new source entries were not fully run live by the prior agent. |
| A58 safety closure propagation | Useful local mechanism; incomplete correctness | Versioned overlay and polling exist. Older responses can replace newer closure state; initial fetch failures are not marked stale. Hosted propagation unverified. |
| A59 production API fixture default | Locally repaired | API defaults to immutable publication, fixture opt-in explicit; both Go module tests pass. Running service/deployment parity unverified. |
| A60 CI/CD | Configuration improved; not operating CI/CD | No Git remote configured. All-local green claim is currently false because one time-dependent Python test fails. Local inventory check does not prove committed checkout completeness. |
| A61 maintained browser checks / OPM | Improved | Built-artifact suite exists; controlled rerun 39/39 passes. OPM check passes. Tests lack end-to-end official-positive recall assertions. |
| A62 useful localized content | Partial | Salary formatting is centralized, but upstream monetary extraction is wrong for an audited candidate. Search/empty-state text still refers to programmes and teaching languages on the jobs page. |
| A63 modal focus | Substantial local improvement | Drawer focus, Escape/restore and responsive checks pass with two workers. One initial 16-worker run failed to open zh-CN mobile nav; no conclusive root cause established. |
| A64 Retry-After | Implemented with regression in test determinism | Seconds/date handling exists. One cooldown test uses a fixed absolute expiration and fails after it. |
| A65 candidate capture / scheduler | Capture improved; deployment unfinished | Generation/locking changes and tests exist; Go scheduler remains a documented/SQL plan, not observed persistent operation. |
| A66 coverage reporting | Better predicates, still misleading edges | Distinct scopes now available. Programme publication subtotals remain hard-coded zero; older PROGRESS tables contradict newest implementation. |

The map's early integration is an explicit owner decision and is **not a defect**. Keep unmodified mouse-wheel zoom. Current maintained map E2E cases cover tile success/fallback, not actual wheel-driven zoom; preserve the earlier behavior and add a targeted interaction assertion when next editing map tests.

## 5. New findings and exact implementation instructions

Severity here reflects user impact: P0 must precede the next trustworthy content release; P1 materially blocks coverage or reliable operation; P2 improves measurement and usability. IDs continue after A66. The following are work packages, not claims that their changes have already been made.

### A67 — P0: Monetary extraction corrupts a real funded PhD salary

**Observed:** `parse_generic_job_page()` parses the trailing `000` in `30,000 CZK` as zero. `job_record()` assigns `month` and `gross` whenever an amount is non-null, irrespective of evidence. This survives the full replay and already exists in the stored candidate for 81701.

**Files:** `services/ingestion/src/harvest_nine_hei_jobs.py` (`parse_generic_job_page`, `job_record`), relevant ingestion tests, publication rules/schema if required, salary formatting only if new fields require it.

1. Add a minimized source-derived fixture for 81701 plus cases for `30,000`, `30 000`, nonbreaking/thin spaces, Czech decimal commas, ranges and annual packages. Keep negative controls for grant budgets, expense allowances and unrelated costs.
2. Parse an entire numeric token with boundaries; never begin in the middle of a number. Normalize separators using source/currency context. Ambiguous text remains unknown with an extraction reason.
3. Extract amount, currency, tax basis, payment cycle, range and employment FTE independently, each with evidence. Do not copy a grant's annual value into a salary or assume that any amount is monthly gross.
4. For 81701, review 30,000 CZK as net. Leave cycle unknown unless the specific source or a directly applicable linked official document supplies it. Preserve that unknown through `job_record()` and publication.
5. Replay affected saved pages into a new candidate generation; invalidate materially changed approvals. Review the corrected evidence and translations before release.
6. Acceptance: no zero from the audited token; no invented gross/month flags; existing CZU salary basis versus actual FTE tests remain valid. The exact browser amount must match the reviewed record in all locales.

### A68 — P0: Paid doctoral opportunities are misclassified as unfunded or enrollment-unspecified

**Observed:** MUNI 81652 and 81369 remain `paidStatus=unconfirmed` and `doctoralEnrollment=unspecified` after current full replay, despite the official evidence above. `assistant_enrollment()` recognizes some title variants but not fellowship/PhD-candidate combinations; funding patterns miss contract-plus-stipend and supported-programme wording. The 0.5 FTE/20h expression is also missed.

1. Separate classifications: research duties, prior degree, doctoral enrollment, compensation type, amount, work hours and current application status. An R1 code or job title cannot establish all seven.
2. Extract qualifications and enrollment from complete vacancy body and relevant attachments, not a fixed character prefix. Preserve source sections/spans to avoid faculty boilerplate contaminating a vacancy.
3. Add funding types such as employment, stipend/scholarship and mixed package to the canonical model, with an explicit unknown. If the existing schema can express them, use its vocabulary rather than inventing a parallel field.
4. Recognize positive evidence like part-time contract plus doctoral stipend and financially supported doctoral recruitment; add negative controls for optional competitive grants, travel-only reimbursement, self-funded PhD, postdoc and research administration.
5. Confirm 81652's linked RECETOX funding terms and programme relationship. Keep guaranteed terms separate from conditional or competitive components. Do not derive guaranteed salary from a generic scholarship landing page.
6. Use full role-specific evidence to review required doctoral registration for the two doctoral notices; leave 81700's enrollment unspecified unless an explicit statement supplies it.
7. Acceptance: the three doctoral positives have correct master-entry and enrollment facts and confirmed funding evidence; postdocs remain excluded from default master results. The actual employment FTE of 81652 is 0.5, independent of any salary normalization basis.

### A69 — P1: Parser improvements do not backfill candidate records

**Observed:** stored MUNI 81701/81652/81369 have unknown qualification, while today's offline full-record replay resolves master eligibility. Parser-unit output and final records also disagree because of the 4,000-character slice.

1. Record parser/extraction version and raw evidence hash with each candidate. Preserve `sourceFetchedAt`, `factsExtractedAt` and `factsReviewedAt` separately.
2. Provide a bounded replay command selecting source IDs and parser version. Replay immutable raw responses into an isolated candidate generation without pretending a network check occurred.
3. Compare old/new normalized facts, emit reasons and affected review IDs, and atomically merge under the existing refresh/publication lock discipline.
4. Re-fetch evidence when raw input is missing or stale; do not fabricate it from the original title. Replay cannot establish that yesterday's vacancy is still recruiting today.
5. Avoid multiple independently authoritative qualification paths. Either one full-document extraction result feeds record construction, or reconcile discrepancies explicitly and fail to review-pending.
6. Acceptance: MUNI replay changes are visible in candidate facts; fetched timestamps are unchanged by offline work; reviewed facts changed by replay require renewed approval; no duplicate IDs are created.

### A70 — P0: Review-to-publication throughput is the immediate recall bottleneck

**Observed:** all four MUNI reference jobs were already discovered and remain pending. Merely adding a new crawler does not make them searchable. There are 85 pending records under the broad current predicate; many need exclusion or evidence work, so do not call all 85 publishable.

1. Produce a per-record queue with canonical ID, official URL, source freshness, deadline, paid/qualification blockers, missing locale reviews, evidence change reason and owner. Keep terminal exclusions with evidence.
2. Start with MUNI 81652 because of its 2026-09-20 deadline; then 81369, 81701 and 81700. Review CZU A2's source change in the same bounded tranche.
3. For each, verify current official application instructions, full eligibility, compensation, enrollment, scope and latest deadline before writing the review bundle. Translate actual user-facing facts into zh-CN/en/cs; a hash operation is not review.
4. Run publication checks and create one immutable content release containing the approved tranche. Inspect its exact diff and count changes. Build and verify those exact IDs through default, institution and funded-doctoral queries.
5. Completion is **4/4 MUNI positives represented by correct reviewed public records or newly evidenced closure/exclusion**, not a quota to force four listings regardless of changed reality. For the three doctoral positives, verify funded-doctoral discoverability separately. A2 requires its own new review, not a mandatory count increase.
6. Set an editorial processing target and report queue age/deadline risk. Suggested initial target: triage newly discovered likely eligible vacancies within one working day, with an explicit operator responsible. This is a proposed service target, not current operation.
7. Stop after the slice is delivered and verified. Report newly visible IDs, not only test counts or files changed. Then repeat for the next small cohort.

### A71 — P1: Search misses common institution aliases and doctoral intent

**Reproduction:** built `/en/research-jobs/?track=all&q=CZU` → 0; full English institution name → 3. `filterJobs()` searches concatenated titles and institution names with one substring; it omits an explicit alias index and job city/body/specialism fields. The UI nevertheless advertises programme/institution/city search.

1. Add a reviewed institution alias table keyed to baseline IDs: CZU/ČZU/Česká zemědělská univerzita, MUNI/MU/Masarykova, CTU/ČVUT, and other official acronyms. Resolve ambiguous short aliases rather than matching arbitrary substrings.
2. Normalize case, diacritics, punctuation, whitespace and Ph.D./PhD variants. Tokenize multiword queries; avoid requiring the entire phrase to occur contiguously in one concatenated string.
3. Index reviewed titles, official names/aliases, faculty/laboratory, city and reviewed research subjects. Avoid indexing unrelated source boilerplate as eligibility evidence.
4. Add a clear funded-doctoral discovery control using structured funding/enrollment/degree facts. It can be a derived filter instead of a disruptive new employment track. Preserve the distinction between incoming doctoral applicants and roles requiring an already completed doctorate.
5. Preserve default master eligibility and visible postdoc exclusion. Locale changes must preserve the same query and entity set, not infer working language.
6. Replace jobs-page search labels and empty messages with job-specific trilingual text. An empty job result must not say that other teaching languages were withheld.
7. Acceptance: CZU alias/full-name queries yield the same current IDs; spelling and locale variants pass a shared query corpus; master/funded-PhD controls find the reviewed MUNI tranche; unrelated postdocs and unpaid leads do not leak into those results. Do not implement embeddings before this baseline is correct.

### A72 — P1: Source registration is not comprehensive discovery

**Observed:** 24 sources/22 HEIs; no full-school assessment; 32 schools missing. Existing MUNI listing and generic no-pattern discovery can discard links by title before reading body. AIC has static seeds but no dedicated registered recurring listing. These are source-coverage/recall risks; this audit does not claim an exact number of lost vacancies for each.

1. Create a source map for each of the 54 baseline HEIs: central HR, Czech/English notice boards, faculties, doctoral schools, funded project calls and laboratory recruitment. Record verified central-to-faculty aggregation evidence rather than assume it.
2. For CZU, inventory all six faculty recruitment/doctoral channels first. For CTU, include AIC/CIIRC and relevant doctoral calls. For MUNI, reconcile Czech and English central listings with CEITEC/RECETOX and faculty doctoral pages. Then address remaining HEIs, including ZČU, arts institutions, state and private schools; none may be dropped solely for language/ranking.
3. Enumerate detail links using official IDs, URL patterns, list metadata and pagination. Title terms are prioritization hints. If uncertain, fetch the body or retain an unresolved discovery event instead of silently dropping the link.
4. Compare all pages against official reported totals where available, detect duplicate/missing pages, and cross-check sitemaps or language variants. Distinguish listings visited, unique announcements, advertised seats and supported opportunities.
5. Follow official PDF attachments and source-linked public ATS interfaces; use installed Scrapling escalation for difficult pages and record failures. Do not count a shell/HTTP200 response as extracted vacancies.
6. Use external search/EURAXESS only to discover official leads. Verify employer, source and official application destination before acceptance. Do not submit forms or contact faculty while collecting evidence.
7. Run each newly registered source live before marking it operational. Capture `attemptedAt`, `completedAt`, detail coverage, pagination completeness and reason-coded failures. Keep incomplete sources in an overdue/error queue.
8. Acceptance: all 54 HEIs receive a documented source assessment, including evidence-backed no-source-found outcomes; every selected source has a reproducible live run; a separately sampled official positive set has a recorded disposition through the pipeline. No “all jobs in Czechia” claim without a defensible denominator.

### A73 — P1: Funded doctoral admissions need an explicit joined discovery route

This is an architecture/product coverage gap, not proof that every doctoral programme offers an employment contract. Current central-job crawling cannot by itself cover faculty-funded doctoral calls.

1. Define opportunity kinds that distinguish a specific salaried PhD vacancy, a mixed contract/stipend position, and an admissions route with conditional funding. Keep funding policy documents as supporting entities.
2. Connect each funded doctoral opportunity to institution, faculty, programme/offering, intake/year, supervisor/project when officially supplied, application window and funding components. One opportunity may be discoverable from both programme and jobs views without being counted twice.
3. For CZU, inspect the currently effective scholarship regulation and faculty-specific applicability, then examine admission rounds, supervisor topics and project recruitment across AF/FAPPZ, PEF, TF, FŽP, FLD and FTZ. Confirm programme language separately from work language.
4. The existing 60 doctoral baseline offerings and 2026/27 window mapping are useful inventory; do not infer 60 current funded seats or unannounced 2027/28 rounds. General regulations require cohort, study-mode and other applicability evidence before being attached to an individual opportunity.
5. Preserve mixed funding components, conditions, amount/cycle/tax unknowns, time validity and distinction between application and employment start. Never sum gross employment and stipend components into a misleading net take-home figure.
6. Update `docs/DATA_MODEL.md`, `docs/PRODUCT.md`, relevant schemas, OPM objects/states/processes and requirement tracing when implementing this route.
7. Acceptance: at least one independently verified doctoral recruitment route can travel from official call and applicable funding evidence through review into both relevant user journeys, with stable deduplication and accurate conditions. If no new CZU call is open, show the actual next/closed/unknown state rather than invent a vacancy.

### A74 — P0 for CI: A new cooldown test expires on the day it was written

**Observed:** `test_deferred_retry_after_does_not_archive_or_hit_source` in `services/ingestion/tests/test_nine_hei_jobs.py` sets cooldown until **2026-09-12 18:00 UTC** but discovery checks the actual clock. At audit execution after that time the cooldown correctly expires, the fake transport raises, and the suite fails. An elevated rerun gives **167 passed, 1 failed**, confirming this is not the initial Windows file-replacement permission error.

1. Inject/freeze the same clock for setting and checking host cooldown. Test before expiry, exactly at expiry and after expiry.
2. Assert that a deferred source makes no request and does not archive prior records; after expiry, assert that it becomes eligible for a request.
3. Keep the production semantics. Do not move the hard-coded expiry to another future date or broadly skip the test.
4. Run the complete Python/OPM suite at a fixed historical and future clock where practical. Do not label local CI green until the actual suite passes.
5. Finish the delivery prerequisites separately: explicit review of intended tracked files, a reproducible clean checkout, remote workflow run, branch policy and configured deploy target. No Git remote currently exists; workflow YAML and artifact upload alone are not a running public CI/CD pipeline.

### A75 — P0: Review migration helper can bless modified facts with old approval

**Reproduction:** `local_probe.py` copies candidates/reviews to the audit directory, changes CZU T1 salary to 123456, and calls `bind_review_payloads()` on the copies. The helper replaces `factHash` with the changed record's hash and leaves all three locale statuses `reviewed` with their original review timestamps. No source/translation review occurred. The isolated hash changes are saved in `local-results.json`.

This is an exposed operator/migration workflow weakness; it is not evidence that the running crawler automatically executes that flag or that arbitrary unauthenticated users can do so.

1. Make legacy migration explicitly one-time and reject already fact-bound entries. Require the exact legacy source hash and expected prior record generation as input.
2. For a fact-bound record, fail on fact/evidence/translation mismatch. Do not silently replace the hash. Create a pending review request with a fact diff instead.
3. Separate normalization migration from actual editorial approval. Re-review must record who/what role reviewed which exact evidence and payload, at a new review timestamp, with a review event ID.
4. Preserve prior reviews append-only. A migration cannot claim a past reviewer approved facts introduced later.
5. Acceptance: this exact 123456 mutation cannot retain approved status by running a generic binding command; legitimate unchanged legacy migration has a narrowly scoped test. Never use this helper to clear the MUNI/A2 queue.

### A76 — P1: Safety polling accepts older generations and conceals first-fetch failure

**Observed:** `safety-probe.mjs` feeds generation `.2` containing a closure followed by older empty generation `.0`. `subscribeSafetyOverlay()` emits both as non-stale and replaces the closure with the empty overlay. A first request failure emits `{overlay:null, stale:false}`. Source: `apps/web/src/lib/safetyStatus.ts`, especially `parseSafetyOverlay` and `subscribeSafetyOverlay`.

1. Compare generations with a validated ordered representation, not lexical suffix ordering. Ignore responses older than the accepted high-water mark, including concurrent/out-of-order polls and stale CDN responses.
2. Keep the last accepted closure across fetch errors. For returning clients, define whether durable cached status is necessary; do not claim persistence across page reloads without implementing it.
3. Treat first-fetch failure as unavailable/stale even when no prior good overlay exists. Distinguish request failure from an empty, successfully verified overlay; enforce source/status age thresholds, not just HTTP success.
4. Validate required overlay fields and all records atomically. Silently dropping malformed closures can turn invalid input into a valid empty overlay.
5. Reopening needs a newer explicit reviewed event; deleting a closure record from a response is not equivalent to proven reopening.
6. Add out-of-order, stale empty payload, malformed entry, initial failure, offline/reload and permitted reopening tests. Cover retained list/detail/API behavior; do not retain saved pages after A80 merely to test them.
7. Verify deployment updates the status endpoint independently of the static content build and measure propagation. The current empty local overlay cannot establish production closure latency.

### A77 — P2: Coverage reporting still contains hard-coded and ambiguous counts

**Observed:** `build_source_coverage.py` hard-codes `formallyPublishedFromThisCandidateSource: 0` for all three CZU programme channels although four reviewed CZU offering records now include candidate provenance. Existing report is bound to the current version but those subtotals were not joined to it. Broad and included-scope queue totals also differ legitimately.

1. Compute publication attribution by joining active reviewed offerings' `candidateIds`/evidence to each candidate source. Count a publication once globally; per-source attribution may overlap and must say so.
2. Report distinct stages: baseline assessed, registered sources, completed source runs, discovered unique announcements, supported current candidates, paid/master positives, reviewed public records, current searchable records and dated/unknown status.
3. Bind each row to source/run ID and timestamp. Do not reuse a global success timestamp as per-source success without an actual successful attempt for that source. Audit existing legacy state before accepting it.
4. Surface per-source overdue state, parser version, review backlog age and losses by reason. Refresh settings of 1/2/4/120 hours are configuration, not achieved freshness.
5. Correct PROGRESS's older verification tables or explicitly label them historical. Change the checkout script's static “local checks passed” wording to “inventory check passed” unless supplied verified suite results.
6. Acceptance: a synthetic single-source run cannot advance every source's success time; newly reviewed CZU programmes change attribution counts; all displayed totals have a named denominator and immutable publication version.

### A78 — P2: Browser acceptance needs content and hydration assertions

**Observed:** initial local E2E run actually used 16 workers and produced 38 passes plus one zh-CN mobile-nav dialog timeout. A direct CLI rerun with two workers passed 39/39. The failure is a reproduced run outcome, not a proven permanent focus-trap defect. The built job screenshot also uses programme/city search wording and teaching-language empty-result guidance.

1. Keep a controlled worker count and save failure traces before reruns replace their output. On this Windows setup `npm run test:e2e -- --workers=2` did not apply the requested limit; direct Playwright CLI did.
2. Investigate whether navigation buttons accept a click before hydration. Add readiness/disabled semantics or a meaningful loaded-state assertion if reproduced; do not hide the defect by an arbitrary long sleep.
3. Extend maintained browser tests with the reference-set queries and exact expected IDs, localized funding labels, qualification text and official application targets. A nonempty generic job list is insufficient. Replace obsolete save/compare tests with A80 removal assertions.
4. Verify actual wheel zoom without Ctrl, not only tile availability; preserve map offline fallback and current owner decision.
5. Use job-specific labels/empty states in all locales and align search's advertised fields with its implementation.
6. Acceptance: three-locale phone/tablet/desktop journeys pass against the exact delivery artifact; report any transient failed first run as well as the controlled rerun. Do not claim tested real devices or exhaustive accessibility.

## 6. Execution order that produces visible improvement

### Gate 0 — Establish the reviewable baseline

1. Read AGENTS and required documents; read this report's evidence files before changing business rules.
2. Capture `git status --short`, active publication pointer, source/review hashes and exact test commands. Preserve all existing dirty/untracked work. Do not stage the entire workspace or delete old audits.
3. Create a small official reference manifest containing the four MUNI IDs, CZU T1/D1/A1/A2, and negative controls (CZU administrative role, doctorate-required role, closed notice, general funding policy). Record observation time and expected disposition, not an eternal open assertion.
4. Repair A74 so the validation baseline is usable. Protect review binding (A75) before using any migration command. Keep these changes reviewable and narrowly scoped.

### Gate 1 — Deliver the first content tranche

1. Fix A67/A68 against the captured official fixtures; then re-fetch the selected pages for current facts.
2. Apply A69 replay/diff to those records. Produce a candidate report showing old and new facts and missing evidence.
3. Complete A70's actual review, translations and official application check. Pair A71 alias search with the release so already published CZU records become discoverable immediately.
4. Publish a new immutable snapshot through the existing gate, build it, and verify exact official IDs in the browser. Keep old snapshots and the independent safety generation.
5. Deliver a concise owner report: before/after master and doctoral result counts, URLs/IDs added, evidence-backed exclusions, remaining queue size and next source cohort. A content tranche is unfinished until its approved records appear in the tested webpage.

### Gate 2 — Expand repeatable discovery

1. Map CZU's six faculties and CTU/MUNI subunit channels, then the other baseline HEIs.
2. Connect and actually run a small source cohort; audit pagination and official-detail coverage before increasing its claimed coverage.
3. Produce a new independently sampled positive set from official pages. Trace each positive to published, pending with reason, closed or excluded with evidence. Track negative controls separately.
4. Repeat review/publication in bounded cohorts. Keep a maximum work-in-progress queue appropriate to available review capacity; fetching more pages without reviewing them is not user-visible completion.

### Gate 3 — Make freshness operational

1. Implement the documented persistent Go scheduler with PostgreSQL state/leases; invoke the existing Python worker offline. Persist retries, host cooldowns, run IDs, partial progress and overdue recovery across restarts.
2. Retain 120-hour baseline coverage and the authorized shorter source cycles. Ensure cohort scheduling does not starve quiet institutions; respect source throttling and Retry-After.
3. Couple successful candidate generations to explicit review tasks and safety status changes. Content review latency must be measured separately from fetch latency.
4. Repair A76 before relying on status polling for public closure guarantees. Set and test endpoint cache behavior in the actual target environment.
5. Establish a clean-checkout remote CI run and deployment from the tested artifact. Record remote run URL, commit SHA, publication version, status generation, deployed URL and smoke checks. Do not call a locally built artifact “deployed”.

Each agent handoff must include: exact owned files, source IDs, starting publication and parser versions, evidence directory, required commands, dependencies, acceptance IDs, observed result IDs and unresolved blockers. Prefer one complete source-to-visible-result slice over simultaneous unrelated refactors. Subagent delegation is not required by this report.

## 7. Required metrics and stop conditions

| Metric | Definition / required boundary |
|---|---|
| Official reference discovery recall | Reference opportunities found / independently identified official positives, within the declared source/date sample |
| Official reference public recall | Correct reviewed public records / eligible current positives in that same sample; report pending ones as misses with reasons |
| Search recall | Expected published IDs returned for reviewed alias/intent queries; independent of crawler recall |
| Qualification/funding accuracy | Field agreement with annotated source evidence; include false master eligibility and falsely confirmed funding as failures |
| Source completeness | Unique official listing IDs and fetched details, pagination coverage and declared scope; distinguish notices from headcount |
| Editorial latency | Discovery-to-triage, facts-to-reviewed, reviewed-to-public; report median, tail and deadline-at-risk backlog |
| Source freshness | Actual per-source successful observed time versus due time; do not substitute publication/generated timestamp |
| Closure propagation | Official closure observed → status published → retained public list/detail/API changed; measure in deployed environment |

Initial completion criterion: the fixed reference set has no silent loss, the three MUNI doctoral positives have correct funded-doctoral disposition, CZU aliases find the current CZU public records, no fabricated salary facts are published, and the exact content build passes required checks. Numbers can legitimately fall when jobs close; completeness means correct coverage and disposition, not a monotonically rising card count.

Do not begin a new visual redesign, replace the whole stack, add embeddings, or expand raw-source counts as a substitute for completing Gate 1. If a case remains ambiguous, document the exact missing fact and retain it for review while finishing independent cases.

## 8. Verification executed in this audit

| Command / probe | Observed result |
|---|---|
| `py -3 work/audit5-2026-09-12/probe.py` | Eight official requests succeeded with Scrapling; MUNI four details + listing; CZU portal + public list + REST cross-check |
| `py -3 work/audit5-2026-09-12/local_probe.py` | Reproduced candidate/replay/publication differences and unsafe review rebinding in isolated copies |
| `py -3 -m pytest services/ingestion/tests tests/test_opm_generation.py -q --basetemp work/audit5-2026-09-12/pytest-confirm` | Elevated rerun: **167 passed, 1 failed** (time-dependent cooldown test). Initial sandbox run had an additional Windows replace permission failure; it did not persist. |
| `npm test` in `apps/web` | **85 passed** |
| `npm run check` in `apps/web` | **54 files, 0 errors/warnings/hints** |
| `go test ./...` in `services/catalog` and `apps/api` | Both pass (Go reported cached results) |
| `publish.py --check` | Active immutable snapshot passes |
| `publish.py --check-sources` | Selection passes: 54 institutions, 54 portals, 5019 inventory offerings/53 schools, 5 jobs, 54 coordinates, 4 reviewed offerings |
| `scripts/checkout_inventory.py --check` | Required local files exist; not a Git-tracked clean-checkout demonstration |
| `scripts/check_framework.py` | Pass after sandbox temporary-directory permission failure was rerun outside sandbox; 12 diagrams, 348 locale keys/language; no formal ISO certification claimed |
| `npm run build` | Pass, pinned v2026-09-12.4; **15,290 pages**; large chunk warning remains |
| Maintained Playwright suite | First actual 16-worker run: **38 pass/1 fail**; direct `node node_modules/@playwright/test/cli.js test --workers=2`: **39 pass** |
| Built-artifact browser probe | Default 3; all 5; `phd=required` 0; `q=CZU` 0; full CZU name 3; `q=Masaryk` 0 |
| `node --experimental-strip-types work/audit5-2026-09-12/safety-probe.mjs` | Older generation accepted after closure; first failure reported `stale:false` |
| `git remote -v` | No configured remote |
| `git diff --check` | Existing working-tree whitespace issue: `scripts/render_opm.py:289`, extra blank line at EOF; not modified by this audit |

Local Node observed as 22.17.0; CI config requests Node 24. The local pass is not proof of execution on the configured hosted runtime. No production dependency upgrade or external vulnerability audit was performed in this fifth audit.

The prior report's defects should be closed individually against this evidence. The project has made useful engineering progress, but the owner-facing outcome remains **limited reviewed catalogue, incomplete funded-doctoral coverage, and demonstrable search misses**. Gate 1 above is the shortest evidence-backed route to meaningful improvement.

## 9. Owner-requested map defect and browse-only product change

### A79 — P1: Map school information is clipped; short-window layout overlaps the school list

**Status: reproduced; production fix not applied in this audit.** The user's report is valid. The audit follows a reproduce/measure/hypothesis loop and deliberately stops at an actionable diagnosis because the requested deliverable is this audit update.

Evidence: [map_probe.py](work/audit5-2026-09-12/map_probe.py), [map-results.json](work/audit5-2026-09-12/map-results.json), [1280×500 interactive screenshot](work/audit5-2026-09-12/map-zh-CN-1280-500-stub.png), [1440×600 fallback screenshot](work/audit5-2026-09-12/map-zh-CN-1440-600-blocked.png), [390px Czech screenshot](work/audit5-2026-09-12/map-cs-390-844-stub.png). Tile-success tests use a valid local PNG; fallback deliberately blocks tiles. The flat tile color is a test fixture, not a claim about real map rendering.

**Reproduction steps:**

1. Build the active publication and open `/zh-CN/map/` at 1280×500 or 1440×600 CSS pixels. A reduced browser window or browser zoom can produce the same constrained layout.
2. Select CZU from the school list. Inspect the selected school card at the map's lower-left area and the left school-list region.
3. Observe clipping of the card's lower content/actions and overlap between the fixed-height map/list region and following explanatory text. In a tall 1440×900 window this case is less apparent.
4. Repeat with tile failure/SVG fallback. Repeat at `/cs/map/`, 390×844. The latter produced a document width of **524px**, and the selected-card close button was outside the viewport in the point-hit check.

**Ranked hypotheses and evidence:**

1. **Conflicting height constraints and clipping — supported.** Global CSS gives desktop map/list wrappers `max-height: calc(100vh - 168px)` and the map wrapper `overflow:hidden`; the component gives the inner map `min-height:min(70vh,850px)`, while the SVG viewport has another minimum. City controls, padding, fallback notices and variable text consume additional height. The selected card is absolutely anchored to that inner map, so its position can fall outside the ancestor's clipped visible box. Sticky positioning also changes geometry on scroll; checking only the card's immediate parent or its center point misses this.
2. **Intrinsic text width on mobile — reproduced separately.** Czech labels/card content can expand the grid beyond the viewport. The current CSS does not robustly constrain all grid children, long labels and card actions. A desktop screenshot alone misses this failure.
3. **Marker/card stacking — additional risk, not the established primary cause.** Selected pins use z-index 100 while the card uses 20. Markers can paint above part of the overlay. Raising the card's z-index cannot solve clipping by `overflow:hidden` ancestors or a grid that is wider than the screen.

A browser-only experiment removed the desktop map wrapper's maximum height, without editing production files. The recorded card then fit within the stage (`clippedBelow:false`), supporting the height-conflict hypothesis. This experiment is **not a complete proposed fix**: the adjacent school list and overall small-screen flow also need correction. Screenshots and point-hit measurements were captured at different scroll positions; use them for their respective visual and interaction checks, not as interchangeable pixel coordinates.

**Implementation sequence:**

1. Add a maintained failing browser case selecting a school at 1280×500, 1440×600 and 390×844; cover all locales, a long school name, both map modes and 200% text/browser zoom. Assert no page horizontal overflow and that school name, close button and official/detail actions are reachable and not clipped by any ancestor.
2. Choose one sizing model. Prefer a responsive map area with a selected-school detail region in normal document flow below/beside it on constrained viewports. If retaining an overlay on larger screens, size it against actual available map height, allow internal scrolling where necessary, and keep essential name/actions visible.
3. Remove conflicting viewport-derived min/max heights. Include toolbar and padding space in the same layout calculation; avoid fixing both parent maximum and child minimum independently. Disable sticky/fixed-height behavior when vertical space is insufficient.
4. Set grid/flex children to allow shrinking (`min-width:0` where appropriate), constrain widths to available space, wrap long localized labels/URLs, and allow action rows to wrap. Do not truncate the only school-name display or hide the close action off-screen.
5. Establish a bounded map stacking context with card/controls above markers. Keep required attribution readable and move scale/legend where they do not cover the card. Do not use an arbitrarily huge z-index as the sole remedy.
6. Ensure the school list and explanatory paragraphs stay in separate normal-flow regions. Test by scrolling both the page and the list; the map description must not paint over the school-name list.
7. Re-run the exact original reproduction and capture before/after screenshots. Retain normal wheel zoom without Ctrl, keyboard selection, resize behavior and offline fallback. A passing tile-load test does not close this issue.

### A80 — Product decision / P1: Remove shortlist and comparison; prohibit private public-user accounts

**Owner decision, not a discovered security incident:** the site is for anonymous browsing. Remove My shortlist and Compare, including their functionality and entry points. Existing save/compare data are browser-local; this audit found no reason to claim they currently consume an account database. The owner nevertheless explicitly chooses their removal, which takes precedence over old AGENTS/PRODUCT/ACCEPTANCE text.

**Required end state:** no public sign-up, login, profile, saved list, comparison module, cloud synchronization, application tracking account or user-submitted application storage. Public visitors browse/filter, read details and leave for official university applications. This does not forbid protected internal maintenance infrastructure, but it does not authorize building a new administrator account system either.

1. Update project instructions and live product documents first: AGENTS implementation flow, README, PRODUCT, UI_RULES, ACCEPTANCE, architecture/data model, relevant decisions and PROGRESS. Mark previous save/compare requirements superseded by this dated owner decision; keep old audits as history.
2. Remove `saved` and `compare` from `apps/web/src/lib/nav.ts`, desktop/mobile navigation, footer and any contextual links.
3. Inventory and remove SaveButton/CompareButton call sites, shortlist/compare views, result/detail actions, counters, toasts and shortcut text. Check programme, job, institution and error pages in all locales.
4. Remove the `/[locale]/saved` and `/[locale]/compare` feature routes. Define localized legacy-link handling (e.g. localized 404 or a simple redirect to the relevant browse list); do not leave empty broken screens or links to removed routes.
5. Remove only unused save/compare storage functions and their keys. Keep shared URL filters, language preference or other required browsing utilities. Do not clear all browser localStorage indiscriminately.
6. Remove obsolete account/sync/shortlist/compare schema/API placeholders if present and unused. Verify no authentication SDK, account endpoint, profile table or registration UI is introduced into the public bundle. The audit does not assert all such artifacts currently exist; inventory before deletion.
7. Replace obsolete acceptance tests with checks that all three locales expose only the remaining navigation and that no card/detail contains save/compare actions. Keep language switching, filtering, source viewing and official outbound application checks.
8. Update OPM model and generated diagrams: remove public Opportunity Saving/Shortlist/Comparing processes and their requirements from the current system, preserve browsing/filtering/source/application-opening processes. Update requirement tracking instead of merely changing prose.
9. Build from a clean candidate checkout and scan generated HTML/routes/assets for lingering active links and controls. Verify legacy URLs behave as specified and no registration request is made during browsing.

**Resource direction:** serve public catalogue/search/map assets statically where possible; keep crawling/translation/review offline and scheduled. Public per-user database writes are unnecessary. Evaluate whether an always-on public Go API is needed for the initial anonymous site; the background Go scheduler can remain independent. Removing save/compare alone does not remove the operational cost of keeping official data current.

**Order adjustment:** ship A79 and A80 as a bounded usability/scope tranche alongside Gate 1. Do not extend these modules or preserve them merely because the old 39-test suite includes their journeys. The recorded 39/39 result is historical baseline evidence, not the post-removal acceptance count.

## 10. GitHub crawler-strategy review and guanfu.online comparison

The owner explicitly requested these sources. They were inspected on 2026-09-12. Recommendations below distinguish documented library features from project-specific design choices. No new framework, paid service or proxy subscription was installed.

### 10.1 Relevant open-source patterns

| Primary source | Verified useful pattern | Recommendation for this repository |
|---|---|---|
| [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) | HTTP and browser fetchers, adaptive extraction and replay/development support are documented | Keep the already installed Python/Scrapling path. Prefer official public structured interfaces and HTTP; use browser fallback for genuinely dynamic sources. Verify any newer API against the locally pinned version before adopting it. Adaptive selector success must still pass entity/body checks. |
| [scrapy/scrapy](https://github.com/scrapy/scrapy), [AutoThrottle documentation](https://docs.scrapy.org/en/latest/topics/autothrottle.html) | Per-download-slot adaptive delays respect concurrency/minimum delay; fast error responses must not cause increased request rate | Borrow per-host scheduling/backpressure into the existing worker. A global fixed sleep alone poorly allocates limited resources across independent schools. Do not rewrite all adapters just to adopt a throttle pattern. |
| [Scrapy resumable jobs](https://docs.scrapy.org/en/latest/topics/jobs.html) | Persistent request/state handling supports clean pause/resume; documented limitations exist for unclean shutdown and version changes | Persist task frontier, attempt state and cursors; use the project's durable leases/idempotency for crash recovery. Do not assume a local crawler job directory alone provides distributed crash-safe scheduling. |
| [apify/crawlee](https://github.com/apify/crawlee), [request storage guide](https://crawlee.dev/js/docs/guides/request-storage) | Persistent URL queues, HTTP/browser modes, routing and resource-aware concurrency; open-source execution does not require hosted Apify | Reference its separation of queue, route handler and storage. Keep the project's Go scheduler/Python extraction boundary unless a measured adapter experiment justifies migration. No paid cloud requirement follows from reading this project. |
| [scrapy-plugins/scrapy-deltafetch](https://github.com/scrapy-plugins/scrapy-deltafetch) | Fingerprint-based suppression of requests already seen in earlier crawls, with reset/per-request controls | Useful idea for duplicate processing, **unsafe as a blanket skip-seen-URL policy for vacancies**. Old job URLs must be rechecked for closure, extension and changed salary; distinguish deduplication within a run from freshness across runs. |

These libraries improve transport and orchestration. None establishes that an MSc applicant is eligible, a PhD is funded, every faculty is covered or a translation has been reviewed. The four MUNI examples demonstrate why changing crawler framework alone would not resolve the current public-result deficit.

### A81 — P1: Implement a measured, resource-bounded crawl strategy

1. **Source frontier:** discover official list/detail/funding/admission endpoints per institution and faculty. Keep source purpose, language, pagination method, scope and confidence. Revisit both Czech and English channels where one is not a documented superset.
2. **Split task kinds:** listing enumeration, newly discovered detail, due detail status recheck, attachment extraction, parser replay and editorial review are separate queues. Assign stable source/job IDs and independent due times. A dedup key must not suppress a later scheduled recheck of the same URL.
3. **Cheap acquisition first:** official public JSON/XML/ATS endpoints linked by the school → static HTML → required PDF extraction → bounded Scrapling browser fallback. Record why a browser was needed. Do not start a browser for every page.
4. **Conditional refresh:** where sources supply reliable ETag/Last-Modified, retain validators and use conditional requests. A 304 updates observed freshness against the unchanged saved content; it does not invent new facts/review. Still periodically enumerate full listings and reconcile disappearance only when enumeration is complete.
5. **Separate hashes:** retain raw response hash for provenance, scoped vacancy-body hash for change detection, normalized fact hash and locale content hash for review. Navigation/cookie changes should trigger extraction comparison, not silently approve changes or repeatedly demand full factual review when facts are demonstrably unchanged.
6. **Bound resource usage:** begin conservatively with one browser worker and small per-host HTTP concurrency, observe latency/429/error rates, and adjust from measurements. These are proposed starting limits, not benchmarked capacity claims. Persist Retry-After cooldowns so restarting workers does not immediately hammer a throttled source.
7. **Priority without starvation:** near-deadline confirmed candidates and CZU receive earlier attention; all baseline institutions still receive the agreed 120-hour assessment cycle. Browser-heavy or failed sources retain explicit overdue status and bounded retries; one slow university must not block the entire run.
8. **Retain unresolved discovery:** log title-rejected/unsupported/attachment-failed links and audit a sample. Use broad candidate discovery followed by strict reviewed publication, rather than silently throwing away a potential PhD role before its body is read.
9. **Measure one cohort:** compare old/new strategy on the same saved/live source set: official-positive recall, number of requests, transferred bytes, wall time, peak memory, retries, unresolved links, duplicate announcements and publication conversion. Include the MUNI monetary/funding cases and an unchanged URL whose closing date changes.
10. **Accept only demonstrated improvement:** retain the new approach if it preserves/increases reference recall and bounds resource consumption with no loss of closure checks. Do not claim a tool is faster or more complete based on stars, README marketing or more raw candidates.

### 10.2 What was actually observed on guanfu.online

The [reference site](https://www.guanfu.online/) was successfully fetched with Scrapling at **18:27:29 UTC** after web-text access failed. See [reference-results.json](work/audit5-2026-09-12/reference-results.json). Its approximately 1.83 MB HTML embeds **1,521 institution records and 1,588 programme records**; **33 institution rows report positive programme counts**. These are frontend payload counts, not verified nationwide coverage.

Useful ideas: static catalogue, client-side filtering/map, and searches including institution short names and cities. These suit anonymous browsing and the CZU-alias fix. No literal `fetch(` call or GitHub link was found in this HTML; that cannot establish its crawler, update schedule or complete network behavior. [Reference site](https://www.guanfu.online/).

Do **not** copy its availability rule: `windowOpen(start,end)` returns true when an end exists but the start is absent, and compares seasonal dates. Our project requires evidenced, intake/year-specific windows. Borrow browsing organization and aliases; verify Czech opportunities on university official sources. [Reference site](https://www.guanfu.online/).

**Final owner-facing acceptance after this addendum:** funded-opportunity recall remains the highest data priority; the school-name card/list must be usable on the reported constrained map layout; shortlist/compare and private user accounts are outside the product; deployment is an anonymous browse experience fed by a measured offline maintenance pipeline.

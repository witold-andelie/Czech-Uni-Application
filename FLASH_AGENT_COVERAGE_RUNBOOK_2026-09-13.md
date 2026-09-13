# Vacancy coverage: small executable work packets

For the next implementation agent. Date: 2026-09-13. Read AGENTS.md and its required documents first. Use this runbook for **coverage execution**, not another general audit or UI redesign.

## Your objective

Make additional official university opportunities reach correct candidate records and, after evidence/translation review, the public search. Start with **one university: UHK (`msmt-vs_18000`)**. Do not start all 54 universities at once. Do not call the task complete because you wrote a table or added a test.

The owner wants both paid research jobs and funded doctoral opportunities. Keep postdocs separate: finding postdocs improves all-track research coverage but does **not** increase master's-entry or funded-PhD coverage.

## Read this result before doing anything

The supervising agent already tested the existing registered UHK source with installed Scrapling:

- Source ID: `uhk-central-selection`.
- One official listing plus nine linked detail pages: **10 HTTP requests, all 200**.
- Existing discovery returned **7 candidate records and 2 quarantined records**.
- Five candidate pages contain confirmed pay and a PhD requirement, with a **2026-10-02** deadline. They are postdoctoral opportunities, subject to final individual review.
- The biology page is currently misclassified: `track=post_master`, `isPostdoc=false`, although its body describes a postdoctoral position. Its doctorate requirement was correctly extracted. Fix this from body evidence; do not infer all PhD-required roles are postdocs.
- Two other candidates have unresolved pay/qualification facts. Do not auto-publish them.
- Full offline structuring plus the existing shard merge produces **135 stored records from 128**, adding seven UHK IDs, changing/removing **none** of the prior records.
- The pilot changed **no production candidates, review records, publication pointer or scheduler state**. There are still ten published jobs. The proposed payload is not an approved publication.

Evidence directory, relative to repository root:

`work/coverage-pilot-2026-09-13/uhk-central-selection-20260913T152549045772Z/`

Open `summary.json` first. `fetches.json` maps URLs to downloaded HTML/text, SHA-256 and actual fetch time. `discovery.json` includes parser output. Files immediately under `work/coverage-pilot-2026-09-13/` include the executable scripts and proposed merged payload.

**Completeness limitation:** “completeSourceIds” is the current adapter's result for this registered listing. It is not independently proven full UHK faculty/laboratory coverage. Check pagination and linked units before making a broader claim.

## Rules that prevent common mistakes

1. Work on the assigned source only. Keep CZU and other existing data intact.
2. Never replace the national candidate file with a single-source result. `harvest_with_registered_discovery` returns a scoped payload. The existing `merge_sharded_jobs` step is mandatory; the pilot demonstrates it.
3. Never copy the staged payload to production without reading its diff and rebasing against current data under the existing refresh lock.
4. Never execute `worker.py --once` as a substitute for a source-specific test. It can launch unrelated scheduled work.
5. `--replay-candidates --source-ids ...` reparses known stored candidates. It is **not** a discovery command and cannot acquire new URLs.
6. HTTP 200 means reachable, not open, paid, translated or complete. Preserve null/unknown facts.
7. A PhD requirement is not a doctoral-enrollment requirement. Mentoring PhD students does not mean the applicant must enroll. Postdocs must stay out of master's-entry/funded-doctoral filters.
8. Do not approve by changing a status string or copying the same English title into Czech and Chinese. Review the source and create actual translations. Do not label model review as external human certification.
9. Do not invent salary, monthly cycle, tax basis, FTE, application opening date or seat count. One missing start date does not justify manufacturing an open window.
10. Do not modify the website layout, dependencies, account features, CI or deployment in this work packet. Those have a separate beta handoff.
11. If a source fails, save the exact failure and continue another explicitly assigned source. Never translate failure into zero jobs. Respect robots/access rules and Retry-After; use normal sandbox escalation for blocked network, not proxy workarounds.
12. Do not refactor the whole crawler. Make the smallest evidence-backed correction, then rerun the fixed saved fixture.

## Packet 1 — Reproduce the pilot offline

Run from `D:\chatgpt\Czech_Uni_Apply`:

```powershell
py -3 work/coverage-pilot-2026-09-13/verify.py
py -3 work/coverage-pilot-2026-09-13/probe.py --offline work/coverage-pilot-2026-09-13/uhk-central-selection-20260913T152549045772Z
py -3 work/coverage-pilot-2026-09-13/stage_offline.py
```

These commands were actually run by the supervising agent. They write only under work and do not access the network in offline mode. `probe.py` creates a new timestamped replay folder; `stage_offline.py` overwrites its own proposed payload/diff in work. Preserve evidence you want to compare before rerunning it.

Inspect `staged-diff.json`. On the original baseline expect:

```json
{"beforeCount":128,"afterCount":135,"removedIds":[],"changedExistingIds":[],"productionHashesUnchanged":true}
```

There must be exactly seven new UHK IDs. If another agent has changed the baseline, do not force these old counts: explain the new baseline and verify unrelated records remain unchanged. If raw HTML hashes fail, stop using that capture and report the exact file.

**Deliverable:** `work/coverage-pilot-2026-09-13/packet-1.md`, at most 20 lines: command results, before/after counts, affected IDs and whether production remained unchanged. Do not yet publish.

## Packet 2 — Make a source-to-record decision table for all nine details

Use the saved text/HTML first; do not waste requests re-fetching unchanged fixtures during coding. Create `work/coverage-pilot-2026-09-13/uhk-decisions.json`. One row per official detail URL, including the two quarantined records.

Each row must contain:

```json
{
  "sourceUrl":"actual official URL",
  "candidateId":"existing generated ID, or null for quarantine",
  "sourceFile":"saved HTML filename",
  "evidenceSha256":"actual hash from fetches.json",
  "researchDutiesEvidence":"short source excerpt or section locator",
  "degreeEvidence":"short source excerpt or unknown",
  "enrollmentEvidence":"short source excerpt or not stated",
  "payEvidence":"short source excerpt or unknown",
  "deadlineEvidence":"short source excerpt or unknown",
  "applicationEvidence":"official instructions or link",
  "decision":"needs_review | excluded | expired | blocked",
  "reason":"specific evidence-based reason"
}
```

Use these checkpoints:

| Candidate ID | Topic | Required next check |
|---|---|---|
| job-18000-0b0de28455a7 | Bioorganic chemistry | Read full contract/pay/PhD/application sections; do not turn part-time OR full-time into definite 1.0 FTE |
| job-18000-53bb0a840389 | Cosmology/gravitation | Verify its own facts, not another advert's salary/deadline |
| job-18000-04276d9b86f1 | Ancient biomolecules | Correct postdoc classification using body evidence |
| job-18000-a17b80cb7ea5 | PDZ-domain biochemistry | Verify evidence and trilingual content |
| job-18000-7d6694cc18df | Analytical chemistry/metabolomics | Verify evidence and trilingual content |
| job-18000-ebb5341d8eaa | Management/marketing teaching | Determine research scope from duties and linked official documents; title alone is insufficient |
| job-18000-7df6b2fc08b7 | Health studies academic role | Determine qualifications/pay/scope; inspect official attachments if needed |

The teaching and health-study records are not automatically valid research opportunities. The pilot wrapper intentionally does not implement attachment/API crawling; if qualifications are in an attachment, fetch that official attachment through the existing supported mechanism and record the limitation. Do not mark “no requirements” from an empty HTML body.

For the chemistry sample, the source explicitly states a gross monthly base of 46,000 CZK plus bonuses and a three-year role, but final field values must be checked on each advert. Record “January 2027” with month precision; never turn it into an invented January 1 start.

**Deliverable:** all nine URLs have decisions. No claimed public growth yet. Explain separately how many are postdoc vs potential master's-entry candidates.

## Packet 3 — Correct the one demonstrated parser defect

1. Copy the exact biology HTML into `services/ingestion/tests/fixtures/uhk-biology-2026-09-13.html`. Keep URL/time/hash metadata beside it.
2. Add a focused regression test in the ingestion tests. Feed the real scoped page through discovery/structuring. Expect `minimumDegree=doctorate`, `doctorateRequired=true`, and postdoc track/flag based on the body's direct description.
3. Add a negative example: a master's-entry role that mentions working with or mentoring doctoral students must not become postdoc. A senior role requiring a PhD is also not automatically a postdoc.
4. Fix the actual classification step in `harvest_nine_hei_jobs.py`. Do not change the official title just to trigger the old classifier. Do not hard-code this URL or ID as the classification rule.
5. Run the focused tests, then replay Packet 1. Verify that the biology role changes appropriately and unrelated prior jobs remain unchanged.
6. Check salary, doctorate and enrollment fields separately. The ledger's “enrollment unspecified” label is not a reason to invent enrollment requirements.

**Deliverable:** focused test output, minimal diff, and updated proposed candidate diff. Do not expand to another school until this small correction is explained.

## Packet 4 — Refresh and merge UHK candidates safely

1. Check current repository changes and acquire the existing ingestion refresh lock before a production candidate write. Read `worker.harvest_jobs`, `refresh_shards.merge_sharded_jobs` and `file_lock.py`; copy their conventions, not a new locking system.
2. The following command is a live **read-only pilot**, not a production merge:

```powershell
py -3 work/coverage-pilot-2026-09-13/probe.py --source uhk-central-selection --max-requests 20
```

It permits same-origin HTML requests only, spaces requests, caps requests, and saves every response. It refuses other parser types. If pagination/details exceed the cap, leave the source incomplete and investigate the actual count before raising a bounded budget. Never claim exhaustion when a cap caused termination.

3. Reconcile the listing manually: pagination/next links, distinct detail count and whether the board includes closed announcements. Record discrepancies. The nine-detail count is a dated reference, not a permanent expected count for live checks.
4. Merge current source results using the existing scoped merge. **Do not copy `source-only-result.json` over `nine-hei-jobs.json`.** The former contains only seven UHK records in the pilot; doing so would remove the previous 128 records. The latter needs the merged result.
5. Re-read latest candidates under the lock before merging. Save before/after hashes and a diff. Persist actual source fetch timestamps, parser version and scope-specific complete/failed/deferred status. A one-source success must not advance all-source success or a national shard completion.
6. Preserve existing unrelated jobs/windows/evidence exactly. Preserve archive and review state where valid. Only a fully traversed matching source can drive absence-based unavailability.
7. Use an atomic write through the existing helper and release the lock. Rebuild the assessment/ledger only after the underlying real operation is recorded, not as a substitute for it.

**Acceptance:** new candidate records persisted; no unrelated losses; source receipt references real responses; publication pointer unchanged; national coverage claim unchanged except accurately recorded source execution.

## Packet 5 — Publish one complete vertical slice, then the remaining reviewed UHK jobs

First choose `job-18000-0b0de28455a7` if its current source remains suitable. If closed or substantially changed, record why and choose another of the five evidence-backed candidates. Do not publish outdated data just to match the pilot.

1. Recheck official status, application instructions and any linked mandatory applicant documents. Keep title/main action pointing to the official instructions page when applications are by email; do not submit an application.
2. Read the complete field set. Create real zh-CN/en/cs translations. Preserve the source title separately where supported. State unknowns and month-only dates honestly.
3. Use the established review contract and content/fact/evidence hashes. Inspect `publication_contract.py`, `publication_rules.py`, `publish.py` and current review examples, but do not blindly copy their prose or language mistakes.
4. Any uncertain translation or eligibility interpretation becomes a specific review request with the exact source excerpt. Continue other unblocked candidates. Never silently mark a doubtful review approved.
5. Validate before activation:

```powershell
py -3 services/ingestion/src/publish.py --check-sources
py -3 -m pytest services/ingestion/tests/test_nine_hei_jobs.py services/ingestion/tests/test_publish.py -q
```

6. Read `py -3 services/ingestion/src/publish.py --help` before selecting a publication mode. The supervisor has not supplied a fabricated `--dry-run` or version number. Follow the existing immutable publication workflow with the next unused version, never edit an old snapshot. Do not disable a failing check.
7. Build and browser-check all three locales. The new role must appear in the all-tracks/postdoc route, link to official application instructions, and remain absent from master's-entry/funded-doctoral results. A default master's filter may correctly hide it; that is not a missing-publication bug.
8. Repeat review for the other suitable UHK candidates. A snapshot may batch the reviewed records, but the first vertical slice must be demonstrably correct.

**Acceptance:** identify exact new public IDs, publication version and three-locale screenshots/search results. All previously reviewed jobs remain valid or have evidence-backed closure changes. No unreviewed record leaks through.

## Packet 6 — Expand one school at a time

After UHK is complete, proceed with UJEP, OSU and TUL, then VETUNI, SLU, VŠPJ, VŠTE and University of Defence. This order is operational, not a claim about vacancy totals. Maintain CZU refresh/review priority. Assess and connect ZČU next; then the remaining unassessed public/private/state institutions until all 54 have a documented result.

For each school repeat the same small cycle:

1. Look up its existing source registry entry and parser. The pilot `probe.py` supports only generic HTML link parsers; do not pass specialized API/PDF parsers to it and call rejection a failed school.
2. Make a read-only source-specific harness using the existing adapter, output under a new work directory, and bounded requests. Adapt the tested harness rather than rewriting ingestion. Never invoke a national production run merely to test one source.
3. Capture list/pages/details/attachments, official affiliation and scope. Separate source connection from whole-school assessment.
4. Produce the per-detail decision table and fix only demonstrated extraction defects using saved fixtures.
5. Merge safely, review eligible records, publish through the gate, and prove browser discoverability in the correct track.
6. If genuinely blocked, record URL/error/time/retry and the next concrete operation. Move to the next assigned school; do not repeatedly rewrite a parser without new evidence.

For master's-entry/funded-PhD growth specifically, inspect official doctoral funding calls, lab recruitment and grant-network pages linked to universities. A central job board alone may miss these. Use VŠB advert 61 and existing MUNI/CZU evidence as references, but do not manufacture a master's threshold where the source is silent. Do not count a degree programme, stipend scheme and linked employment advert as three jobs.

## Required end-of-packet response

Use this exact short format:

```text
Packet completed:
Source IDs:
Actual list/detail/attachment requests:
Candidate IDs added/changed:
Official roles excluded/blocked and why:
Public IDs added (or none):
Postdoc vs master's-entry vs funded-doctoral counts:
Unrelated-record preservation check:
Evidence files and test commands/results:
Remaining blocker and next concrete step:
```

Do not report only “all tests passed.” Do not call seven unreviewed pilot records seven published jobs. Do not call five postdocs five master's-entry opportunities.

## Short prompt the owner can paste into the other agent

> Read AGENTS.md and docs/FLASH_AGENT_COVERAGE_RUNBOOK_2026-09-13.md. Execute Packet 1, then Packet 2, using the already saved UHK evidence. Do not change production data or publish during these two packets. Return the exact required end-of-packet response, including the nine-detail decision table. Do not perform a broad refactor or another audit. When these outputs are correct, continue Packets 3–5 to complete UHK discovery, safe merge, review and public search verification. Do not claim nationwide coverage, do not count postdocs as master's-entry roles, and do not bypass the evidence-bound three-language publication gates. Keep the work focused on measurable new school coverage.

The next operator may give these packets separately to keep model context small. No remote agent was contacted or started by this handoff; the tested scripts and instructions are ready to use locally.

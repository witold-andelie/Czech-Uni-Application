# Incremental review without repeating approved work

The immutable public snapshot changes only through the existing review and
publication gates. These two commands prepare **local operator packets**; they
never approve a record, write to Supabase, or activate a snapshot:

```powershell
py -3 services/ingestion/src/build_incremental_job_review_queue.py --limit 50
py -3 services/ingestion/src/build_admissions_review_queue.py --school msmt-vs_41000 --limit 30
```

Read the JSON and Markdown files in `work/`. Do not commit those packets as
published data. Both queues use stable record IDs, not list position or the
number of records visible at the visitor's current time.

## Vacancies: process only the delta

The job queue intersects the current candidate-disposition ledger with the
candidate file and the stored per-locale review records. An unchanged candidate
with a matching source hash, fact hash, and reviewed zh-CN/en/cs entries stays
approved. A blocked record enters one of these operator actions:

1. `source_and_fact_re_review`: open the direct official vacancy and compare
   employer, full scope, degree, doctoral-registration condition, pay evidence,
   application target, and deadline with the stored facts. Rebind the source and
   fact hashes; re-review all three locale entries against the new version.
2. `trilingual_review`: finish the three language entries for a candidate that
   never had a complete review. Draft text is not an approval.
3. `live_evidence_recheck`: the existing translations and hashes still match,
   but the publication gate withheld the record. Check the direct official page
   and record the current live result; a 404 or timeout does not by itself mean
   the vacancy closed. Do not redo translations when the facts are unchanged.
4. `scope_or_other_review`: resolve the named blocker using the full official
   notice. An unknown salary, degree, or working language stays unknown unless
   the notice supplies evidence.

The ledger is rebuilt with a publication, not with each daily harvest, so the
queue also reads harvested jobs the ledger has not seen. Those enter as
`not_in_disposition_ledger` packets, grouped by school in the Markdown
(`--school msmt-vs_24000` prints one school). A new job already closed,
expired or past its announced deadline is skipped. A new job with no
research/technical track, or that the source adapter marked excluded, goes to
a separate scope screen instead of a review packet; it is listed, not
dropped, because the full notice may still prove technical duties (A38).
`--jobs <file>` builds the queue from a refresh artifact's candidate file
before it is committed.

The queue carries the ledger's `candidateGenerationId` and
`sourceRunSetDigest`. Before acting on packets, compare these to the current
ledger; regenerate if either changes. Missing candidate IDs and non-HTTPS
targets go to diagnostics, never silently disappear or become approved. The
operator then updates the existing source review files and runs the existing
source, contract, and publication checks. Only the existing `publish.yml` path
may activate an immutable snapshot; a green daily refresh is not publication.

## Admissions: start with sourced matches

The admissions queue exact-matches the register institution ID, normalized
title, degree, and teaching language to one register row and requires a
school-owned page link. It groups the English and Czech portal candidates for
that same row so one review can handle corroborating sources. A source older
than 48 hours is `refresh_before_review`; it is not a fresh admission claim.
The current CZU candidate exports are older than that limit. Refresh and
reconcile the live official page before approving any queued record. Previously
approved rows with the same candidate IDs and evidence hashes are carried
forward; a changed hash, missing old candidate, or newly corroborating source
is surfaced explicitly. Ambiguous matches, missing hashes, and bad URLs stay
in diagnostics. A school-owned programme page is an identity link; it is not
alone proof of current application dates, fees, or language requirements.

Review each selected packet against the current official source, retain its
exact URL and hash, resolve conflicting statements, and review every published
fact in zh-CN, en, and cs. Use the existing admission builder and publisher
only after all three locale reviews bind to the same source/fact version. The
other 3,320 linked register rows without a structured candidate in the two
loaded CZU files are an *input-scope gap*, not a claim that those programmes
have no admissions information.

## Supabase access boundary

The browser reads an immutable Cloudflare snapshot; ingestion uses the
`service_role` key server-side only. The public `schema_migrations` table has
RLS enabled and no `PUBLIC`, `anon`, or `authenticated` grants. The public
programme Data API views also deny those roles; only the server-side role and
database owner retain access. Migration
`20260929210000_harden_public_api.sql` records this repair. Never place the
service key in browser code or public CI output. After any new public view or
table migration, check role grants and RLS before treating a green workflow as
evidence of safe API exposure. The Sep 27 alert screenshot predates this
repair; the dashboard adviser may need a fresh scan before its warning clears.

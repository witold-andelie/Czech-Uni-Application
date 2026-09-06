# services/catalog

Go domain package compiled into `apps/api`. It is not a separate microservice.

Rules implemented here:

- Teaching-language filter: English/Czech single tracks; joint-required only when explicitly included.
- Application windows evaluated with ISO dates and Europe/Prague calendar dates. A missing start date does not mean open.
- Round 1 closing does not take down an offering that still has an open later round.
- Whole-job closure beats a future round.
- CSCSE lookup status is never inferred from public/private/state ownership.

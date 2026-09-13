# UI fixtures

These records are **interface fixtures**, not a verified published catalogue.

Rules applied here:

- Every record has `dataClass: "ui_fixture"`.
- CSCSE lookup values are labelled as fixture demonstrations. They are not the result of a live query of the official CSCSE list.
- Application dates exist only to exercise round logic. They are not real intake windows.
- Unknown tuition is stored as unpublished, never as zero.
- Closed jobs have `visibility: "archived"` so public lists omit them.

Published catalogue files belong in `data/published/` and remain empty until verification.

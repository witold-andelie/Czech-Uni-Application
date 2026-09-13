# Publication contract corpus

This corpus is the shared acceptance set for A52 and the minimum A53 review binding.

Both engines must independently implement the same rules:

- Python: `services/ingestion/src/publication_contract.py`
- Node: `apps/web/scripts/published-contract.mjs`

Cases in `cases.json` name **rule identifiers**, not implementation-specific sentence text. A case passes when:

- `expect` is `accept` and both engines report no errors, or
- `expect` is `reject` and both engines emit every listed `rules` identifier.

Mutations are applied to an isolated copy of the active immutable snapshot. Checksums are regenerated so the probe tests business acceptance, not byte-tampering detection. These copies are never publication candidates.

Rule identifiers are defined in `services/ingestion/src/publication_rules.py`.

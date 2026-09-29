# Incremental admissions review

The 5,019 MŠMT register rows are the browse inventory; a school-owned link is
not an admissions review. An official admissions extract is added only when its
programme identity, degree, teaching language, duration, dates, fees, source
evidence, and three locale titles have been checked. Existing approved records
remain approved when their bound source and normalized facts have not changed.
New or changed records enter a later batch; the builder must retain prior IDs
and their review timestamps. Job review follows the same incremental rule but
is a separate queue and is unchanged by these admissions batches.

## 2026-09-29 — CZU PEF English bachelor programmes (2 new records)

| Inventory ID | Official programme | Teaching language / degree | Application window | Annual tuition labels on source |
| --- | --- | --- | --- | --- |
| `inv-ca4cebefff1b` | [Business Administration](https://study.czu.cz/programmes/business-administration/) | English / bachelor, 3 years | 2026-09-15 to 2027-03-31 | general €2,600; EU students €500 |
| `inv-1810509648f0` | [Economics and Management](https://study.czu.cz/programmes/economics-and-management/) | English / bachelor, 3 years | 2026-09-15 to 2027-03-31 | general €2,000; EU students €500 |

The official [Czech-portal Business Administration](https://studuj.czu.cz/programmes/business-administration/)
and [Economics and Management](https://studuj.czu.cz/programmes/economics-and-management/)
pages independently show the same degree, teaching language, duration, window,
and separate EU tuition rate. The [CZU admissions page](https://study.czu.cz/admission/)
states the general CZK 850 application fee; this is not tuition. The programme
pages link to the general UIS application system, so the records do not claim a
verified programme-specific application URL. The English pages note that the
EUR tuition figures vary with the CZK exchange rate at payment.

The official programme and admissions pages were checked on 2026-09-29 against
the stored CZU candidate extracts. The source hashes in
`data/sources/admissions/czu-english-programmes.json` and
`czu-czech-programmes.json` identify the 2026-09-11 harvested bodies; this
batch does **not** claim a fresh byte-for-byte HTML hash. The checked fields
still agree with the live pages. Chinese titles are reviewed translations;
the Czech portal itself uses the English programme names, so the Czech title
slots preserve those official names. The descriptive notes in all three
locales remain short and do not reproduce the schools' programme descriptions.

The original four approved CZU records and their 2026-09-12 reviews are
retained. This batch moves the reviewed admissions extract from 4 to 6; it
does not change the register inventory, linked-page count, job approval count,
or the remaining admissions review queue.

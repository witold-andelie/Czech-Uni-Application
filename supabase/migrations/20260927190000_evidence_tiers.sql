-- Evidence tiers and three hashes. Legacy sha256 stays as the extracted-text
-- digest so existing review bindings are not rewritten.

ALTER TABLE ingest.raw_document
  ADD COLUMN IF NOT EXISTS raw_sha256 text,
  ADD COLUMN IF NOT EXISTS text_sha256 text,
  ADD COLUMN IF NOT EXISTS evidence_tier text,
  ADD COLUMN IF NOT EXISTS byte_size integer,
  ADD COLUMN IF NOT EXISTS compressed boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS raw_document_raw_sha256
  ON ingest.raw_document (raw_sha256)
  WHERE raw_sha256 IS NOT NULL;

ALTER TABLE catalog.research_job_version
  ADD COLUMN IF NOT EXISTS evidence_raw_sha256 text;

ALTER TABLE catalog.programme_version
  ADD COLUMN IF NOT EXISTS evidence_raw_sha256 text;

CREATE OR REPLACE VIEW public.ingest_raw_document AS SELECT * FROM ingest.raw_document;
CREATE OR REPLACE VIEW public.catalog_research_job_version AS SELECT * FROM catalog.research_job_version;
CREATE OR REPLACE VIEW public.catalog_programme_version AS SELECT * FROM catalog.programme_version;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingest_raw_document TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_research_job_version TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_programme_version TO service_role, postgres;

NOTIFY pgrst, 'reload schema';

-- HTTPS Data API access for GitHub Actions. No dedicated IPv4 / direct Postgres.
-- Anon and authenticated still have no rights. service_role only.

GRANT USAGE ON SCHEMA ingest, catalog, review, publish, ops TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA ingest, catalog, review, publish, ops TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA ingest, catalog, review, publish, ops TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA ingest GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog GRANT ALL ON TABLES TO service_role;

CREATE OR REPLACE VIEW public.ingest_source AS SELECT * FROM ingest.source;
CREATE OR REPLACE VIEW public.ingest_source_run AS SELECT * FROM ingest.source_run;
CREATE OR REPLACE VIEW public.ingest_raw_document AS SELECT * FROM ingest.raw_document;
CREATE OR REPLACE VIEW public.ingest_listing_observation AS SELECT * FROM ingest.listing_observation;
CREATE OR REPLACE VIEW public.catalog_research_job AS SELECT * FROM catalog.research_job;
CREATE OR REPLACE VIEW public.catalog_research_job_version AS SELECT * FROM catalog.research_job_version;

REVOKE ALL ON public.ingest_source FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.ingest_source_run FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.ingest_raw_document FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.ingest_listing_observation FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.catalog_research_job FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.catalog_research_job_version FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingest_source TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingest_source_run TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingest_raw_document TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingest_listing_observation TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_research_job TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_research_job_version TO service_role, postgres;

NOTIFY pgrst, 'reload schema';

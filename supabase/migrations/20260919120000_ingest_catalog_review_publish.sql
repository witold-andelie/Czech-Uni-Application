-- Operational store for collection, review and release.
-- The public site does not read these schemas.

CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS review;
CREATE SCHEMA IF NOT EXISTS publish;
CREATE SCHEMA IF NOT EXISTS ops;

REVOKE ALL ON SCHEMA ingest, catalog, review, publish, ops FROM PUBLIC;
REVOKE ALL ON SCHEMA ingest, catalog, review, publish, ops FROM anon, authenticated;

CREATE TABLE ingest.source (
  id text PRIMARY KEY,
  institution_id text,
  entity_kind text NOT NULL CHECK (entity_kind IN ('research_job', 'programme', 'admission_window', 'tuition', 'institution')),
  source_kind text NOT NULL,
  adapter_key text NOT NULL,
  entry_url text NOT NULL,
  official_host text NOT NULL,
  allowed_hosts text[] NOT NULL,
  coverage_scope text NOT NULL,
  coverage_claim text NOT NULL DEFAULT 'not_asserted',
  cadence_seconds integer NOT NULL CHECK (cadence_seconds > 0),
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ingest.source_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text NOT NULL REFERENCES ingest.source(id),
  scheduled_for timestamptz NOT NULL,
  started_at timestamptz,
  finished_at timestamptz,
  status text NOT NULL CHECK (status IN ('queued', 'running', 'partial', 'succeeded', 'failed', 'deferred')),
  parser_version text,
  expected_count integer,
  listed_count integer,
  parsed_count integer,
  listing_complete boolean NOT NULL DEFAULT false,
  content_set_hash text,
  error_class text,
  error_message text,
  retry_at timestamptz,
  lease_owner text,
  lease_token text,
  lease_until timestamptz,
  heartbeat_at timestamptz,
  github_run_id text,
  git_commit text,
  artifact_digest text,
  UNIQUE (source_id, scheduled_for)
);

CREATE TABLE ingest.raw_document (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text NOT NULL REFERENCES ingest.source(id),
  run_id uuid REFERENCES ingest.source_run(id),
  requested_url text NOT NULL,
  final_url text,
  http_status integer,
  content_type text,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  source_language text,
  sha256 text NOT NULL,
  storage_path text,
  parse_status text,
  parser_version text
);

CREATE UNIQUE INDEX raw_document_sha256 ON ingest.raw_document (sha256);

CREATE TABLE ingest.listing_observation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES ingest.source_run(id),
  remote_key text NOT NULL,
  detail_url text NOT NULL,
  title text,
  listing_position integer,
  listing_page integer,
  present boolean NOT NULL DEFAULT true
);

CREATE TABLE catalog.research_job (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id text NOT NULL UNIQUE,
  employer_id text,
  remote_id text,
  official_detail_url text NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  last_complete_run_at timestamptz,
  preferred_version_id uuid,
  lifecycle text NOT NULL DEFAULT 'discovered',
  visibility text NOT NULL DEFAULT 'private',
  consecutive_complete_run_absence integer NOT NULL DEFAULT 0
);

CREATE TABLE catalog.research_job_version (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES catalog.research_job(id),
  source_run_id uuid REFERENCES ingest.source_run(id),
  parser_version text,
  fact_hash text NOT NULL,
  source_title text,
  official_detail_url text NOT NULL,
  application_url text,
  application_method text,
  official_referrer_url text,
  url_verified_at timestamptz,
  url_directness text,
  scope_classification text,
  paid_status text,
  facts jsonb NOT NULL DEFAULT '{}'::jsonb,
  review_state text NOT NULL DEFAULT 'required',
  UNIQUE (job_id, fact_hash)
);

CREATE TABLE review.translation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type text NOT NULL,
  version_id uuid NOT NULL,
  locale text NOT NULL CHECK (locale IN ('zh-CN', 'en', 'cs')),
  content jsonb NOT NULL,
  fact_hash text NOT NULL,
  source_hash text NOT NULL,
  content_hash text NOT NULL,
  status text NOT NULL CHECK (status IN ('missing', 'draft', 'reviewed', 'stale')),
  reviewer text,
  reviewed_at timestamptz,
  UNIQUE (entity_type, version_id, locale)
);

CREATE TABLE review.decision (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type text NOT NULL,
  version_id uuid NOT NULL,
  scope text NOT NULL DEFAULT 'record',
  decision text NOT NULL CHECK (decision IN ('approve', 'reject', 'request_change')),
  reason text,
  reviewer text NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE publish.release (
  id text PRIMARY KEY,
  generation_id text NOT NULL,
  manifest_hash text NOT NULL,
  git_commit text,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  status text NOT NULL CHECK (status IN ('staging', 'published', 'superseded')),
  active boolean NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX one_active_release ON publish.release (active) WHERE active;

CREATE TABLE publish.release_item (
  release_id text NOT NULL REFERENCES publish.release(id),
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  version_id uuid NOT NULL,
  PRIMARY KEY (release_id, entity_type, entity_id)
);

CREATE TABLE ops.lease (
  source_id text PRIMARY KEY REFERENCES ingest.source(id),
  owner text NOT NULL,
  token text NOT NULL,
  until timestamptz NOT NULL,
  heartbeat_at timestamptz NOT NULL DEFAULT now()
);

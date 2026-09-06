-- Logical PostgreSQL schema for the Czech study platform.
-- Facts live once; translations hang off entity_id + locale + source_version.

CREATE TABLE institutions (
  id TEXT PRIMARY KEY,
  official_name TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT 'CZ',
  ownership TEXT NOT NULL CHECK (ownership IN ('public', 'private', 'state', 'unknown')),
  ownership_evidence_id TEXT,
  legal_type TEXT NOT NULL CHECK (legal_type IN ('university', 'non_university', 'research_institute', 'unknown')),
  orientation TEXT NOT NULL CHECK (orientation IN ('research', 'applied', 'unknown')),
  official_url TEXT NOT NULL,
  parent_institution_id TEXT REFERENCES institutions(id),
  data_class TEXT NOT NULL DEFAULT 'draft'
);

CREATE TABLE institution_i18n (
  institution_id TEXT NOT NULL REFERENCES institutions(id),
  locale TEXT NOT NULL CHECK (locale IN ('zh-CN', 'en', 'cs')),
  display_name TEXT NOT NULL,
  city TEXT NOT NULL,
  PRIMARY KEY (institution_id, locale)
);

CREATE TABLE cscse_references (
  institution_id TEXT PRIMARY KEY REFERENCES institutions(id),
  lookup_status TEXT NOT NULL CHECK (lookup_status IN ('listed', 'not_found', 'unverified')),
  official_matched_name TEXT,
  matched_awarding_institution_id TEXT REFERENCES institutions(id),
  lookup_url TEXT NOT NULL,
  checked_at TIMESTAMPTZ,
  source_version TEXT,
  evidence_id TEXT,
  reviewer TEXT,
  match_confidence TEXT CHECK (match_confidence IN ('exact', 'needs_review') OR match_confidence IS NULL)
);

CREATE TABLE cscse_notices (
  id TEXT PRIMARY KEY,
  institution_id TEXT NOT NULL REFERENCES institutions(id),
  scope TEXT,
  effective_from DATE,
  effective_to DATE,
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE cscse_notice_i18n (
  notice_id TEXT NOT NULL REFERENCES cscse_notices(id),
  locale TEXT NOT NULL CHECK (locale IN ('zh-CN', 'en', 'cs')),
  body TEXT NOT NULL,
  PRIMARY KEY (notice_id, locale)
);

CREATE TABLE programmes (
  id TEXT PRIMARY KEY,
  institution_id TEXT NOT NULL REFERENCES institutions(id),
  official_code TEXT,
  degree TEXT NOT NULL,
  orientation TEXT NOT NULL
);

CREATE TABLE offerings (
  id TEXT PRIMARY KEY,
  programme_id TEXT NOT NULL REFERENCES programmes(id),
  institution_id TEXT NOT NULL REFERENCES institutions(id),
  academic_year TEXT NOT NULL CHECK (academic_year ~ '^[0-9]{4}/[0-9]{4}$'),
  language_mode TEXT NOT NULL CHECK (language_mode IN ('single', 'joint_required')),
  teaching_languages TEXT[] NOT NULL,
  language_evidence_url TEXT NOT NULL,
  tuition_amount NUMERIC,
  tuition_currency TEXT,
  tuition_cycle TEXT,
  tuition_published BOOLEAN NOT NULL DEFAULT FALSE,
  application_url TEXT,
  lifecycle_override TEXT CHECK (lifecycle_override IN ('open', 'closed', 'upcoming', 'unknown') OR lifecycle_override IS NULL),
  source_hash TEXT,
  verified BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (programme_id, academic_year, language_mode, teaching_languages)
);

CREATE TABLE offering_i18n (
  offering_id TEXT NOT NULL REFERENCES offerings(id),
  locale TEXT NOT NULL CHECK (locale IN ('zh-CN', 'en', 'cs')),
  title TEXT NOT NULL,
  field TEXT NOT NULL,
  review_status TEXT NOT NULL CHECK (review_status IN ('missing', 'draft', 'reviewed', 'stale')),
  translated_from_hash TEXT,
  PRIMARY KEY (offering_id, locale)
);

CREATE TABLE additional_language_requirements (
  id TEXT PRIMARY KEY,
  offering_id TEXT NOT NULL REFERENCES offerings(id),
  language TEXT NOT NULL,
  context TEXT NOT NULL CHECK (context IN ('admission', 'placement', 'clinical', 'other')),
  requirement TEXT NOT NULL CHECK (requirement IN ('required', 'optional', 'unknown')),
  evidence_url TEXT NOT NULL
);

CREATE TABLE application_windows (
  id TEXT PRIMARY KEY,
  owner_type TEXT NOT NULL CHECK (owner_type IN ('offering', 'research_job')),
  owner_id TEXT NOT NULL,
  academic_year TEXT,
  round_number INTEGER CHECK (round_number IS NULL OR round_number >= 1),
  round_label_original TEXT,
  round_type TEXT NOT NULL CHECK (round_type IN ('regular', 'supplementary', 'rolling', 'unspecified')),
  opens_at TIMESTAMPTZ,
  closes_at TIMESTAMPTZ,
  timezone TEXT,
  date_precision TEXT NOT NULL CHECK (date_precision IN ('datetime', 'date', 'month', 'unknown')),
  status TEXT NOT NULL CHECK (status IN ('upcoming', 'open', 'closed', 'conditional', 'unknown')),
  conditional_on_vacancies BOOLEAN NOT NULL DEFAULT FALSE,
  application_url TEXT,
  source_evidence_id TEXT NOT NULL
);

CREATE TABLE research_jobs (
  id TEXT PRIMARY KEY,
  employer_id TEXT NOT NULL REFERENCES institutions(id),
  minimum_degree TEXT NOT NULL,
  doctorate_required BOOLEAN,
  doctoral_enrollment TEXT NOT NULL CHECK (doctoral_enrollment IN ('required', 'optional', 'not_required', 'unspecified')),
  paid_status TEXT NOT NULL CHECK (paid_status IN ('confirmed', 'unconfirmed', 'unpaid')),
  salary_amount NUMERIC,
  salary_currency TEXT,
  salary_cycle TEXT,
  salary_tax TEXT,
  basis_fte NUMERIC,
  working_languages TEXT[] NOT NULL,
  source_url TEXT NOT NULL,
  application_url TEXT,
  application_method TEXT NOT NULL CHECK (application_method IN ('web_form', 'official_instructions')),
  lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('open', 'closed', 'expired', 'unavailable', 'unknown')),
  visibility TEXT NOT NULL CHECK (visibility IN ('public', 'archived')),
  is_postdoc BOOLEAN NOT NULL DEFAULT FALSE,
  whole_opportunity_closed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE research_job_i18n (
  job_id TEXT NOT NULL REFERENCES research_jobs(id),
  locale TEXT NOT NULL CHECK (locale IN ('zh-CN', 'en', 'cs')),
  title TEXT NOT NULL,
  review_status TEXT NOT NULL,
  PRIMARY KEY (job_id, locale)
);

CREATE TABLE source_evidence (
  id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  extracted_at TIMESTAMPTZ,
  page_updated_at TIMESTAMPTZ,
  content_hash TEXT,
  source_language TEXT
);

CREATE TABLE crawl_runs (
  id TEXT PRIMARY KEY,
  scheduled_at TIMESTAMPTZ NOT NULL,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  scope_version TEXT,
  expected_sources INTEGER,
  successful_sources INTEGER,
  failed_sources INTEGER,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'partial', 'succeeded', 'failed')),
  retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE source_registry (
  id TEXT PRIMARY KEY,
  institution_id TEXT REFERENCES institutions(id),
  source_type TEXT NOT NULL,
  source_language TEXT,
  official_url TEXT NOT NULL,
  adapter TEXT,
  last_attempt_at TIMESTAMPTZ,
  last_success_at TIMESTAMPTZ,
  next_due_at TIMESTAMPTZ,
  failure_reason TEXT,
  coverage_status TEXT
);

CREATE TABLE publish_snapshots (
  id TEXT PRIMARY KEY,
  published_at TIMESTAMPTZ NOT NULL,
  fact_version TEXT NOT NULL,
  translation_version TEXT NOT NULL,
  current BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX offerings_language_idx ON offerings USING GIN (teaching_languages);
CREATE INDEX windows_owner_idx ON application_windows (owner_type, owner_id);
CREATE INDEX jobs_visibility_idx ON research_jobs (visibility, lifecycle_status);

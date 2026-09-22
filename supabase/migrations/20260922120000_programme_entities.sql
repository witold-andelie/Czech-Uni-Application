-- Stable programme/offering entities and immutable versions (§5.5).
-- The stable programme key is institution + official programme code; the
-- offering key adds academic year, campus/mode and teaching-language track.
-- Catalogue presence never implies applications are open.

CREATE TABLE catalog.programme (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id text NOT NULL UNIQUE,
  institution_id text,
  official_code text,
  official_detail_url text NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  preferred_version_id uuid,
  lifecycle text NOT NULL DEFAULT 'discovered',
  visibility text NOT NULL DEFAULT 'private'
);

CREATE TABLE catalog.programme_version (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  programme_id uuid NOT NULL REFERENCES catalog.programme(id),
  source_run_id uuid REFERENCES ingest.source_run(id),
  parser_version text,
  fact_hash text NOT NULL,
  source_title text,
  official_detail_url text NOT NULL,
  degree text,
  facts jsonb NOT NULL DEFAULT '{}'::jsonb,
  review_state text NOT NULL DEFAULT 'required',
  UNIQUE (programme_id, fact_hash)
);

ALTER TABLE catalog.programme
  ADD CONSTRAINT programme_preferred_version_fk
  FOREIGN KEY (preferred_version_id) REFERENCES catalog.programme_version(id);

CREATE TABLE catalog.offering (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id text NOT NULL UNIQUE,
  programme_id uuid NOT NULL REFERENCES catalog.programme(id),
  institution_id text,
  academic_year text NOT NULL CHECK (academic_year ~ '^[0-9]{4}/[0-9]{4}$'),
  campus_mode text NOT NULL,
  teaching_languages text[] NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  preferred_version_id uuid,
  visibility text NOT NULL DEFAULT 'private'
);

CREATE TABLE catalog.offering_version (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  offering_id uuid NOT NULL REFERENCES catalog.offering(id),
  source_run_id uuid REFERENCES ingest.source_run(id),
  parser_version text,
  fact_hash text NOT NULL,
  official_detail_url text,
  language_evidence_url text,
  application_url text,
  lifecycle text NOT NULL CHECK (lifecycle IN ('open', 'closed', 'upcoming', 'unknown')),
  facts jsonb NOT NULL DEFAULT '{}'::jsonb,
  review_state text NOT NULL DEFAULT 'required',
  UNIQUE (offering_id, fact_hash)
);

ALTER TABLE catalog.offering
  ADD CONSTRAINT offering_preferred_version_fk
  FOREIGN KEY (preferred_version_id) REFERENCES catalog.offering_version(id);

CREATE TABLE catalog.admission_window (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_type text NOT NULL CHECK (owner_type IN ('offering', 'research_job')),
  owner_id text NOT NULL,
  offering_version_id uuid REFERENCES catalog.offering_version(id),
  academic_year text CHECK (academic_year IS NULL OR academic_year ~ '^[0-9]{4}/[0-9]{4}$'),
  round_number integer CHECK (round_number IS NULL OR round_number >= 1),
  round_label_original text,
  round_type text NOT NULL CHECK (round_type IN ('regular', 'supplementary', 'rolling', 'unspecified')),
  opens_at timestamptz,
  closes_at timestamptz,
  timezone text,
  date_precision text NOT NULL CHECK (date_precision IN ('datetime', 'date', 'month', 'unknown')),
  status text NOT NULL CHECK (status IN ('upcoming', 'open', 'closed', 'conditional', 'unknown')),
  application_url text,
  source_run_id uuid REFERENCES ingest.source_run(id),
  UNIQUE (owner_type, owner_id, round_number, opens_at)
);

CREATE TABLE catalog.tuition (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  offering_id uuid NOT NULL REFERENCES catalog.offering(id),
  amount numeric,
  currency text NOT NULL DEFAULT 'CZK',
  cycle text NOT NULL CHECK (cycle IN ('per_year', 'per_semester', 'per_month', 'once', 'unknown')),
  published boolean NOT NULL DEFAULT false,
  evidence_url text,
  source_run_id uuid REFERENCES ingest.source_run(id)
);

CREATE TABLE catalog.requirement (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  offering_id uuid NOT NULL REFERENCES catalog.offering(id),
  kind text NOT NULL CHECK (kind IN ('degree', 'language', 'tests', 'documentation', 'other')),
  requirement text NOT NULL,
  mandatory boolean,
  evidence_url text,
  source_run_id uuid REFERENCES ingest.source_run(id)
);

CREATE INDEX offering_programme_idx ON catalog.offering (programme_id);
CREATE INDEX offering_language_idx ON catalog.offering USING GIN (teaching_languages);
CREATE INDEX admission_window_owner_idx ON catalog.admission_window (owner_type, owner_id);
CREATE INDEX tuition_offering_idx ON catalog.tuition (offering_id);

CREATE OR REPLACE VIEW public.catalog_programme AS SELECT * FROM catalog.programme;
CREATE OR REPLACE VIEW public.catalog_programme_version AS SELECT * FROM catalog.programme_version;
CREATE OR REPLACE VIEW public.catalog_offering AS SELECT * FROM catalog.offering;
CREATE OR REPLACE VIEW public.catalog_offering_version AS SELECT * FROM catalog.offering_version;
CREATE OR REPLACE VIEW public.catalog_admission_window AS SELECT * FROM catalog.admission_window;
CREATE OR REPLACE VIEW public.catalog_tuition AS SELECT * FROM catalog.tuition;
CREATE OR REPLACE VIEW public.catalog_requirement AS SELECT * FROM catalog.requirement;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_programme TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_programme_version TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_offering TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_offering_version TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_admission_window TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_tuition TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.catalog_requirement TO service_role, postgres;

NOTIFY pgrst, 'reload schema';
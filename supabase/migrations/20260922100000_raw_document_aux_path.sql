-- Store the extracted-text sibling object path for PDF/Aux evidence uploads.
-- The primary evidence object is the official body (HTML/JSON) or the original
-- PDF bytes; aux_object_path points at the extracted text when it is kept as a
-- separate object.

ALTER TABLE ingest.raw_document ADD COLUMN IF NOT EXISTS aux_object_path text;

CREATE OR REPLACE VIEW public.ingest_raw_document AS SELECT * FROM ingest.raw_document;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingest_raw_document TO service_role, postgres;

NOTIFY pgrst, 'reload schema';
-- Ingestion uses these public Data API views only with the server-side service role.
-- Supabase's default public grants made the programme views readable to anon/authenticated.
ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.schema_migrations FROM PUBLIC, anon, authenticated;

REVOKE ALL ON TABLE public.catalog_programme FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.catalog_programme_version FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.catalog_offering FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.catalog_offering_version FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.catalog_admission_window FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.catalog_tuition FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.catalog_requirement FROM PUBLIC, anon, authenticated;

NOTIFY pgrst, 'reload schema';

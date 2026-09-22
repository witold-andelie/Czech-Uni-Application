-- Lease claim / heartbeat / fencing-token release for source runs.
-- One running task that holds a lease is the only writer for a run row; release
-- or extension requires the exact fencing token returned by the claim.

CREATE OR REPLACE FUNCTION public.rpc_claim_run(p_run uuid, p_owner text, p_lease_seconds integer DEFAULT 900)
RETURNS jsonb
LANGUAGE sql
VOLATILE
AS $$
WITH updated AS (
  UPDATE ingest.source_run
  SET lease_owner = p_owner,
      lease_token = gen_random_uuid()::text,
      lease_until = now() + make_interval(secs => p_lease_seconds),
      heartbeat_at = now()
  WHERE id = p_run
    AND (lease_owner IS NULL OR lease_until IS NULL OR lease_until < now())
  RETURNING lease_token AS token, lease_until AS lease_until
)
SELECT to_jsonb(d) FROM updated d;
$$;

CREATE OR REPLACE FUNCTION public.rpc_heartbeat_run(p_run uuid, p_token text, p_lease_seconds integer DEFAULT 900)
RETURNS jsonb
LANGUAGE sql
VOLATILE
AS $$
WITH updated AS (
  UPDATE ingest.source_run
  SET lease_until = now() + make_interval(secs => p_lease_seconds),
      heartbeat_at = now()
  WHERE id = p_run AND lease_token = p_token
  RETURNING true AS ok
)
SELECT to_jsonb(d) FROM updated d;
$$;

CREATE OR REPLACE FUNCTION public.rpc_release_run(p_run uuid, p_token text)
RETURNS jsonb
LANGUAGE sql
VOLATILE
AS $$
WITH updated AS (
  UPDATE ingest.source_run
  SET lease_owner = NULL,
      lease_token = NULL,
      lease_until = NULL
  WHERE id = p_run AND lease_token = p_token
  RETURNING true AS ok
)
SELECT to_jsonb(d) FROM updated d;
$$;

REVOKE ALL ON FUNCTION public.rpc_claim_run(uuid, text, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.rpc_heartbeat_run(uuid, text, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.rpc_release_run(uuid, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.rpc_claim_run(uuid, text, integer) TO service_role, postgres;
GRANT EXECUTE ON FUNCTION public.rpc_heartbeat_run(uuid, text, integer) TO service_role, postgres;
GRANT EXECUTE ON FUNCTION public.rpc_release_run(uuid, text) TO service_role, postgres;

NOTIFY pgrst, 'reload schema';
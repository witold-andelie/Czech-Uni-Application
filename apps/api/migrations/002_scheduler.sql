-- Planned durable scheduler tables. Not applied; no hosted PostgreSQL exists.
-- Go should schedule existing Python commands, not reimplement parsers.

CREATE TABLE IF NOT EXISTS ingestion_task (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    shard_index INTEGER,
    interval_seconds INTEGER NOT NULL,
    expected_source_set TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_run (
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES ingestion_task (task_id),
    lease_owner TEXT,
    lease_token TEXT,
    lease_until TIMESTAMPTZ,
    attempt INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    retry_at TIMESTAMPTZ,
    result_kind TEXT,
    artifact_digest TEXT,
    candidate_generation_id TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS source_state (
    source_id TEXT PRIMARY KEY,
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    retry_at TIMESTAMPTZ,
    last_error TEXT,
    sla_hours INTEGER NOT NULL DEFAULT 120
);

CREATE TABLE IF NOT EXISTS candidate_generation (
    generation_id TEXT PRIMARY KEY,
    pinned_at TIMESTAMPTZ NOT NULL,
    checksums JSONB NOT NULL,
    lock_order TEXT[] NOT NULL,
    complete BOOLEAN NOT NULL DEFAULT FALSE
);

-- ============================================================
-- Distributed Job Scheduler — Initial Schema
-- PostgreSQL 15+
-- ============================================================

-- ---- Enums ----
CREATE TYPE job_status AS ENUM (
    'queued', 'scheduled', 'claimed', 'running', 'completed', 'failed', 'cancelled'
);

CREATE TYPE job_type AS ENUM (
    'immediate', 'delayed', 'scheduled', 'cron', 'batch'
);

CREATE TYPE retry_strategy AS ENUM (
    'fixed', 'linear', 'exponential'
);

CREATE TYPE worker_status AS ENUM (
    'active', 'idle', 'dead'
);

-- ---- 1. users ----
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---- 2. organizations ----
CREATE TABLE IF NOT EXISTS organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    owner_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---- 3. projects ----
CREATE TABLE IF NOT EXISTS projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---- 4. retry_policies ----
CREATE TABLE IF NOT EXISTS retry_policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy        retry_strategy NOT NULL DEFAULT 'exponential',
    max_attempts    INT NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    base_delay_ms   INT NOT NULL DEFAULT 1000 CHECK (base_delay_ms >= 0),
    max_delay_ms    INT NOT NULL DEFAULT 60000 CHECK (max_delay_ms >= 0)
);

-- ---- 5. queues ----
CREATE TABLE IF NOT EXISTS queues (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    priority            INT NOT NULL DEFAULT 0,
    concurrency_limit   INT NOT NULL DEFAULT 10 CHECK (concurrency_limit >= 1),
    retry_policy_id     UUID REFERENCES retry_policies(id) ON DELETE SET NULL,
    is_paused           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, name)
);

-- ---- 6. jobs ----
CREATE TABLE IF NOT EXISTS jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id        UUID NOT NULL REFERENCES queues(id) ON DELETE CASCADE,
    job_type        job_type NOT NULL DEFAULT 'immediate',
    status          job_status NOT NULL DEFAULT 'queued',
    payload         JSONB NOT NULL DEFAULT '{}',
    priority        INT NOT NULL DEFAULT 0,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- idempotency
    idempotency_key TEXT,
    -- tracking
    attempt_count   INT NOT NULL DEFAULT 0,
    max_attempts    INT NOT NULL DEFAULT 3,
    claimed_by      UUID,          -- worker id
    claimed_at      TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- batch grouping
    batch_id        UUID,
    UNIQUE (queue_id, idempotency_key)
);

-- Critical composite index for the SKIP LOCKED claim query
CREATE INDEX IF NOT EXISTS idx_jobs_claim
    ON jobs (queue_id, status, run_at, priority DESC)
    WHERE status IN ('queued', 'scheduled');

-- ---- 7. job_executions ----
CREATE TABLE IF NOT EXISTS job_executions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    worker_id   UUID,
    attempt     INT NOT NULL DEFAULT 1,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status      job_status NOT NULL DEFAULT 'running',
    error_msg   TEXT,
    duration_ms INT
);

CREATE INDEX IF NOT EXISTS idx_executions_job ON job_executions(job_id);

-- ---- 8. job_logs ----
CREATE TABLE IF NOT EXISTS job_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID NOT NULL REFERENCES job_executions(id) ON DELETE CASCADE,
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level           TEXT NOT NULL DEFAULT 'info',
    message         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_execution ON job_logs(execution_id);

-- ---- 9. scheduled_jobs (cron definitions) ----
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id        UUID NOT NULL REFERENCES queues(id) ON DELETE CASCADE,
    cron_expr       TEXT NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    priority        INT NOT NULL DEFAULT 0,
    max_attempts    INT NOT NULL DEFAULT 3,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at     TIMESTAMPTZ,
    last_run_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---- 10. workers ----
CREATE TABLE IF NOT EXISTS workers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hostname    TEXT NOT NULL,
    pid         INT NOT NULL,
    status      worker_status NOT NULL DEFAULT 'active',
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---- 11. worker_heartbeats ----
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id   UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
    beat_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active_jobs INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_heartbeats_worker ON worker_heartbeats(worker_id, beat_at DESC);

-- ---- 12. dead_letter_entries ----
CREATE TABLE IF NOT EXISTS dead_letter_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    queue_id        UUID NOT NULL REFERENCES queues(id) ON DELETE CASCADE,
    payload         JSONB NOT NULL DEFAULT '{}',
    failure_reason  TEXT,
    attempt_count   INT NOT NULL,
    first_failed_at TIMESTAMPTZ NOT NULL,
    dead_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dlq_queue ON dead_letter_entries(queue_id, dead_at DESC);

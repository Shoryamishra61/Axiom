-- ============================================================
-- Migration 002: Add 'dead' status, fix indexes
-- ============================================================

-- 1. Add 'dead' to the job_status enum
ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'dead';

-- 2. Fix composite index order: priority DESC should come before run_at
--    (planner uses leftmost columns; priority is a more selective filter)
DROP INDEX IF EXISTS idx_jobs_claim;
CREATE INDEX idx_jobs_claim
    ON jobs (queue_id, status, priority DESC, run_at ASC)
    WHERE status IN ('queued', 'scheduled');

-- 3. Partial index for scheduled_jobs cron materializer query
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_due
    ON scheduled_jobs (next_run_at ASC)
    WHERE is_active = TRUE;

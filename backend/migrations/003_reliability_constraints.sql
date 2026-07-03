-- Reliability and lookup constraints added after the initial assignment pass.
-- Old demo/test rows used synthetic worker IDs; detach those before adding FKs.
UPDATE jobs SET claimed_by = NULL
WHERE claimed_by IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM workers WHERE workers.id = jobs.claimed_by);

UPDATE job_executions SET worker_id = NULL
WHERE worker_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM workers WHERE workers.id = job_executions.worker_id);

ALTER TABLE jobs
    ADD CONSTRAINT fk_jobs_claimed_by_workers
    FOREIGN KEY (claimed_by) REFERENCES workers(id) ON DELETE SET NULL;

ALTER TABLE job_executions
    ADD CONSTRAINT fk_executions_worker
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_dlq_job ON dead_letter_entries(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_queue_created ON jobs(queue_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workers_last_seen ON workers(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_logs_execution_time ON job_logs(execution_id, logged_at ASC);

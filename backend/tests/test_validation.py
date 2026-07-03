"""Trust-boundary validation that must not require PostgreSQL."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas import JobCreate, RetryPolicyCreate


def test_delayed_job_requires_run_at():
    with pytest.raises(ValidationError, match="run_at is required"):
        JobCreate(job_type="delayed")


def test_batch_rejects_nested_control_jobs():
    with pytest.raises(ValidationError, match="batch_jobs may only contain"):
        JobCreate(job_type="batch", batch_jobs=[JobCreate(job_type="cron", cron_expr="* * * * *")])


def test_valid_scheduled_job():
    job = JobCreate(job_type="scheduled", run_at=datetime.now(timezone.utc))
    assert job.job_type == "scheduled"


def test_retry_max_delay_cannot_be_below_base():
    with pytest.raises(ValidationError, match="max_delay_ms"):
        RetryPolicyCreate(base_delay_ms=2000, max_delay_ms=1000)

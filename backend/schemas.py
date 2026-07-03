from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


# ---- Auth ----

class UserRegister(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str
    created_at: datetime
    model_config = {"from_attributes": True}


# ---- Organization ----

class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrgOut(BaseModel):
    id: UUID
    name: str
    owner_id: UUID
    created_at: datetime
    model_config = {"from_attributes": True}


# ---- Project ----

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    org_id: UUID


class ProjectOut(BaseModel):
    id: UUID
    name: str
    org_id: UUID
    created_at: datetime
    model_config = {"from_attributes": True}


# ---- Retry Policy ----

class RetryPolicyCreate(BaseModel):
    strategy: Literal["fixed", "linear", "exponential"] = "exponential"
    max_attempts: int = Field(default=3, ge=1, le=100)
    base_delay_ms: int = Field(default=1000, ge=0)
    max_delay_ms: int = Field(default=60000, ge=0)

    @model_validator(mode="after")
    def validate_delays(self):
        if self.max_delay_ms < self.base_delay_ms:
            raise ValueError("max_delay_ms must be greater than or equal to base_delay_ms")
        return self


class RetryPolicyOut(BaseModel):
    id: UUID
    strategy: str
    max_attempts: int
    base_delay_ms: int
    max_delay_ms: int
    model_config = {"from_attributes": True}


# ---- Queue ----

class QueueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    priority: int = Field(default=0, ge=0)
    concurrency_limit: int = Field(default=10, ge=1, le=1000)
    retry_policy: Optional[RetryPolicyCreate] = None


class QueueUpdate(BaseModel):
    priority: Optional[int] = Field(default=None, ge=0)
    concurrency_limit: Optional[int] = Field(default=None, ge=1, le=1000)
    is_paused: Optional[bool] = None
    retry_policy: Optional[RetryPolicyCreate] = None


class QueueOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    priority: int
    concurrency_limit: int
    is_paused: bool
    retry_policy: Optional[RetryPolicyOut]
    created_at: datetime
    model_config = {"from_attributes": True}


# ---- Job ----

class JobCreate(BaseModel):
    job_type: Literal["immediate", "delayed", "scheduled", "cron", "batch"] = "immediate"
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0)
    run_at: Optional[datetime] = None        # delayed / scheduled
    cron_expr: Optional[str] = None          # cron
    max_attempts: Optional[int] = Field(default=None, ge=1, le=100)
    batch_jobs: Optional[list["JobCreate"]] = None  # batch

    @model_validator(mode="after")
    def validate_type_fields(self):
        if self.job_type in ("delayed", "scheduled") and self.run_at is None:
            raise ValueError("run_at is required for delayed and scheduled jobs")
        if self.job_type not in ("delayed", "scheduled") and self.run_at is not None:
            raise ValueError("run_at is only valid for delayed and scheduled jobs")
        if self.job_type == "cron" and not self.cron_expr:
            raise ValueError("cron_expr is required for cron jobs")
        if self.job_type != "cron" and self.cron_expr is not None:
            raise ValueError("cron_expr is only valid for cron jobs")
        if self.job_type == "batch":
            if not self.batch_jobs:
                raise ValueError("batch_jobs must contain at least one job")
            if any(job.job_type in ("cron", "batch") for job in self.batch_jobs):
                raise ValueError("batch_jobs may only contain immediate, delayed, or scheduled jobs")
        elif self.batch_jobs is not None:
            raise ValueError("batch_jobs is only valid for batch jobs")
        return self


class JobOut(BaseModel):
    id: UUID
    queue_id: UUID
    job_type: str
    status: str
    payload: dict
    priority: int
    run_at: datetime
    attempt_count: int
    max_attempts: int
    created_at: datetime
    completed_at: Optional[datetime]
    batch_id: Optional[UUID]
    model_config = {"from_attributes": True}


# ---- Execution ----

class ExecutionOut(BaseModel):
    id: UUID
    job_id: UUID
    worker_id: Optional[UUID]
    attempt: int
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    error_msg: Optional[str]
    duration_ms: Optional[int]
    model_config = {"from_attributes": True}


# ---- Job Log ----

class JobLogOut(BaseModel):
    id: UUID
    execution_id: UUID
    logged_at: datetime
    level: str
    message: str
    model_config = {"from_attributes": True}


# ---- Scheduled Job (cron definition) ----

class ScheduledJobCreate(BaseModel):
    cron_expr: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0)
    max_attempts: Optional[int] = Field(default=None, ge=1, le=100)


class ScheduledJobOut(BaseModel):
    id: UUID
    queue_id: UUID
    cron_expr: str
    payload: dict
    is_active: bool
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}


# ---- Worker ----

class WorkerOut(BaseModel):
    id: UUID
    hostname: str
    pid: int
    status: str
    started_at: datetime
    last_seen: datetime
    active_jobs: int = 0
    model_config = {"from_attributes": True}


# ---- DLQ ----

class DLQEntryOut(BaseModel):
    id: UUID
    job_id: UUID
    queue_id: UUID
    payload: dict
    failure_reason: Optional[str]
    attempt_count: int
    dead_at: datetime
    model_config = {"from_attributes": True}


# ---- Metrics ----

class QueueMetrics(BaseModel):
    queue_id: UUID
    queue_name: str
    pending: int
    running: int
    completed: int
    failed: int
    dead: int


class SystemMetrics(BaseModel):
    total_queues: int
    active_workers: int
    jobs_pending: int
    jobs_running: int
    jobs_completed_last_hour: int
    jobs_failed_last_hour: int
    throughput: list[dict[str, Any]] = Field(default_factory=list)


# ---- Pagination ----

class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


class JobPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[JobOut]


class BatchJobOut(BaseModel):
    batch_id: UUID
    jobs: list[JobOut]


# ---- Error envelope ----

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None

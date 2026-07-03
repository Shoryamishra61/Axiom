import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


# ---- Enums (mirror SQL enums) ----

class JobStatus(str, enum.Enum):
    queued = "queued"
    scheduled = "scheduled"
    claimed = "claimed"
    running = "running"
    completed = "completed"
    failed = "failed"
    dead = "dead"
    cancelled = "cancelled"


class JobType(str, enum.Enum):
    immediate = "immediate"
    delayed = "delayed"
    scheduled = "scheduled"
    cron = "cron"
    batch = "batch"


class RetryStrategy(str, enum.Enum):
    fixed = "fixed"
    linear = "linear"
    exponential = "exponential"


class WorkerStatus(str, enum.Enum):
    active = "active"
    idle = "idle"
    dead = "dead"


# ---- Models ----

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    organizations = relationship("Organization", back_populates="owner")


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner = relationship("User", back_populates="organizations")
    projects = relationship("Project", back_populates="org")


class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    org = relationship("Organization", back_populates="projects")
    queues = relationship("Queue", back_populates="project")


class RetryPolicy(Base):
    __tablename__ = "retry_policies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy = Column(Enum(RetryStrategy, name="retry_strategy", create_type=False), nullable=False, default=RetryStrategy.exponential)
    max_attempts = Column(Integer, nullable=False, default=3)
    base_delay_ms = Column(Integer, nullable=False, default=1000)
    max_delay_ms = Column(Integer, nullable=False, default=60000)
    __table_args__ = (
        CheckConstraint("max_attempts >= 1"),
        CheckConstraint("base_delay_ms >= 0"),
        CheckConstraint("max_delay_ms >= 0"),
    )


class Queue(Base):
    __tablename__ = "queues"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    priority = Column(Integer, nullable=False, default=0)
    concurrency_limit = Column(Integer, nullable=False, default=10)
    retry_policy_id = Column(UUID(as_uuid=True), ForeignKey("retry_policies.id", ondelete="SET NULL"), nullable=True)
    is_paused = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    project = relationship("Project", back_populates="queues")
    retry_policy = relationship("RetryPolicy")
    jobs = relationship("Job", back_populates="queue")
    __table_args__ = (UniqueConstraint("project_id", "name"),)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    queue_id = Column(UUID(as_uuid=True), ForeignKey("queues.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(Enum(JobType, name="job_type", create_type=False), nullable=False, default=JobType.immediate)
    status = Column(Enum(JobStatus, name="job_status", create_type=False), nullable=False, default=JobStatus.queued)
    payload = Column(JSONB, nullable=False, default=dict)
    priority = Column(Integer, nullable=False, default=0)
    run_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    idempotency_key = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    claimed_by = Column(UUID(as_uuid=True), ForeignKey("workers.id", ondelete="SET NULL", use_alter=True), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    batch_id = Column(UUID(as_uuid=True), nullable=True)
    queue = relationship("Queue", back_populates="jobs")
    executions = relationship("JobExecution", back_populates="job")
    __table_args__ = (
        UniqueConstraint("queue_id", "idempotency_key"),
        # Checklist order: queue_id, status, priority DESC, run_at ASC
        Index("idx_jobs_claim", "queue_id", "status", "priority", "run_at"),
    )


class JobExecution(Base):
    __tablename__ = "job_executions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    worker_id = Column(UUID(as_uuid=True), ForeignKey("workers.id", ondelete="SET NULL", use_alter=True), nullable=True)
    attempt = Column(Integer, nullable=False, default=1)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(JobStatus, name="job_status", create_type=False), nullable=False, default=JobStatus.running)
    error_msg = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    job = relationship("Job", back_populates="executions")
    logs = relationship("JobLog", back_populates="execution")


class JobLog(Base):
    __tablename__ = "job_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("job_executions.id", ondelete="CASCADE"), nullable=False)
    logged_at = Column(DateTime(timezone=True), server_default=func.now())
    level = Column(Text, nullable=False, default="info")
    message = Column(Text, nullable=False)
    execution = relationship("JobExecution", back_populates="logs")


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    queue_id = Column(UUID(as_uuid=True), ForeignKey("queues.id", ondelete="CASCADE"), nullable=False)
    cron_expr = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    priority = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    is_active = Column(Boolean, nullable=False, default=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Worker(Base):
    __tablename__ = "workers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hostname = Column(Text, nullable=False)
    pid = Column(Integer, nullable=False)
    status = Column(Enum(WorkerStatus, name="worker_status", create_type=False), nullable=False, default=WorkerStatus.active)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    heartbeats = relationship("WorkerHeartbeat", back_populates="worker")


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id = Column(UUID(as_uuid=True), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False)
    beat_at = Column(DateTime(timezone=True), server_default=func.now())
    active_jobs = Column(Integer, nullable=False, default=0)
    worker = relationship("Worker", back_populates="heartbeats")


class DeadLetterEntry(Base):
    __tablename__ = "dead_letter_entries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    queue_id = Column(UUID(as_uuid=True), ForeignKey("queues.id", ondelete="CASCADE"), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    failure_reason = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False)
    first_failed_at = Column(DateTime(timezone=True), nullable=False)
    dead_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("job_id"),)

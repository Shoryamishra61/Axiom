import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import settings
from models import User, Organization, Project, Queue, Job, JobStatus, JobType
from auth import hash_password

engine = create_async_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def seed():
    async with AsyncSessionLocal() as db:
        # Create a test user if not exists
        result = await db.execute(select(User).where(User.email == "shoryamishra61@gmail.com"))
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(email="shoryamishra61@gmail.com", name="Shorya Mishra", password_hash=hash_password("password"))
            db.add(user)
            await db.flush()
        
        # Create Org and Project
        org = Organization(name="Acme Corp", owner_id=user.id)
        db.add(org)
        await db.flush()
        
        proj = Project(name="Main Production", org_id=org.id)
        db.add(proj)
        await db.flush()
        
        # Create some Queues
        q1 = Queue(project_id=proj.id, name="emails", concurrency_limit=20)
        q2 = Queue(project_id=proj.id, name="reports", concurrency_limit=5)
        db.add_all([q1, q2])
        await db.flush()
        
        # Seed Jobs for emails
        now = datetime.now(timezone.utc)
        jobs = []
        for i in range(15):
            jobs.append(Job(
                queue_id=q1.id,
                job_type=JobType.immediate,
                status=JobStatus.completed if i < 10 else JobStatus.queued,
                payload={"to": f"user{i}@example.com", "subject": "Welcome!"},
                priority=1,
                run_at=now
            ))
        
        # Seed Jobs for reports
        for i in range(5):
            jobs.append(Job(
                queue_id=q2.id,
                job_type=JobType.immediate,
                status=JobStatus.failed if i == 0 else JobStatus.queued,
                payload={"report_type": "monthly", "user_id": 100+i},
                priority=10,
                run_at=now
            ))
        
        db.add_all(jobs)
        await db.commit()
        print("Database seeded with realistic human-looking data!")

if __name__ == "__main__":
    asyncio.run(seed())

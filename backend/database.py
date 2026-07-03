from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import settings
from sqlalchemy.pool import NullPool

# Supabase uses PgBouncer. Port 6543 is Transaction Mode (breaks asyncpg). 
# Port 5432 is Session Mode / Direct, which fully supports asyncpg prepared statements.
# We auto-patch the URL so you don't even have to change your Render ENV vars.
db_url = settings.database_url.replace(":6543", ":5432")

engine = create_async_engine(
    db_url,
    pool_size=20,
    max_overflow=10,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import settings

from sqlalchemy.pool import NullPool

# Supabase uses PgBouncer in transaction mode. We must:
# 1. Disable SQLAlchemy's internal pool to avoid double-pooling (use NullPool).
# 2. Disable prepared statements which break under transaction-mode PgBouncer.
db_url = settings.database_url
if "?" not in db_url:
    db_url += "?prepared_statement_cache_size=0"
else:
    db_url += "&prepared_statement_cache_size=0"

engine = create_async_engine(
    db_url,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0}
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

"""
migrate.py — Run all SQL migrations against the configured DATABASE_URL.
Safe to run multiple times (uses IF NOT EXISTS / CREATE OR REPLACE patterns).
"""
import asyncio
import os
import pathlib
import asyncpg

DATABASE_URL = os.environ["DATABASE_URL"]

# asyncpg needs plain postgresql:// not postgresql+asyncpg://
DB_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"

async def main():
    print(f"Connecting to database...")
    conn = await asyncpg.connect(DB_URL)
    print("Connected.")

    # Create a migrations tracking table so we don't re-run
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for mf in migration_files:
        already_applied = await conn.fetchval(
            "SELECT 1 FROM _migrations WHERE filename = $1", mf.name
        )
        if already_applied:
            print(f"  Skipping {mf.name} (already applied)")
            continue

        print(f"  Applying {mf.name}...")
        sql = mf.read_text(encoding="utf-8")
        await conn.execute(sql)
        await conn.execute(
            "INSERT INTO _migrations (filename) VALUES ($1)", mf.name
        )
        print(f"  Done: {mf.name}")

    await conn.close()
    print("All migrations applied successfully.")

if __name__ == "__main__":
    asyncio.run(main())

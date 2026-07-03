"""
Shared fixtures for the integration test suite.

Integration tests require a live PostgreSQL instance reachable at DATABASE_URL.
Unit tests (test_retry_math.py) run without any DB.

Start Postgres before running integration tests:
    docker compose up -d postgres
    pytest tests/ -v
"""

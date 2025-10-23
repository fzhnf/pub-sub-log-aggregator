# pyright:reportExplicitAny=false

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from dedup_store import DedupStore


DB_PATH = Path("data/dedup.db")


@pytest.fixture(autouse=True)
def clean_production_db():
    """
    Clean production database before each test to ensure test isolation.
    This is needed because the main app uses a global database path.
    """
    if DB_PATH.exists():
        DB_PATH.unlink()
    # Also ensure the directory exists
    DB_PATH.parent.mkdir(exist_ok=True)
    yield
    # clean up after test
    if DB_PATH.exists():
        DB_PATH.unlink()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db():
    """Create temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_dedup.db"

        store = DedupStore(str(db_path))
        await store.initialize()

        yield store

        await store.close()


@pytest_asyncio.fixture
async def test_client():
    """
    Fixed test client - don't use lifespan_context which causes thread issues
    """
    # Create fresh app instance for each test
    from main import app, lifespan

    # Manually run lifespan
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", timeout=10.0
        ) as client:
            await asyncio.sleep(0.1)  # Let consumer start
            yield client


@pytest.fixture
def sample_event():
    """Sample event data for testing"""
    return {
        "topic": "test.events",
        "event_id": "test-001",
        "timestamp": "2025-10-23T10:00:00Z",
        "source": "test-source",
        "payload": {"message": "Test event", "level": "INFO"},
    }


@pytest.fixture
def sample_batch(sample_event: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "events": [
            sample_event,
            {
                **sample_event,
                "event_id": "test-002",
                "timestamp": "2025-10-23T10:00:01Z",
            },
            {
                **sample_event,
                "event_id": "test-003",
                "timestamp": "2025-10-23T10:00:02Z",
            },
        ]
    }

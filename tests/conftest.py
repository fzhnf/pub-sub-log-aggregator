import asyncio
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from dedup_store import DedupStore
from main import app


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
    FastAPI test client with manual lifespan trigger.
    """
    # ✅ Manually trigger lifespan startup
    async with app.router.lifespan_context(app):
        # Now create client
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", timeout=10.0
        ) as client:
            # Give consumer worker time to start
            await asyncio.sleep(0.1)

            yield client
            # Lifespan shutdown happens automatically when exiting context


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
def sample_batch(sample_event):
    """Sample batch of events"""
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

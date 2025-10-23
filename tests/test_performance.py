# pyright: reportExplicitAny=false
# pyright: reportAny=false

import asyncio
import time
from typing import Any
from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_performance_5000_events(test_client: AsyncClient):
    """Test 5000 events with exactly 1000 duplicates"""
    events: list[dict[str, Any]] = []

    # Create 4000 unique events
    for i in range(4000):
        events.append(
            {
                "topic": "performance.test",
                "event_id": f"unique-{i}",
                "timestamp": "2025-10-23T10:00:00Z",
                "source": "perf-test",
                "payload": {"count": i, "message": f"Unique Event {i}"},
            }
        )

    # Add 1000 duplicates of the first 1000 events
    for i in range(1000):
        events.append(
            {
                "topic": "performance.test",
                "event_id": f"unique-{i}",  # Same event_id as first 1000
                "timestamp": "2025-10-23T10:00:00Z",
                "source": "perf-test",
                "payload": {"count": i, "message": f"Duplicate of {i}"},
            }
        )

    # Send in batches
    start_time = time.time()
    for i in range(0, len(events), 100):
        batch = events[i : i + 100]
        response = await test_client.post("/publish", json={"events": batch})
        assert response.status_code == 202

    processing_time = time.time() - start_time

    # Wait for processing
    await asyncio.sleep(3.0)

    # Verify
    assert processing_time < 30.0

    stats_response = await test_client.get("/stats")
    stats = stats_response.json()

    # Exact expectations
    assert stats["received"] == 5000
    assert stats["duplicate_dropped"] == 1000, (
        f"Expected 1000 duplicates, got {stats['duplicate_dropped']}"
    )
    assert stats["unique_processed"] == 4000

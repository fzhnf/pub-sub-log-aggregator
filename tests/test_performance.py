# pyright: reportExplicitAny=false
# pyright: reportAny=false

import asyncio
import time
from typing import Any
from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_concurrent_publish_stress_5000_events(test_client: AsyncClient):
    """
    Test 12: Concurrent publishers sending 5000 events (at-least-once simulation)

    Requirement: T3 (at-least-once + idempotent consumer)
    Verifies: Idempotency under concurrent load, system responsiveness

    Scenario: 100 concurrent publishers each send 50 events (5000 total)
    with 20% duplication to simulate at-least-once with retries.
    """

    async def publish_batch(batch_num: int):
        """Each concurrent task publishes one batch of 50 events"""
        batch_events: list[dict[str, Any]] = []

        for i in range(50):
            event_idx = (batch_num * 50 + i) % 4000  # 4000 unique IDs
            batch_events.append(
                {
                    "topic": "concurrent.stress.test",
                    "event_id": f"event-{event_idx}",  # 20% will be duplicates
                    "timestamp": "2025-10-23T10:00:00Z",
                    "source": f"concurrent-publisher-{batch_num}",
                    "payload": {
                        "batch": batch_num,
                        "index": i,
                        "message": f"Concurrent event from publisher {batch_num}",
                    },
                }
            )

        return await test_client.post("/publish", json={"events": batch_events})

    # Launch 100 concurrent publishers (100 * 50 = 5000 events)
    print("Starting concurrent publish stress test (5000 events)...")
    start_time = time.time()

    tasks = [publish_batch(i) for i in range(100)]
    responses = await asyncio.gather(*tasks)

    publish_duration = time.time() - start_time
    print(f"All 5000 events published in {publish_duration:.2f}s")

    # Verify all publishes succeeded
    assert all(r.status_code == 202 for r in responses), (
        "Not all publishes returned 202 Accepted"
    )
    print(f"✓ All {len(responses)} concurrent publishes returned 202")

    # Wait for consumer to process all events
    print("Waiting for consumer to process events...")
    await asyncio.sleep(2.0)

    # Check stats
    stats_response = await test_client.get("/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()

    print("\nStats after concurrent processing:")
    print(f"  - Received: {stats['received']}")
    print(f"  - Unique Processed: {stats['unique_processed']}")
    print(f"  - Duplicate Dropped: {stats['duplicate_dropped']}")
    print(f"  - Topics: {stats['topics']}")

    # Assertions: Verify at-least-once semantics
    assert stats["received"] == 5000, (
        f"Should receive 5000 events, got {stats['received']}"
    )
    assert stats["unique_processed"] == 4000, (
        f"Should process 4000 unique events, got {stats['unique_processed']}"
    )
    assert stats["duplicate_dropped"] == 1000, (
        f"Should drop 1000 duplicates, got {stats['duplicate_dropped']}"
    )

    # Verify idempotency: duplicate rate should be ~20%
    dup_rate = stats["duplicate_dropped"] / stats["received"]
    assert 0.15 <= dup_rate <= 0.25, (
        f"Duplicate rate {dup_rate * 100:.1f}% not in expected 15-25% range"
    )

    # Verify responsiveness: all 5000 concurrent events processed in reasonable time
    total_time = publish_duration + 2.0  # publish + processing wait
    assert total_time < 15.0, (
        f"Total time {total_time:.2f}s exceeded 15s threshold (not responsive enough)"
    )

    print(f"\n✓ Test passed: Processed {stats['received']} concurrent events")
    print(
        f"✓ Idempotency verified: {dup_rate * 100:.1f}% duplicate rate (expected ~20%)"
    )
    print(f"✓ Responsiveness verified: Total time {total_time:.2f}s < 15s threshold")

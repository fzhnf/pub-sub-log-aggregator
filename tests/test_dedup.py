"""
Unit tests for deduplication store
Tests core idempotency and persistence logic
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from dedup_store import DedupStore

from dedup_store import DedupStore


@pytest.mark.asyncio
async def test_dedup_new_event(test_db: DedupStore):
    """
    Test 1: New event is NOT a duplicate

    Requirement: T3 (at-least-once + idempotency)
    Verifies: check_and_mark() returns True for new events
    """
    # Arrange
    topic = "test.topic"
    event_id = "new-event-001"

    # Act
    is_new = await test_db.check_and_mark(topic, event_id)

    # Assert
    assert is_new is True, "New event should be marked as new"

    # Verify it's stored in DB
    is_duplicate = await test_db.is_duplicate(topic, event_id)
    assert is_duplicate is True, "Event should now be in dedup store"


@pytest.mark.asyncio
async def test_dedup_duplicate_event(test_db: DedupStore):
    """
    Test 2: Duplicate event is correctly detected

    Requirement: T3, T6 (idempotency + fault tolerance)
    Verifies: Same event_id is rejected on second attempt
    """
    # Arrange
    topic = "test.topic"
    event_id = "duplicate-event-001"

    # Act - First insert
    is_new_first = await test_db.check_and_mark(topic, event_id)

    # Act - Second insert (duplicate)
    is_new_second = await test_db.check_and_mark(topic, event_id)

    # Assert
    assert is_new_first is True, "First event should be new"
    assert is_new_second is False, "Second event should be duplicate"


@pytest.mark.asyncio
async def test_dedup_different_topics(test_db: DedupStore):
    """
    Test 3: Same event_id in different topics are NOT duplicates

    Requirement: T4 (naming scheme - topic:event_id composite key)
    Verifies: Dedup key includes both topic and event_id
    """
    # Arrange
    event_id = "shared-event-001"
    topic1 = "topic.one"
    topic2 = "topic.two"

    # Act
    is_new_topic1 = await test_db.check_and_mark(topic1, event_id)
    is_new_topic2 = await test_db.check_and_mark(topic2, event_id)

    # Assert
    assert is_new_topic1 is True, "Event in topic1 should be new"
    assert is_new_topic2 is True, "Event in topic2 should be new (different topic)"

    # Verify both are stored separately
    assert await test_db.is_duplicate(topic1, event_id) is True
    assert await test_db.is_duplicate(topic2, event_id) is True


@pytest.mark.asyncio
async def test_dedup_persistence_after_reconnect(test_db: DedupStore):
    """
    Test 4: Dedup store survives database reconnect

    Requirement: T6 (fault tolerance - crash recovery)
    Verifies: Data persists after closing and reopening connection
    """
    # Arrange
    topic = "test.persistence"
    event_id = "persist-001"
    db_path = test_db.db_path

    # Act - Insert event and close connection
    is_new_before = await test_db.check_and_mark(topic, event_id)
    await test_db.close()

    # Reconnect to same database
    new_store = DedupStore(str(db_path))
    await new_store.initialize()

    # Try to insert same event again
    is_new_after = await new_store.check_and_mark(topic, event_id)

    # Assert
    assert is_new_before is True, "First insert should succeed"
    assert is_new_after is False, "After reconnect, should detect duplicate"

    # Cleanup
    await new_store.close()


@pytest.mark.asyncio
async def test_event_payload_storage(test_db: DedupStore):
    """
    Test 5: Full event payloads are stored and retrievable

    Requirement: T6 (durability), Implementation spec (GET /events)
    Verifies: Event data persists beyond dedup metadata
    """
    from models import StoredEvent

    # Arrange
    event = StoredEvent(
        topic="test.storage",
        event_id="storage-001",
        timestamp="2025-10-23T10:00:00Z",
        source="test-source",
        payload={"message": "Test payload", "count": 42},
    )

    # Act - Store event
    _ = await test_db.check_and_mark(event.topic, event.event_id)
    await test_db.store_event_payload(event)

    # Retrieve events
    stored_events = await test_db.load_all_events(topic="test.storage", limit=10)

    # Assert
    assert len(stored_events) == 1, "Should retrieve 1 stored event"
    retrieved = stored_events[0]
    assert retrieved.topic == event.topic
    assert retrieved.event_id == event.event_id
    assert retrieved.payload["message"] == "Test payload"
    assert retrieved.payload["count"] == 42


@pytest.mark.asyncio
async def test_stats_counters_persistence(test_db: DedupStore):
    """
    Test 6: Stats counters persist across restarts

    Requirement: T8 (evaluation metrics must be accurate)
    Verifies: received/duplicate_dropped counters survive reconnect
    """
    # Arrange
    db_path = test_db.db_path

    # Act - Increment counters
    await test_db.increment_received()
    await test_db.increment_received()
    await test_db.increment_duplicate_dropped()

    received_before = await test_db.get_counter("received")
    duplicates_before = await test_db.get_counter("duplicate_dropped")

    # Close and reconnect
    await test_db.close()
    new_store = DedupStore(str(db_path))
    await new_store.initialize()

    # Retrieve counters after reconnect
    received_after = await new_store.get_counter("received")
    duplicates_after = await new_store.get_counter("duplicate_dropped")

    # Assert
    assert received_before == 2, "Should have 2 received events"
    assert duplicates_before == 1, "Should have 1 duplicate"
    assert received_after == 2, "Received counter should persist"
    assert duplicates_after == 1, "Duplicate counter should persist"

    # Cleanup
    await new_store.close()

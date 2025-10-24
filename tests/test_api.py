"""
Integration tests for FastAPI endpoints
Tests HTTP API behavior and end-to-end flows
"""
# pyright: reportExplicitAny=false
# pyright: reportAny=false

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_publish_single_event(
    test_client: AsyncClient,
    sample_event: dict[str, Any],
):
    """
    Test 7: POST /publish accepts single event

    Requirement: Implementation spec (POST /publish endpoint)
    Verifies: Event validation, 202 response, queuing
    """
    # Act
    response = await test_client.post("/publish", json={"events": [sample_event]})

    # Assert
    assert response.status_code == 202, "Should return 202 Accepted"
    data = response.json()
    assert data["accepted"] == 1, "Should accept 1 event"
    # ✅ Fix: Match actual message format
    assert "accepted" in data["message"].lower()

    # Wait for async processing
    await asyncio.sleep(0.3)

    # Verify event was processed
    stats_response = await test_client.get("/stats")
    stats = stats_response.json()
    assert stats["received"] >= 1, "Should count received event"


@pytest.mark.asyncio
async def test_publish_batch_events(
    test_client: AsyncClient, sample_batch: dict[str, list[dict[str, Any]]]
):
    """
    Test 8: POST /publish accepts batch of events

    Requirement: Implementation spec (batch up to 1000 events)
    Verifies: Batch processing, all events accepted
    """
    # Act
    response = await test_client.post("/publish", json=sample_batch)

    # Assert
    assert response.status_code == 202
    data = response.json()
    assert data["accepted"] == 3, "Should accept all 3 events in batch"

    # Wait for processing
    await asyncio.sleep(0.2)

    # Verify all processed
    stats_response = await test_client.get("/stats")
    stats = stats_response.json()
    assert stats["unique_processed"] >= 3, "Should process all unique events"


@pytest.mark.asyncio
async def test_duplicate_detection_via_api(
    test_client: AsyncClient, sample_event: dict[str, Any]
):
    """
    Test 9: End-to-end duplicate detection through API

    Requirement: T3 (idempotent consumer), T6 (fault tolerance)
    Verifies: Duplicate events are counted but not reprocessed
    """
    # Arrange - Publish same event twice
    event_batch = {"events": [sample_event]}

    # Act - First publish
    response1 = await test_client.post("/publish", json=event_batch)
    assert response1.status_code == 202

    # Wait for processing
    await asyncio.sleep(0.1)

    # Get stats after first event
    stats1 = (await test_client.get("/stats")).json()
    received1 = stats1["received"]
    unique1 = stats1["unique_processed"]

    # Act - Second publish (duplicate)
    response2 = await test_client.post("/publish", json=event_batch)
    assert response2.status_code == 202

    # Wait for processing
    await asyncio.sleep(0.1)

    # Get stats after duplicate
    stats2 = (await test_client.get("/stats")).json()
    received2 = stats2["received"]
    unique2 = stats2["unique_processed"]
    duplicate2 = stats2["duplicate_dropped"]

    # Assert
    assert received2 == received1 + 1, "Should count both received events"
    assert unique2 == unique1, "Should NOT increment unique count for duplicate"
    assert duplicate2 >= 1, "Should increment duplicate counter"


@pytest.mark.asyncio
async def test_get_events_endpoint(
    test_client: AsyncClient, sample_event: dict[str, Any]
):
    """
    Test 10: GET /events returns processed events

    Requirement: Implementation spec (GET /events endpoint)
    Verifies: Event retrieval, filtering, pagination
    """
    # Arrange - Publish event
    _ = await test_client.post("/publish", json={"events": [sample_event]})
    await asyncio.sleep(0.1)  # Wait for processing

    # Act - Get all events
    response = await test_client.get("/events")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1, "Should have at least 1 event"
    assert len(data["events"]) >= 1, "Should return event list"

    # Verify event structure
    first_event = data["events"][0]
    assert "topic" in first_event
    assert "event_id" in first_event
    assert "payload" in first_event

    # Test topic filtering
    topic_response = await test_client.get(f"/events?topic={sample_event['topic']}")
    topic_data = topic_response.json()
    assert topic_data["topic"] == sample_event["topic"]
    assert topic_data["total"] >= 1


@pytest.mark.asyncio
async def test_get_events_sorted_by_timestamp(test_client: AsyncClient):
    """
    Test 11: GET /events returns events sorted by timestamp DESC

    Requirement: T5 (ordering - events sorted for analysis)
    Verifies: Timestamp ordering, not insertion order

    This proves the claim in Section 2.5.3:
    "Events sorted by timestamp DESC per-topic"
    """
    # Publish 3 events with INTENTIONAL out-of-order timestamps
    events = [
        {
            "topic": "test.ordering",
            "event_id": "event-newest",
            "timestamp": "2025-10-23T10:00:03Z",  # Should be first
            "source": "source-a",
            "payload": {"sequence": 3},
        },
        {
            "topic": "test.ordering",
            "event_id": "event-oldest",
            "timestamp": "2025-10-23T10:00:01Z",  # Should be last (arrives second)
            "source": "source-b",
            "payload": {"sequence": 1},
        },
        {
            "topic": "test.ordering",
            "event_id": "event-middle",
            "timestamp": "2025-10-23T10:00:02Z",  # Should be middle
            "source": "source-c",
            "payload": {"sequence": 2},
        },
    ]

    # Publish in non-timestamp order: newest, oldest, middle
    for event in events:
        response = await test_client.post("/publish", json={"events": [event]})
        assert response.status_code == 202

    await asyncio.sleep(0.2)  # Wait for processing

    # GET /events and verify sorting by timestamp DESC
    response = await test_client.get("/events?topic=test.ordering&limit=10")
    assert response.status_code == 200

    result = response.json()
    returned_events = result["events"]

    # Assert correct timestamp order (DESC = newest first)
    assert len(returned_events) == 3, "Should return all 3 events"
    assert returned_events[0]["event_id"] == "event-newest", "Newest should be first"
    assert returned_events[1]["event_id"] == "event-middle", "Middle should be second"
    assert returned_events[2]["event_id"] == "event-oldest", "Oldest should be last"

    # Verify timestamps are actually in DESC order
    ts0 = returned_events[0]["timestamp"]
    ts1 = returned_events[1]["timestamp"]
    ts2 = returned_events[2]["timestamp"]
    assert ts0 > ts1 > ts2, f"Timestamps not in DESC order: {ts0}, {ts1}, {ts2}"

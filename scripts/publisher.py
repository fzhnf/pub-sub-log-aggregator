#!/usr/bin/env python3
"""
Event publisher for testing Pub-Sub aggregator
Sends batch of events including duplicates to aggregator service
"""

# pyright: reportExplicitAny=false
# pyright: reportAny=false

import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

AGGREGATOR_URL = os.getenv("AGGREGATOR_URL", "http://localhost:8080")
TOTAL_EVENTS = 100
DUPLICATE_RATE = 0.2  # 20% duplicates


def generate_events(count: int, duplicate_rate: float = 0.2):
    """Generate events with specified duplicate rate"""
    events: list[dict[str, Any]] = []
    unique_ids: list[str] = []

    for i in range(count):
        # Generate duplicate based on rate
        if i > 0 and (i / count) < duplicate_rate:
            # Reuse previous event_id (create duplicate)
            event_id = unique_ids[-1]
        else:
            # Generate new unique ID
            event_id = str(uuid4())
            unique_ids.append(event_id)

        event = {
            "topic": f"test.topic.{i % 5}",  # 5 different topics
            "event_id": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "publisher-service",
            "payload": {
                "message": f"Test event {i}",
                "batch_id": "test-batch-001",
                "sequence": i,
            },
        }
        events.append(event)

    return events


def main():
    """Publish events to aggregator"""
    print(f"Publisher starting - target: {AGGREGATOR_URL}")

    # Wait for aggregator to be ready
    max_retries = 10
    for attempt in range(max_retries):
        try:
            response = httpx.get(f"{AGGREGATOR_URL}/health", timeout=2.0)
            if response.status_code == 200:
                print("✅ Aggregator is healthy")
                break
        except Exception:
            print(f"⏳ Waiting for aggregator... (attempt {attempt + 1}/{max_retries})")
            time.sleep(2)
    else:
        print("❌ Aggregator not available - exiting")
        return

    # Generate and send events
    print(
        f"📤 Generating {TOTAL_EVENTS} events ({DUPLICATE_RATE * 100}% duplicates)..."
    )
    events = generate_events(TOTAL_EVENTS, DUPLICATE_RATE)

    # Send in batches of 50
    batch_size = 50
    for i in range(0, len(events), batch_size):
        batch = events[i : i + batch_size]

        try:
            response = httpx.post(
                f"{AGGREGATOR_URL}/publish", json={"events": batch}, timeout=10.0
            )

            if response.status_code == 202:
                print(f"✅ Batch {i // batch_size + 1}: Sent {len(batch)} events")
            else:
                print(
                    f"❌ Batch {i // batch_size + 1}: Failed - {response.status_code}"
                )

        except Exception as e:
            print(f"❌ Error sending batch: {e}")

        # Small delay between batches
        time.sleep(0.5)

    # Wait for processing
    print("⏳ Waiting for events to be processed...")
    time.sleep(3)

    # Check stats
    try:
        response = httpx.get(f"{AGGREGATOR_URL}/stats")
        stats = response.json()
        print("\n📊 Final Statistics:")
        print(f"  Received: {stats['received']}")
        print(f"  Unique Processed: {stats['unique_processed']}")
        print(f"  Duplicates Dropped: {stats['duplicate_dropped']}")
        print(
            f"  Duplicate Rate: {stats['duplicate_dropped'] / stats['received'] * 100:.1f}%"
        )
        print(f"  Topics: {len(stats['topics'])}")

    except Exception as e:
        print(f"❌ Error fetching stats: {e}")

    print("\n✅ Publisher completed")


if __name__ == "__main__":
    main()

"""
Pub-Sub Log Aggregator - Main Application
FastAPI server with idempotent consumer and deduplication
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from dedup_store import DedupStore
from models import (
    Event,
    EventBatch,
    EventQueryResponse,
    PublishResponse,
    StoredEvent,
    SystemStats,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global state
dedup_store: DedupStore
event_queue: asyncio.Queue[Event]  # ← concrete type argument
processed_events: list[StoredEvent] = []  # In-memory storage for GET /events
stats_counters = {
    "received": 0,
    "unique_processed": 0,
    "duplicate_dropped": 0,
}
start_time = time.time()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifecycle management."""
    global dedup_store, event_queue, processed_events

    # Startup
    logger.info("Starting Pub-Sub Log Aggregator...")

    dedup_store = DedupStore("data/dedup.db")
    await dedup_store.initialize()

    event_queue = asyncio.Queue(maxsize=10000)

    # Load existing events from database (BARU)
    processed_events = await dedup_store.load_all_events(limit=10000)
    logger.info(f"Loaded {len(processed_events)} existing events from database")

    consumer_task = asyncio.create_task(consumer_worker())
    logger.info("Consumer worker started")

    yield

    # Shutdown (sama seperti sebelumnya)
    logger.info("Shutting down...")
    __ = consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await dedup_store.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Pub-Sub Log Aggregator",
    description="Idempotent event processing with deduplication",
    version="1.0.0",
    lifespan=lifespan,
)


async def consumer_worker():
    """Background worker that consumes events from queue."""
    logger.info("Consumer worker running")

    while True:
        try:
            event = await event_queue.get()

            # Idempotent check (atomic DB operation)
            is_new = await dedup_store.check_and_mark(event.topic, event.event_id)

            if is_new:
                # Store event payload
                stored_event = StoredEvent.from_event(event)
                await dedup_store.store_event_payload(stored_event)
                processed_events.append(stored_event)

                logger.info(f"Processed: {event.topic}:{event.event_id}")
            else:
                # Duplicate - increment counter
                await dedup_store.increment_duplicate_dropped()

                logger.warning(f"Duplicate: {event.topic}:{event.event_id}")

            event_queue.task_done()

        except asyncio.CancelledError:
            logger.info("Consumer worker cancelled")
            break
        except Exception as e:
            logger.error(f"Error in consumer: {e}", exc_info=True)


@app.post("/publish", response_model=PublishResponse, status_code=202)
async def publish_events(batch: EventBatch):
    """
    POST /publish - Accept events for processing

    Accepts single event or batch (up to 1000 events).
    Events are validated by Pydantic and queued for async processing.

    Returns 202 Accepted (events queued, not yet processed).
    Returns 400 Bad Request if validation fails (any event in batch).
    Returns 503 Service Unavailable if queue is full.
    """
    try:
        accepted = 0

        for event in batch.events:
            try:
                # Add to queue (non-blocking with timeout)
                await asyncio.wait_for(event_queue.put(event), timeout=5.0)
                accepted += 1

                # ✅ Persist to DB instead of in-memory
                await dedup_store.increment_received()

            except asyncio.TimeoutError:
                logger.error("Queue full - rejecting events")
                raise HTTPException(
                    status_code=503, detail="Event queue full - system overloaded"
                )

        logger.info(f"Accepted {accepted} events for processing")

        return PublishResponse(
            accepted=accepted, message=f"Accepted {accepted} events for processing"
        )

    except Exception as e:
        logger.error(f"Error in /publish: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events", response_model=EventQueryResponse)
async def get_events(topic: str | None = None, limit: int = 100):
    """
    GET /events?topic=<topic>&limit=<limit>

    Returns list of processed events, optionally filtered by topic.

    Query parameters:
    - topic: Filter by topic name (optional)
    - limit: Max number of events to return (default 100, max 1000)

    Returns events in reverse chronological order (newest first).
    """
    try:
        # Enforce max limit
        limit = min(limit, 1000)

        if topic:
            # Filter by topic
            filtered = [e for e in processed_events if e.topic == topic]
            filtered = filtered[:limit]

            return EventQueryResponse(
                topic=topic,
                total=len(filtered),
                events=[dict(e.to_api_dict()) for e in filtered],  # cast to plain dict
            )
        else:
            # Return all events (up to limit)
            events_slice = processed_events[:limit]

            return EventQueryResponse(
                topic=None,
                total=len(events_slice),
                events=[dict(e.to_api_dict()) for e in events_slice],
            )

    except Exception as e:
        logger.error(f"Error in /events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", response_model=SystemStats)
async def get_stats():
    """
    GET /stats - System statistics and metrics

    Returns:
    - uptime_seconds: Time since server started
    - received: Total events received via /publish
    - unique_processed: Unique events processed (after dedup)
    - duplicate_dropped: Number of duplicates detected
    - topics: List of all distinct topics seen

    Computed properties:
    - duplicate_rate: Percentage of duplicates (duplicate_dropped / received)
    """
    try:
        uptime = time.time() - start_time

        # Get topics from dedup store
        dedup_stats = await dedup_store.get_stats()

        return SystemStats(
            uptime_seconds=round(uptime, 2),
            received=await dedup_store.get_counter("received"),
            duplicate_dropped=await dedup_store.get_counter("duplicate_dropped"),
            unique_processed=dedup_stats["total_processed"],
            topics=dedup_stats["topics"],
        )

    except Exception as e:
        logger.error(f"Error in /stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """
    GET /health - Simple health check endpoint
    Returns 200 OK if service is running
    """
    return {
        "status": "healthy",
        "queue_size": event_queue.qsize(),
        "processed_count": len(processed_events),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, log_level="info")

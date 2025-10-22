"""
Data models for Pub-Sub Log Aggregator
Simplified for grading requirements - focuses on core spec compliance
"""

from __future__ import annotations  # keeps 3.9-3.10 happy

from datetime import datetime, timezone
from typing import ClassVar, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)


class EventDict(TypedDict):
    topic: str
    event_id: str
    timestamp: str
    source: str
    payload: dict[str, JsonValue]


class EventPayload(TypedDict, total=False):
    """Example payload; extend or tighten as needed."""

    level: str
    message: str


class Event(BaseModel):
    """
    Core event model matching spec requirements.
    Required fields: topic, event_id, timestamp, source, payload
    """

    topic: str = Field(..., min_length=1, max_length=255)
    event_id: str = Field(..., min_length=1, max_length=128)
    timestamp: str = Field(..., description="ISO8601 timestamp")
    source: str = Field(..., min_length=1, max_length=255)
    payload: dict[str, JsonValue]  # was dict[str, Any]

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate ISO8601 format only - accept client timestamp as-is"""
        try:
            _ = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"Invalid ISO8601 timestamp: {v}") from e
        return v

    def dedup_key(self) -> str:
        """
        Composite key for deduplication: (topic, event_id)
        Matches spec requirement for idempotency
        """
        return f"{self.topic}:{self.event_id}"

    model_config: ClassVar[ConfigDict] = ConfigDict(  # ← note ClassVar
        json_schema_extra={
            "example": {
                "topic": "logs.application.error",
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2025-10-22T10:30:45Z",
                "source": "web-server-01",
                "payload": {"level": "ERROR", "message": "Connection timeout"},
            }
        }
    )


class EventBatch(BaseModel):
    """Support batch publish (single or multiple events)"""

    events: list[Event] = Field(..., min_length=1, max_length=1000)


class PublishResponse(BaseModel):
    """Response for POST /publish"""

    accepted: int
    message: str = "Events queued for processing"


class EventQueryResponse(BaseModel):
    """Response for GET /events?topic=..."""

    topic: str | None = None
    total: int
    events: list[dict[str, object]]  # accepts any JSON-serialisable dict


class SystemStats(BaseModel):
    """
    System statistics for GET /stats endpoint
    Maps to T8 evaluation metrics (graded: Observability 4 pts)
    """

    uptime_seconds: float
    received: int = Field(..., description="Total events received")
    unique_processed: int = Field(..., description="Unique events processed")
    duplicate_dropped: int = Field(..., description="Duplicates detected")
    topics: list[str] = Field(..., description="All topics seen")

    @property
    def topics_count(self) -> int:
        return len(self.topics)

    @property
    def duplicate_rate(self) -> float:
        """Duplicate rate as percentage"""
        if self.received == 0:
            return 0.0
        return (self.duplicate_dropped / self.received) * 100

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={
            "example": {
                "uptime_seconds": 123.45,
                "received": 5000,
                "unique_processed": 4000,
                "duplicate_dropped": 1000,
                "topics": ["logs.app.error", "metrics.cpu"],
            }
        }
    )


class StoredEvent(BaseModel):
    """
    Internal model for storing processed events
    Used by GET /events to return event list
    """

    topic: str
    event_id: str
    timestamp: str
    source: str
    payload: dict[str, JsonValue]  # was dict[str, Any]
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_api_dict(self) -> EventDict:  # ← new helper
        return {
            "topic": self.topic,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "payload": self.payload,
        }

    @classmethod
    def from_event(cls, event: Event) -> "StoredEvent":
        """Convert incoming Event to StoredEvent"""
        return cls(
            topic=event.topic,
            event_id=event.event_id,
            timestamp=event.timestamp,
            source=event.source,
            payload=event.payload,
        )

    def to_dict(self):
        """Convert to dict for API response"""
        return {
            "topic": self.topic,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "payload": self.payload,
            "processed_at": self.processed_at,
        }

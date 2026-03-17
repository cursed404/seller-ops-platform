from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    occurred_at: datetime = Field(default_factory=utcnow)
    correlation_id: str
    trace_id: str
    workflow_id: str | None = None
    incident_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


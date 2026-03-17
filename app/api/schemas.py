from typing import Any

from pydantic import BaseModel, Field


class IncidentCreateRequest(BaseModel):
    title: str
    description: str
    order_id: str | None = None
    sku: str | None = None
    sync_job_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentCreateResponse(BaseModel):
    incident_id: str
    workflow_id: str


class ApprovalRequestBody(BaseModel):
    approved: bool
    decided_by: str
    note: str | None = None


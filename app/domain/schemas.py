from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import ActionType, ApprovalStatus, IncidentType, Severity, WorkflowStatus


class Citation(BaseModel):
    document_id: str
    slug: str
    title: str
    excerpt: str
    score: float


class IncidentClassification(BaseModel):
    incident_type: IncidentType
    severity: Severity
    summary: str
    rationale: str


class ContextSummary(BaseModel):
    headline: str
    details: dict[str, Any] = Field(default_factory=dict)
    risk_signals: list[str] = Field(default_factory=list)


class ProposedAction(BaseModel):
    action_type: ActionType
    summary: str
    rationale: str
    requires_approval: bool
    risk_level: Severity
    target_reference: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    requires_approval: bool
    reason: str
    approval_scope: str | None = None


class VerificationResult(BaseModel):
    workflow_status: WorkflowStatus
    summary: str
    completed: bool
    follow_up_actions: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    approval_id: str
    status: ApprovalStatus
    decided_by: str
    note: str | None = None
    decided_at: datetime


class WorkflowResult(BaseModel):
    recommendation: str
    verification: VerificationResult
    citations: list[Citation] = Field(default_factory=list)


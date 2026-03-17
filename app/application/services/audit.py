from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ActionStatus, ApprovalStatus, StepStatus, ToolStatus, WorkflowStatus
from app.domain.events import EventEnvelope
from app.infrastructure.db.models import (
    ActionExecution,
    ApprovalRequest,
    OperationalIncident,
    RetryAttempt,
    ToolInvocation,
    WorkflowEvent,
    WorkflowRun,
    WorkflowStep,
)
from app.infrastructure.messaging.redpanda import KafkaEventPublisher
from app.infrastructure.observability.metrics import (
    approval_wait_seconds,
    tool_invocations_total,
    workflow_duration_seconds,
    workflow_errors_total,
    workflow_retries_total,
    workflow_runs_total,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass
class EventContext:
    workflow_id: str | None
    incident_id: str | None
    correlation_id: str
    trace_id: str


class AuditTrailService:
    def __init__(self, session: Session, publisher: KafkaEventPublisher | None = None) -> None:
        self._session = session
        self._publisher = publisher

    def start_step(self, *, workflow_id: str, step_name: str) -> WorkflowStep:
        step = WorkflowStep(workflow_id=workflow_id, step_name=step_name, status=StepStatus.STARTED.value)
        self._session.add(step)
        self._session.flush()
        return step

    def complete_step(self, step: WorkflowStep, output: dict[str, Any] | None = None) -> None:
        step.status = StepStatus.COMPLETED.value
        step.output_json = jsonable_encoder(output) if output is not None else None
        step.completed_at = utcnow()
        self._session.flush()

    def fail_step(self, step: WorkflowStep, *, error: Exception | str) -> None:
        message = str(error)
        step.status = StepStatus.FAILED.value
        step.error_json = {"message": message}
        step.completed_at = utcnow()
        workflow_errors_total.labels(step=step.step_name, error_type=type(error).__name__).inc()
        self._session.flush()

    def update_incident_classification(
        self,
        *,
        incident: OperationalIncident,
        incident_type: str,
        severity: str,
    ) -> None:
        incident.incident_type = incident_type
        incident.severity = severity
        incident.updated_at = utcnow()
        self._session.flush()

    def mark_workflow_running(self, workflow: WorkflowRun, *, phase: str = "initial") -> None:
        workflow.status = WorkflowStatus.RUNNING.value
        workflow.phase = phase
        workflow.started_at = workflow.started_at or utcnow()
        self._session.flush()

    def update_workflow_state(
        self,
        workflow: WorkflowRun,
        *,
        status: WorkflowStatus,
        context_summary: dict[str, Any] | None = None,
        recommended_action: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
        error: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        selected_runbook_id: str | None = None,
        phase: str | None = None,
    ) -> None:
        workflow.status = status.value
        if context_summary is not None:
            workflow.context_summary_json = jsonable_encoder(context_summary)
        if recommended_action is not None:
            workflow.recommended_action_json = jsonable_encoder(recommended_action)
        if citations is not None:
            workflow.citations_json = jsonable_encoder(citations)
        if error is not None:
            workflow.error_json = jsonable_encoder(error)
        if result is not None:
            workflow.result_summary_json = jsonable_encoder(result)
        if selected_runbook_id is not None:
            workflow.selected_runbook_id = selected_runbook_id
        if phase is not None:
            workflow.phase = phase
        if status in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}:
            workflow.completed_at = utcnow()
            if workflow.started_at:
                duration = (
                    ensure_utc(workflow.completed_at) - ensure_utc(workflow.started_at)
                ).total_seconds()
                workflow_duration_seconds.observe(duration)
            incident_type = "unknown"
            if workflow.recommended_action_json:
                incident_type = workflow.recommended_action_json.get("incident_type", incident_type)
            workflow_runs_total.labels(incident_type=incident_type, status=status.value).inc()
        self._session.flush()

    def create_tool_invocation(
        self,
        *,
        workflow_id: str,
        tool_name: str,
        request: dict[str, Any] | None = None,
    ) -> ToolInvocation:
        invocation = ToolInvocation(
            workflow_id=workflow_id,
            tool_name=tool_name,
            status=ToolStatus.SUCCESS.value,
            request_json=jsonable_encoder(request) if request is not None else None,
        )
        self._session.add(invocation)
        self._session.flush()
        return invocation

    def complete_tool_invocation(
        self,
        invocation: ToolInvocation,
        *,
        status: ToolStatus,
        response: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        invocation.status = status.value
        invocation.response_json = jsonable_encoder(response) if response is not None else None
        invocation.error_message = error_message
        invocation.completed_at = utcnow()
        tool_invocations_total.labels(tool=invocation.tool_name, status=status.value).inc()
        self._session.flush()

    def create_action_execution(
        self,
        *,
        workflow_id: str,
        action_type: str,
        requires_approval: bool,
        request: dict[str, Any],
        status: ActionStatus = ActionStatus.PENDING,
        idempotency_key: str | None = None,
    ) -> ActionExecution:
        action_execution = ActionExecution(
            workflow_id=workflow_id,
            action_type=action_type,
            status=status.value,
            requires_approval=requires_approval,
            request_json=jsonable_encoder(request),
            idempotency_key=idempotency_key,
        )
        self._session.add(action_execution)
        self._session.flush()
        return action_execution

    def update_action_execution(
        self,
        action_execution: ActionExecution,
        *,
        status: ActionStatus,
        result: dict[str, Any] | None = None,
        external_reference: str | None = None,
        approval_request_id: str | None = None,
    ) -> None:
        action_execution.status = status.value
        if result is not None:
            action_execution.result_json = jsonable_encoder(result)
        if external_reference is not None:
            action_execution.external_reference = external_reference
        if approval_request_id is not None:
            action_execution.approval_request_id = approval_request_id
        self._session.flush()

    def create_approval_request(
        self,
        *,
        workflow_id: str,
        reason: str,
        requested_by: str,
        action_execution_id: int | None = None,
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            id=str(uuid4()),
            workflow_id=workflow_id,
            action_execution_id=action_execution_id,
            status=ApprovalStatus.PENDING.value,
            reason=reason,
            requested_by=requested_by,
        )
        self._session.add(approval)
        self._session.flush()
        return approval

    def resolve_approval(
        self,
        approval: ApprovalRequest,
        *,
        status: ApprovalStatus,
        decided_by: str,
        note: str | None,
    ) -> None:
        approval.status = status.value
        approval.decided_by = decided_by
        approval.decision_note = note
        approval.decided_at = utcnow()
        self._session.flush()
        wait_seconds = (ensure_utc(approval.decided_at) - ensure_utc(approval.created_at)).total_seconds()
        approval_wait_seconds.observe(wait_seconds)

    def record_retry_attempt(
        self,
        *,
        workflow_id: str,
        target_name: str,
        outcome: str,
        attempt_number: int,
        action_execution_id: int | None = None,
        tool_invocation_id: int | None = None,
        error_message: str | None = None,
    ) -> None:
        retry_attempt = RetryAttempt(
            workflow_id=workflow_id,
            action_execution_id=action_execution_id,
            tool_invocation_id=tool_invocation_id,
            target_name=target_name,
            outcome=outcome,
            error_message=error_message,
            attempt_number=attempt_number,
        )
        self._session.add(retry_attempt)
        self._session.flush()
        workflow_retries_total.labels(target=target_name, outcome=outcome).inc()

    def record_event(self, *, context: EventContext, event_type: str, payload: dict[str, Any]) -> None:
        event_record = WorkflowEvent(
            workflow_id=context.workflow_id,
            incident_id=context.incident_id,
            event_type=event_type,
            payload_json=jsonable_encoder(payload),
            correlation_id=context.correlation_id,
            trace_id=context.trace_id,
        )
        self._session.add(event_record)
        self._session.flush()
        if self._publisher is not None:
            envelope = EventEnvelope(
                event_type=event_type,
                workflow_id=context.workflow_id,
                incident_id=context.incident_id,
                correlation_id=context.correlation_id,
                trace_id=context.trace_id,
                payload=jsonable_encoder(payload),
            )
            self._publisher.publish(envelope)

    def latest_pending_approval(self, workflow_id: str) -> ApprovalRequest | None:
        statement = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.workflow_id == workflow_id,
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
            )
            .order_by(ApprovalRequest.created_at.desc())
        )
        return self._session.scalars(statement).first()

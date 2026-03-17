from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.audit import AuditTrailService, EventContext
from app.application.services.queries import OperationsQueryService
from app.domain.enums import ApprovalStatus, WorkflowStatus
from app.infrastructure.db.models import ApprovalRequest, OperationalIncident, WorkflowRun


class IncidentService:
    def __init__(
        self,
        *,
        session: Session,
        audit: AuditTrailService,
        queries: OperationsQueryService,
    ) -> None:
        self._session = session
        self._audit = audit
        self._queries = queries

    def create_incident(
        self,
        *,
        title: str,
        description: str,
        order_id: str | None,
        sku: str | None,
        sync_job_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, str]:
        incident_id = str(uuid4())
        workflow_id = str(uuid4())
        correlation_id = str(uuid4())
        trace_id = str(uuid4())

        incident = OperationalIncident(
            id=incident_id,
            title=title,
            description=description,
            order_id=order_id,
            sku=sku,
            sync_job_id=sync_job_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
            metadata_json=metadata or {},
        )
        workflow = WorkflowRun(
            id=workflow_id,
            incident_id=incident_id,
            status=WorkflowStatus.PENDING.value,
            phase="initial",
            correlation_id=correlation_id,
            trace_id=trace_id,
        )
        self._session.add(incident)
        self._session.add(workflow)
        context = EventContext(
            workflow_id=workflow_id,
            incident_id=incident_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
        )
        self._audit.record_event(
            context=context,
            event_type="incident.received",
            payload={
                "title": title,
                "order_id": order_id,
                "sku": sku,
                "sync_job_id": sync_job_id,
            },
        )
        self._audit.record_event(
            context=context,
            event_type="workflow.created",
            payload={"workflow_id": workflow_id, "status": WorkflowStatus.PENDING.value},
        )
        self._session.commit()
        return {"incident_id": incident_id, "workflow_id": workflow_id}

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        return self._queries.get_incident_details(incident_id)

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        return self._queries.get_workflow_details(workflow_id)

    def list_workflow_events(self, workflow_id: str) -> list[dict[str, Any]]:
        details = self._queries.get_workflow_details(workflow_id)
        if details is None:
            return []
        return details["events"]

    def approve_workflow(
        self,
        *,
        workflow_id: str,
        approved: bool,
        decided_by: str,
        note: str | None,
    ) -> dict[str, Any]:
        workflow = self._session.get(WorkflowRun, workflow_id)
        if workflow is None:
            raise LookupError(f"Workflow {workflow_id} not found")
        approval = self._audit.latest_pending_approval(workflow_id)
        if approval is None:
            raise LookupError(f"Workflow {workflow_id} has no pending approval")

        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        self._audit.resolve_approval(approval, status=status, decided_by=decided_by, note=note)
        if approved:
            workflow.status = WorkflowStatus.RUNNING.value
        else:
            self._audit.update_workflow_state(
                workflow,
                status=WorkflowStatus.CANCELLED,
                result={
                    "recommendation": "Operator rejected the proposed action.",
                    "approval_id": approval.id,
                },
            )
        context = EventContext(
            workflow_id=workflow.id,
            incident_id=workflow.incident_id,
            correlation_id=workflow.correlation_id,
            trace_id=workflow.trace_id,
        )
        self._audit.record_event(
            context=context,
            event_type="approval.received",
            payload={
                "approval_id": approval.id,
                "status": status.value,
                "decided_by": decided_by,
                "note": note,
            },
        )
        self._session.commit()
        return {
            "workflow_id": workflow_id,
            "approval_id": approval.id,
            "status": status.value,
        }

    def get_pending_approval(self, workflow_id: str) -> ApprovalRequest | None:
        statement = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.workflow_id == workflow_id,
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
            )
            .order_by(ApprovalRequest.created_at.desc())
        )
        return self._session.scalars(statement).first()

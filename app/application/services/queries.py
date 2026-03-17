from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.models import (
    ActionExecution,
    ApprovalRequest,
    InventorySnapshot,
    MarketplaceSyncJob,
    OperationalIncident,
    Order,
    PriceSnapshot,
    RunbookDocument,
    ToolInvocation,
    WorkflowEvent,
    WorkflowRun,
    WorkflowStep,
)


class OperationsQueryService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        order = self._session.get(Order, order_id)
        if order is None:
            return None
        return {
            "id": order.id,
            "external_order_ref": order.external_order_ref,
            "status": order.status,
            "payment_status": order.payment_status,
            "customer_email": order.customer_email,
            "total_amount": str(order.total_amount),
            "currency": order.currency,
            "marketplace": order.marketplace,
            "placed_at": order.placed_at,
            "updated_at": order.updated_at,
            "items": [
                {
                    "id": item.id,
                    "sku": item.sku,
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "margin_amount": str(item.margin_amount),
                }
                for item in order.items
            ],
        }

    def get_inventory(self, sku: str) -> list[dict[str, Any]]:
        statement = (
            select(InventorySnapshot)
            .where(InventorySnapshot.sku == sku)
            .order_by(InventorySnapshot.recorded_at.desc())
        )
        snapshots = self._session.scalars(statement).all()
        return [
            {
                "id": snapshot.id,
                "sku": snapshot.sku,
                "source": snapshot.source,
                "warehouse": snapshot.warehouse,
                "quantity": snapshot.quantity,
                "recorded_at": snapshot.recorded_at,
                "metadata": snapshot.metadata_json,
            }
            for snapshot in snapshots
        ]

    def get_pricing(self, sku: str) -> list[dict[str, Any]]:
        statement = (
            select(PriceSnapshot)
            .where(PriceSnapshot.sku == sku)
            .order_by(PriceSnapshot.recorded_at.desc())
        )
        snapshots = self._session.scalars(statement).all()
        return [
            {
                "id": snapshot.id,
                "sku": snapshot.sku,
                "source": snapshot.source,
                "price": float(snapshot.price),
                "cost": float(snapshot.cost),
                "margin_percent": float(snapshot.margin_percent),
                "recorded_at": snapshot.recorded_at,
                "metadata": snapshot.metadata_json,
            }
            for snapshot in snapshots
        ]

    def get_sync_job(self, sync_job_id: str) -> dict[str, Any] | None:
        sync_job = self._session.get(MarketplaceSyncJob, sync_job_id)
        if sync_job is None:
            return None
        return {
            "id": sync_job.id,
            "entity_type": sync_job.entity_type,
            "reference_id": sync_job.reference_id,
            "partner": sync_job.partner,
            "status": sync_job.status,
            "failure_code": sync_job.failure_code,
            "failure_message": sync_job.failure_message,
            "retryable": sync_job.retryable,
            "attempts": sync_job.attempts,
            "last_attempt_at": sync_job.last_attempt_at,
            "metadata": sync_job.metadata_json,
        }

    def get_latest_sync_job_for_reference(self, reference_id: str) -> dict[str, Any] | None:
        statement = (
            select(MarketplaceSyncJob)
            .where(MarketplaceSyncJob.reference_id == reference_id)
            .order_by(MarketplaceSyncJob.updated_at.desc())
        )
        sync_job = self._session.scalars(statement).first()
        if sync_job is None:
            return None
        return self.get_sync_job(sync_job.id)

    def get_runbooks(self) -> list[dict[str, Any]]:
        documents = self._session.scalars(select(RunbookDocument).order_by(RunbookDocument.title.asc())).all()
        return [
            {
                "id": document.id,
                "slug": document.slug,
                "title": document.title,
                "category": document.category,
                "body": document.body,
                "tags": document.tags_json or [],
                "metadata": document.metadata_json or {},
            }
            for document in documents
        ]

    def get_workflow_details(self, workflow_id: str) -> dict[str, Any] | None:
        workflow = self._session.get(WorkflowRun, workflow_id)
        if workflow is None:
            return None
        incident = self._session.get(OperationalIncident, workflow.incident_id)
        steps = self._session.scalars(
            select(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id).order_by(WorkflowStep.id.asc())
        ).all()
        events = self._session.scalars(
            select(WorkflowEvent).where(WorkflowEvent.workflow_id == workflow_id).order_by(WorkflowEvent.id.asc())
        ).all()
        tools = self._session.scalars(
            select(ToolInvocation).where(ToolInvocation.workflow_id == workflow_id).order_by(ToolInvocation.id.asc())
        ).all()
        actions = self._session.scalars(
            select(ActionExecution).where(ActionExecution.workflow_id == workflow_id).order_by(ActionExecution.id.asc())
        ).all()
        approvals = self._session.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.workflow_id == workflow_id)
            .order_by(ApprovalRequest.created_at.asc())
        ).all()
        return jsonable_encoder(
            {
                "workflow": workflow,
                "incident": incident,
                "steps": steps,
                "events": events,
                "tool_invocations": tools,
                "action_executions": actions,
                "approval_requests": approvals,
            }
        )

    def get_incident_details(self, incident_id: str) -> dict[str, Any] | None:
        incident = self._session.get(OperationalIncident, incident_id)
        if incident is None:
            return None
        workflow = self._session.scalars(
            select(WorkflowRun).where(WorkflowRun.incident_id == incident_id).order_by(WorkflowRun.created_at.desc())
        ).first()
        return jsonable_encoder({"incident": incident, "workflow": workflow})


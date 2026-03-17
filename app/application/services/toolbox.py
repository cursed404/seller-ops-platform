from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session
from tenacity import RetryError, Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.application.services.audit import AuditTrailService
from app.application.services.queries import OperationsQueryService
from app.domain.enums import ActionStatus, ActionType, ToolStatus, WorkflowStatus
from app.infrastructure.db.models import ActionExecution, MarketplaceSyncJob
from app.infrastructure.observability.metrics import workflow_errors_total
from app.infrastructure.redis.idempotency import IdempotencyStore
from app.infrastructure.tools.marketplace import MarketplaceGateway, TransientToolError
from app.infrastructure.tools.ticketing import TicketGateway


def utcnow() -> datetime:
    return datetime.now(UTC)


class Toolbox:
    def __init__(
        self,
        *,
        session: Session,
        query_service: OperationsQueryService,
        audit: AuditTrailService,
        marketplace_gateway: MarketplaceGateway,
        ticket_gateway: TicketGateway,
        idempotency_store: IdempotencyStore,
    ) -> None:
        self._session = session
        self._query_service = query_service
        self._audit = audit
        self._marketplace_gateway = marketplace_gateway
        self._ticket_gateway = ticket_gateway
        self._idempotency_store = idempotency_store

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "order_lookup", "description": "Поднимает данные по заказу и его позициям."},
            {"name": "inventory_comparison", "description": "Сравнивает внутренний и внешний остаток."},
            {"name": "price_policy_evaluation", "description": "Проверяет цену, маржу и риск аномалии."},
            {"name": "sync_job_inspection", "description": "Читает состояние последней синхронизации."},
            {"name": "ticket_creation", "description": "Создает тикет для эскалации в моковой системе."},
            {
                "name": "reconciliation_request",
                "description": "Отправляет моковый запрос на сверку остатков.",
            },
            {"name": "repricing_request", "description": "Отправляет моковый запрос на изменение цены."},
            {"name": "sync_retry", "description": "Повторяет временно упавшую синхронизацию."},
        ]

    def order_lookup(self, *, workflow_id: str, order_id: str) -> dict[str, Any]:
        invocation = self._audit.create_tool_invocation(
            workflow_id=workflow_id,
            tool_name="order_lookup",
            request={"order_id": order_id},
        )
        order = self._query_service.get_order(order_id)
        if order is None:
            self._audit.complete_tool_invocation(
                invocation,
                status=ToolStatus.FAILED,
                error_message=f"Заказ {order_id} не найден",
            )
            raise LookupError(f"Заказ {order_id} не найден")
        self._audit.complete_tool_invocation(invocation, status=ToolStatus.SUCCESS, response=order)
        return order

    def inventory_comparison(self, *, workflow_id: str, sku: str) -> dict[str, Any]:
        invocation = self._audit.create_tool_invocation(
            workflow_id=workflow_id,
            tool_name="inventory_comparison",
            request={"sku": sku},
        )
        snapshots = self._query_service.get_inventory(sku)
        internal = next((entry for entry in snapshots if entry["source"] == "internal"), None)
        marketplace = next((entry for entry in snapshots if entry["source"] == "marketplace"), None)
        if internal is None or marketplace is None:
            self._audit.complete_tool_invocation(
                invocation,
                status=ToolStatus.FAILED,
                error_message=f"Недостаточно данных по остаткам для {sku}",
            )
            raise LookupError(f"Недостаточно данных по остаткам для {sku}")
        response = {
            "sku": sku,
            "internal_quantity": internal["quantity"],
            "marketplace_quantity": marketplace["quantity"],
            "difference": internal["quantity"] - marketplace["quantity"],
            "recorded_at": max(internal["recorded_at"], marketplace["recorded_at"]),
        }
        self._audit.complete_tool_invocation(invocation, status=ToolStatus.SUCCESS, response=response)
        return response

    def price_policy_evaluation(self, *, workflow_id: str, sku: str) -> dict[str, Any]:
        invocation = self._audit.create_tool_invocation(
            workflow_id=workflow_id,
            tool_name="price_policy_evaluation",
            request={"sku": sku},
        )
        snapshots = self._query_service.get_pricing(sku)
        if len(snapshots) < 2:
            self._audit.complete_tool_invocation(
                invocation,
                status=ToolStatus.FAILED,
                error_message=f"Недостаточно данных по истории цен для {sku}",
            )
            raise LookupError(f"Недостаточно данных по истории цен для {sku}")
        latest = snapshots[0]
        previous = snapshots[1]
        price_drop_percent = round(((previous["price"] - latest["price"]) / previous["price"]) * 100, 2)
        recommended_price = round(max(latest["cost"] * 1.2, latest["price"]), 2)
        response = {
            "sku": sku,
            "latest_price": latest["price"],
            "previous_price": previous["price"],
            "margin_percent": latest["margin_percent"],
            "price_drop_percent": price_drop_percent,
            "recommended_price": recommended_price,
            "policy_breach": latest["margin_percent"] < 12 or price_drop_percent > 20,
        }
        self._audit.complete_tool_invocation(invocation, status=ToolStatus.SUCCESS, response=response)
        return response

    def sync_job_inspection(
        self,
        *,
        workflow_id: str,
        sync_job_id: str | None = None,
        reference_id: str | None = None,
    ) -> dict[str, Any]:
        invocation = self._audit.create_tool_invocation(
            workflow_id=workflow_id,
            tool_name="sync_job_inspection",
            request={"sync_job_id": sync_job_id, "reference_id": reference_id},
        )
        sync_job = None
        if sync_job_id:
            sync_job = self._query_service.get_sync_job(sync_job_id)
        elif reference_id:
            sync_job = self._query_service.get_latest_sync_job_for_reference(reference_id)
        if sync_job is None:
            self._audit.complete_tool_invocation(
                invocation,
                status=ToolStatus.FAILED,
                error_message="Sync job не найдена",
            )
            raise LookupError("Sync job не найдена")
        self._audit.complete_tool_invocation(invocation, status=ToolStatus.SUCCESS, response=sync_job)
        return sync_job

    def execute_action(
        self,
        *,
        workflow_id: str,
        action: dict[str, Any],
        action_execution: ActionExecution,
    ) -> dict[str, Any]:
        action_type = action["action_type"]
        if action_type == ActionType.RETRY_SYNC.value:
            return self._retry_sync(workflow_id=workflow_id, action=action, action_execution=action_execution)
        if action_type == ActionType.REQUEST_RECONCILIATION.value:
            return self._request_reconciliation(
                workflow_id=workflow_id, action=action, action_execution=action_execution
            )
        if action_type == ActionType.REQUEST_REPRICING.value:
            return self._request_repricing(
                workflow_id=workflow_id, action=action, action_execution=action_execution
            )
        if action_type == ActionType.CREATE_TICKET.value:
            return self._create_ticket(workflow_id=workflow_id, action=action, action_execution=action_execution)
        return {"status": "failed", "summary": f"Неподдерживаемый тип действия: {action_type}"}

    def _retry_sync(
        self,
        *,
        workflow_id: str,
        action: dict[str, Any],
        action_execution: ActionExecution,
    ) -> dict[str, Any]:
        sync_job_id = action["parameters"].get("sync_job_id")
        if not sync_job_id:
            raise ValueError("Для retry_sync нужен sync_job_id")
        sync_job = self._session.get(MarketplaceSyncJob, sync_job_id)
        if sync_job is None:
            raise LookupError(f"Sync job {sync_job_id} не найдена")

        invocation = self._audit.create_tool_invocation(
            workflow_id=workflow_id,
            tool_name="sync_retry",
            request={"sync_job_id": sync_job_id},
        )
        try:
            retrying = Retrying(
                stop=stop_after_attempt(3),
                wait=wait_fixed(1),
                retry=retry_if_exception_type(TransientToolError),
                reraise=False,
            )
            for attempt in retrying:
                with attempt:
                    attempt_number = attempt.retry_state.attempt_number
                    try:
                        if attempt_number > 1:
                            sync_job.status = WorkflowStatus.RETRYING.value
                        result = self._marketplace_gateway.retry_sync_job(
                            sync_job_id=sync_job_id,
                            current_attempts=sync_job.attempts,
                            failure_code=sync_job.failure_code,
                        )
                    except TransientToolError as exc:
                        sync_job.attempts += 1
                        sync_job.status = WorkflowStatus.RETRYING.value
                        sync_job.last_attempt_at = utcnow()
                        self._audit.record_retry_attempt(
                            workflow_id=workflow_id,
                            target_name="sync_retry",
                            outcome="retryable_failure",
                            attempt_number=attempt_number,
                            action_execution_id=action_execution.id,
                            tool_invocation_id=invocation.id,
                            error_message=str(exc),
                        )
                        self._session.flush()
                        raise
                    sync_job.attempts += 1
                    sync_job.status = "completed"
                    sync_job.failure_code = None
                    sync_job.failure_message = None
                    sync_job.last_attempt_at = utcnow()
                    self._audit.record_retry_attempt(
                        workflow_id=workflow_id,
                        target_name="sync_retry",
                        outcome="success",
                        attempt_number=attempt_number,
                        action_execution_id=action_execution.id,
                        tool_invocation_id=invocation.id,
                    )
                    self._audit.complete_tool_invocation(
                        invocation,
                        status=ToolStatus.SUCCESS,
                        response=result,
                    )
                    self._audit.update_action_execution(
                        action_execution,
                        status=ActionStatus.EXECUTED,
                        result=result,
                        external_reference=result["external_reference"],
                    )
                    self._session.flush()
                    return result
        except RetryError as exc:
            workflow_errors_total.labels(step="execute_action", error_type="RetryError").inc()
            final_exception = exc.last_attempt.exception()
            message = str(final_exception) if final_exception else "Лимит повторных попыток исчерпан"
            self._audit.complete_tool_invocation(
                invocation,
                status=ToolStatus.FAILED,
                error_message=message,
            )
            self._audit.update_action_execution(action_execution, status=ActionStatus.FAILED, result={"error": message})
            return {"status": "failed", "summary": message}
        return {"status": "failed", "summary": "Повторные попытки завершились без финального результата"}

    def _request_reconciliation(
        self,
        *,
        workflow_id: str,
        action: dict[str, Any],
        action_execution: ActionExecution,
    ) -> dict[str, Any]:
        sku = action["parameters"]["sku"]
        difference = int(action["parameters"]["difference"])
        idempotency_key = action_execution.idempotency_key or f"reconciliation:{workflow_id}:{sku}"
        invocation = self._audit.create_tool_invocation(
            workflow_id=workflow_id,
            tool_name="reconciliation_request",
            request={"sku": sku, "difference": difference, "idempotency_key": idempotency_key},
        )
        if not self._idempotency_store.acquire(idempotency_key):
            result = {
                "status": "success",
                "summary": "Запрос на сверку уже был отправлен для этого workflow.",
                "request_id": action_execution.external_reference or f"reconcile-{sku}",
                "idempotent": True,
            }
            self._audit.complete_tool_invocation(invocation, status=ToolStatus.SUCCESS, response=result)
            self._audit.update_action_execution(
                action_execution,
                status=ActionStatus.EXECUTED,
                result=result,
                external_reference=result["request_id"],
            )
            return result
        result = self._marketplace_gateway.request_reconciliation(sku=sku, difference=difference)
        self._audit.complete_tool_invocation(invocation, status=ToolStatus.SUCCESS, response=result)
        self._audit.update_action_execution(
            action_execution,
            status=ActionStatus.EXECUTED,
            result=result,
            external_reference=str(result["request_id"]),
        )
        return result

    def _request_repricing(
        self,
        *,
        workflow_id: str,
        action: dict[str, Any],
        action_execution: ActionExecution,
    ) -> dict[str, Any]:
        sku = action["parameters"]["sku"]
        recommended_price = float(action["parameters"]["recommended_price"])
        idempotency_key = action_execution.idempotency_key or f"repricing:{workflow_id}:{sku}"
        invocation = self._audit.create_tool_invocation(
            workflow_id=workflow_id,
            tool_name="repricing_request",
            request={"sku": sku, "recommended_price": recommended_price, "idempotency_key": idempotency_key},
        )
        if not self._idempotency_store.acquire(idempotency_key):
            result = {
                "status": "success",
                "summary": "Запрос на изменение цены уже был отправлен для этого workflow.",
                "request_id": action_execution.external_reference or f"reprice-{sku}",
                "idempotent": True,
            }
            self._audit.complete_tool_invocation(invocation, status=ToolStatus.SUCCESS, response=result)
            self._audit.update_action_execution(
                action_execution,
                status=ActionStatus.EXECUTED,
                result=result,
                external_reference=result["request_id"],
            )
            return result
        result = self._marketplace_gateway.request_repricing(sku=sku, price=recommended_price)
        self._audit.complete_tool_invocation(invocation, status=ToolStatus.SUCCESS, response=result)
        self._audit.update_action_execution(
            action_execution,
            status=ActionStatus.EXECUTED,
            result=result,
            external_reference=str(result["request_id"]),
        )
        return result

    def _create_ticket(
        self,
        *,
        workflow_id: str,
        action: dict[str, Any],
        action_execution: ActionExecution,
    ) -> dict[str, Any]:
        reference = action["parameters"].get("reference") or action.get("target_reference") or workflow_id
        invocation = self._audit.create_tool_invocation(
            workflow_id=workflow_id,
            tool_name="ticket_creation",
            request={"reference": reference},
        )
        result = self._ticket_gateway.create_ticket(reference=reference, summary=action["summary"])
        self._audit.complete_tool_invocation(invocation, status=ToolStatus.SUCCESS, response=result)
        self._audit.update_action_execution(
            action_execution,
            status=ActionStatus.EXECUTED,
            result=result,
            external_reference=str(result["ticket_id"]),
        )
        return result

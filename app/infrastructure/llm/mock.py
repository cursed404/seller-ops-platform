from __future__ import annotations

from typing import Any

from app.domain.enums import ActionType, IncidentType, Severity, WorkflowStatus
from app.domain.schemas import IncidentClassification, ProposedAction, VerificationResult
from app.infrastructure.llm.base import ChatModel


class MockChatModel(ChatModel):
    def classify_incident(
        self,
        *,
        title: str,
        description: str,
        metadata: dict[str, Any] | None,
    ) -> IncidentClassification:
        text = f"{title} {description}".lower()
        metadata = metadata or {}

        def contains_any(haystack: str, needles: list[str]) -> bool:
            return any(needle in haystack for needle in needles)

        if contains_any(
            text,
            [
                "processing",
                "order stuck",
                "завис",
                "обработк",
                "подтверждения оплаты",
            ],
        ) or metadata.get("order_id"):
            incident_type = IncidentType.ORDER_PROCESSING_DELAY
            severity = Severity.HIGH if "45" in text or "hour" in text else Severity.MEDIUM
        elif contains_any(
            text,
            [
                "inventory",
                "stock",
                "остат",
                "расхожд",
                "сверк",
            ],
        ):
            incident_type = IncidentType.INVENTORY_MISMATCH
            severity = Severity.HIGH
        elif contains_any(
            text,
            [
                "margin",
                "price",
                "цена",
                "маржа",
            ],
        ):
            incident_type = IncidentType.PRICE_ANOMALY
            severity = Severity.HIGH
        elif contains_any(
            text,
            [
                "sync",
                "timeout",
                "синхрон",
                "таймаут",
            ],
        ):
            incident_type = IncidentType.SYNC_FAILURE
            severity = Severity.MEDIUM
        elif contains_any(text, ["delivery", "достав"]):
            incident_type = IncidentType.DELIVERY_INCONSISTENCY
            severity = Severity.MEDIUM
        elif contains_any(text, ["catalog", "каталог"]):
            incident_type = IncidentType.CATALOG_CONFLICT
            severity = Severity.MEDIUM
        else:
            incident_type = IncidentType.UNKNOWN
            severity = Severity.MEDIUM

        return IncidentClassification(
            incident_type=incident_type,
            severity=severity,
            summary=f"Инцидент отнесен к типу {incident_type.value} с уровнем {severity.value}.",
            rationale="Локальный классификатор определил тип инцидента по формулировке и контексту.",
        )

    def plan_action(
        self,
        *,
        incident_type: str,
        severity: str,
        context_summary: dict[str, Any],
        runbooks: list[dict[str, Any]],
    ) -> ProposedAction:
        citations = [entry["citation"] for entry in runbooks if "citation" in entry]
        if incident_type == IncidentType.ORDER_PROCESSING_DELAY.value:
            action_type = ActionType.RETRY_SYNC
            summary = "Нужно повторить последнюю синхронизацию по заказу перед эскалацией."
            requires_approval = False
            target = context_summary.get("sync_job_id") or context_summary.get("order_id")
            parameters = {"sync_job_id": context_summary.get("sync_job_id")}
        elif incident_type == IncidentType.INVENTORY_MISMATCH.value:
            action_type = ActionType.REQUEST_RECONCILIATION
            summary = "Нужно отправить запрос на сверку, чтобы выровнять внешний и внутренний остаток."
            requires_approval = True
            target = context_summary.get("sku")
            parameters = {
                "sku": context_summary.get("sku"),
                "difference": context_summary.get("difference"),
            }
        elif incident_type == IncidentType.PRICE_ANOMALY.value:
            action_type = ActionType.REQUEST_REPRICING
            summary = "Нужно подготовить запрос на изменение цены, чтобы вернуть маржу в допустимую зону."
            requires_approval = True
            target = context_summary.get("sku")
            parameters = {
                "sku": context_summary.get("sku"),
                "recommended_price": context_summary.get("recommended_price"),
            }
        elif incident_type == IncidentType.SYNC_FAILURE.value:
            action_type = ActionType.RETRY_SYNC
            summary = "Нужно повторить временно упавшую синхронизацию с ограничением по попыткам."
            requires_approval = False
            target = context_summary.get("sync_job_id")
            parameters = {"sync_job_id": context_summary.get("sync_job_id")}
        else:
            action_type = ActionType.CREATE_TICKET
            summary = "Нужно передать инцидент в операционную команду через тикет."
            requires_approval = True
            target = context_summary.get("order_id") or context_summary.get("sku")
            parameters = {"reference": target}

        return ProposedAction(
            action_type=action_type,
            summary=summary,
            rationale="Локальная модель выбрала действие на основе типа инцидента и найденных регламентов.",
            requires_approval=requires_approval,
            risk_level=Severity(severity),
            target_reference=target,
            parameters=parameters,
            citations=citations,
        )

    def verify_execution(
        self,
        *,
        incident_type: str,
        action: dict[str, Any],
        execution_result: dict[str, Any],
    ) -> VerificationResult:
        if execution_result.get("status") == "success":
            summary = f"Действие {action['action_type']} успешно выполнено для инцидента {incident_type}."
            status = WorkflowStatus.COMPLETED
            completed = True
            follow_up = []
        elif execution_result.get("status") == "waiting_for_approval":
            summary = "Workflow поставлен на паузу и ждет подтверждение."
            status = WorkflowStatus.WAITING_FOR_APPROVAL
            completed = False
            follow_up = ["Нужно подтвердить или отклонить предложенное действие."]
        else:
            summary = execution_result.get("summary", "Выполнение завершилось ошибкой и требует ручной проверки.")
            status = WorkflowStatus.FAILED
            completed = False
            follow_up = ["Нужно посмотреть события workflow и историю повторных попыток."]

        return VerificationResult(
            workflow_status=status,
            summary=summary,
            completed=completed,
            follow_up_actions=follow_up,
        )

from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.audit import AuditTrailService, EventContext
from app.application.services.incidents import IncidentService
from app.application.services.knowledge_base import KnowledgeBaseService
from app.application.services.queries import OperationsQueryService
from app.application.services.toolbox import Toolbox
from app.application.workflows.state import WorkflowState
from app.domain.enums import ActionStatus, ApprovalStatus, WorkflowStatus
from app.infrastructure.db.models import ActionExecution, OperationalIncident, WorkflowRun
from app.infrastructure.llm.base import ChatModel


class WorkflowEngine:
    def __init__(
        self,
        *,
        session: Session,
        audit: AuditTrailService,
        incidents: IncidentService,
        queries: OperationsQueryService,
        toolbox: Toolbox,
        chat_model: ChatModel,
    ) -> None:
        self._session = session
        self._audit = audit
        self._incidents = incidents
        self._queries = queries
        self._toolbox = toolbox
        self._chat_model = chat_model

        self._initial_graph = self._build_initial_graph()
        self._resume_graph = self._build_resume_graph()

    def run_initial(self, workflow_id: str) -> None:
        workflow = self._session.get(WorkflowRun, workflow_id)
        if workflow is None:
            raise LookupError(f"Workflow {workflow_id} not found")
        incident_details = self._incidents.get_incident(workflow.incident_id)
        if incident_details is None:
            raise LookupError(f"Incident {workflow.incident_id} not found")
        self._audit.mark_workflow_running(workflow, phase="initial")
        self._audit.record_event(
            context=self._context(workflow),
            event_type="workflow.started",
            payload={"workflow_id": workflow.id},
        )
        self._session.commit()
        state: WorkflowState = {
            "workflow_id": workflow.id,
            "incident_id": workflow.incident_id,
            "incident": incident_details["incident"],
        }
        try:
            self._initial_graph.invoke(state)
            self._session.commit()
        except Exception as exc:
            self._fail_workflow(workflow, step_name="initial_graph", error=exc)
            raise

    def run_resume(self, workflow_id: str) -> None:
        workflow = self._session.get(WorkflowRun, workflow_id)
        if workflow is None:
            raise LookupError(f"Workflow {workflow_id} not found")
        approval = self._incidents.get_pending_approval(workflow_id)
        if approval is not None:
            raise RuntimeError("Cannot resume workflow while approval is still pending")
        if workflow.status == WorkflowStatus.CANCELLED.value:
            return
        incident_details = self._incidents.get_incident(workflow.incident_id)
        if incident_details is None:
            raise LookupError(f"Incident {workflow.incident_id} not found")
        incident_record = self._session.get(OperationalIncident, workflow.incident_id)
        if incident_record is None:
            raise LookupError(f"Incident {workflow.incident_id} not found")
        recommended_action = workflow.recommended_action_json or {}
        incident_type = incident_record.incident_type or recommended_action.get("incident_type")
        if incident_type is None:
            raise LookupError(f"Workflow {workflow_id} has no incident type to resume with")
        state: WorkflowState = {
            "workflow_id": workflow.id,
            "incident_id": workflow.incident_id,
            "incident": incident_details["incident"],
            "classification": {
                "incident_type": incident_type,
                "severity": incident_record.severity or "medium",
            },
            "context_summary": workflow.context_summary_json or {},
            "action": recommended_action,
        }
        self._audit.mark_workflow_running(workflow, phase="resumed")
        try:
            self._resume_graph.invoke(state)
            self._session.commit()
        except Exception as exc:
            self._fail_workflow(workflow, step_name="resume_graph", error=exc)
            raise

    def _build_initial_graph(self) -> Any:
        graph = StateGraph(WorkflowState)
        graph.add_node("classify_incident", self._classify_incident)
        graph.add_node("collect_context", self._collect_context)
        graph.add_node("select_runbook", self._select_runbook)
        graph.add_node("evaluate_risk", self._evaluate_risk)
        graph.add_node("await_approval", self._await_approval)
        graph.add_node("execute_action", self._execute_action)
        graph.add_node("verify_result", self._verify_result)
        graph.set_entry_point("classify_incident")
        graph.add_edge("classify_incident", "collect_context")
        graph.add_edge("collect_context", "select_runbook")
        graph.add_edge("select_runbook", "evaluate_risk")
        graph.add_conditional_edges(
            "evaluate_risk",
            self._risk_route,
            {
                "await_approval": "await_approval",
                "execute_action": "execute_action",
            },
        )
        graph.add_edge("execute_action", "verify_result")
        graph.add_edge("await_approval", END)
        graph.add_edge("verify_result", END)
        return graph.compile()

    def _build_resume_graph(self) -> Any:
        graph = StateGraph(WorkflowState)
        graph.add_node("execute_action", self._execute_action)
        graph.add_node("verify_result", self._verify_result)
        graph.set_entry_point("execute_action")
        graph.add_edge("execute_action", "verify_result")
        graph.add_edge("verify_result", END)
        return graph.compile()

    def _classify_incident(self, state: WorkflowState) -> WorkflowState:
        workflow = self._session.get(WorkflowRun, state["workflow_id"])
        incident = state["incident"]
        step = self._audit.start_step(workflow_id=workflow.id, step_name="classify_incident")
        try:
            classification = self._chat_model.classify_incident(
                title=incident["title"],
                description=incident["description"],
                metadata=incident.get("metadata_json") or incident.get("metadata") or {},
            )
            operational_incident = self._session.get(OperationalIncident, workflow.incident_id)
            if operational_incident is None:
                raise LookupError(f"Incident {workflow.incident_id} not found")
            self._audit.update_incident_classification(
                incident=operational_incident,
                incident_type=classification.incident_type.value,
                severity=classification.severity.value,
            )
            self._audit.complete_step(step, output=classification.model_dump(mode="json"))
            self._audit.record_event(
                context=self._context(workflow),
                event_type="incident.classified",
                payload=classification.model_dump(mode="json"),
            )
            self._session.commit()
            return {"classification": classification.model_dump(mode="json")}
        except Exception as exc:
            self._audit.fail_step(step, error=exc)
            self._session.commit()
            raise

    def _collect_context(self, state: WorkflowState) -> WorkflowState:
        workflow = self._session.get(WorkflowRun, state["workflow_id"])
        incident = state["incident"]
        incident_type = state["classification"]["incident_type"]
        step = self._audit.start_step(workflow_id=workflow.id, step_name="collect_context")
        try:
            summary: dict[str, Any] = {"incident_type": incident_type}
            details: dict[str, Any] = {}
            risk_signals: list[str] = []

            if incident.get("order_id"):
                order_context = self._toolbox.order_lookup(workflow_id=workflow.id, order_id=incident["order_id"])
                details["order"] = order_context
                summary["order_id"] = incident["order_id"]
            if incident.get("sku") and incident_type == "inventory_mismatch":
                inventory_context = self._toolbox.inventory_comparison(
                    workflow_id=workflow.id,
                    sku=incident["sku"],
                )
                details["inventory"] = inventory_context
                summary["sku"] = incident["sku"]
                summary["difference"] = inventory_context["difference"]
                risk_signals.append(f"Inventory difference is {inventory_context['difference']} units.")
            if incident.get("sku") and incident_type == "price_anomaly":
                pricing_context = self._toolbox.price_policy_evaluation(
                    workflow_id=workflow.id,
                    sku=incident["sku"],
                )
                details["pricing"] = pricing_context
                summary["sku"] = incident["sku"]
                summary["recommended_price"] = pricing_context["recommended_price"]
                risk_signals.append(
                    f"Price dropped {pricing_context['price_drop_percent']} percent with "
                    f"{pricing_context['margin_percent']} percent margin."
                )

            sync_reference = incident.get("sync_job_id") or incident.get("order_id") or incident.get("sku")
            if sync_reference:
                sync_context = self._toolbox.sync_job_inspection(
                    workflow_id=workflow.id,
                    sync_job_id=incident.get("sync_job_id"),
                    reference_id=None if incident.get("sync_job_id") else sync_reference,
                )
                details["sync"] = sync_context
                summary["sync_job_id"] = sync_context["id"]
                if sync_context["retryable"]:
                    risk_signals.append("Latest marketplace sync failure is retryable.")

            context_summary = {
                "headline": f"Collected operational context for {incident_type}",
                "details": details,
                "risk_signals": risk_signals,
                **summary,
            }
            self._audit.update_workflow_state(
                workflow,
                status=WorkflowStatus.RUNNING,
                context_summary=context_summary,
            )
            self._audit.complete_step(step, output=context_summary)
            self._audit.record_event(
                context=self._context(workflow),
                event_type="context.collected",
                payload=context_summary,
            )
            self._session.commit()
            return {"context_summary": jsonable_encoder(context_summary)}
        except Exception as exc:
            self._audit.fail_step(step, error=exc)
            self._session.commit()
            raise

    def _select_runbook(self, state: WorkflowState) -> WorkflowState:
        workflow = self._session.get(WorkflowRun, state["workflow_id"])
        step = self._audit.start_step(workflow_id=workflow.id, step_name="select_runbook")
        try:
            knowledge = KnowledgeBaseService(self._queries.get_runbooks())
            runbooks = knowledge.search(
                incident_type=state["classification"]["incident_type"],
                query_text=state["incident"]["description"],
            )
            plan = self._chat_model.plan_action(
                incident_type=state["classification"]["incident_type"],
                severity=state["classification"]["severity"],
                context_summary=state["context_summary"],
                runbooks=runbooks,
            )
            recommendation = plan.model_dump(mode="json")
            recommendation["incident_type"] = state["classification"]["incident_type"]
            selected_runbook_id = plan.citations[0].document_id if plan.citations else None
            self._audit.update_workflow_state(
                workflow,
                status=WorkflowStatus.RUNNING,
                recommended_action=recommendation,
                citations=[citation.model_dump(mode="json") for citation in plan.citations],
                selected_runbook_id=selected_runbook_id,
            )
            self._audit.complete_step(
                step,
                output={"runbooks": runbooks, "recommended_action": recommendation},
            )
            self._audit.record_event(
                context=self._context(workflow),
                event_type="runbook.selected",
                payload={
                    "selected_runbook_id": selected_runbook_id,
                    "citations": [citation.model_dump(mode="json") for citation in plan.citations],
                },
            )
            self._audit.record_event(
                context=self._context(workflow),
                event_type="action.requested",
                payload=recommendation,
            )
            self._session.commit()
            return {
                "runbooks": runbooks,
                "action": recommendation,
            }
        except Exception as exc:
            self._audit.fail_step(step, error=exc)
            self._session.commit()
            raise

    def _evaluate_risk(self, state: WorkflowState) -> WorkflowState:
        workflow = self._session.get(WorkflowRun, state["workflow_id"])
        step = self._audit.start_step(workflow_id=workflow.id, step_name="evaluate_risk")
        try:
            action = state["action"]
            requires_approval = bool(action["requires_approval"])
            action_execution = self._audit.create_action_execution(
                workflow_id=workflow.id,
                action_type=action["action_type"],
                requires_approval=requires_approval,
                request=action,
                idempotency_key=f"{action['action_type']}:{workflow.id}:{action.get('target_reference')}",
            )
            approval_payload = {
                "requires_approval": requires_approval,
                "action_execution_id": action_execution.id,
            }
            if requires_approval:
                approval = self._audit.create_approval_request(
                    workflow_id=workflow.id,
                    reason=action["summary"],
                    requested_by="workflow_engine",
                    action_execution_id=action_execution.id,
                )
                self._audit.update_action_execution(
                    action_execution,
                    status=ActionStatus.PENDING,
                    approval_request_id=approval.id,
                )
                self._audit.update_workflow_state(
                    workflow,
                    status=WorkflowStatus.WAITING_FOR_APPROVAL,
                )
                approval_payload["approval_id"] = approval.id
                approval_payload["approval_status"] = ApprovalStatus.PENDING.value
                self._audit.record_event(
                    context=self._context(workflow),
                    event_type="approval.required",
                    payload=approval_payload,
                )
            self._audit.complete_step(step, output=approval_payload)
            self._session.commit()
            return {"approval": approval_payload}
        except Exception as exc:
            self._audit.fail_step(step, error=exc)
            self._session.commit()
            raise

    def _await_approval(self, state: WorkflowState) -> WorkflowState:
        workflow = self._session.get(WorkflowRun, state["workflow_id"])
        step = self._audit.start_step(workflow_id=workflow.id, step_name="await_approval")
        self._audit.complete_step(
            step,
            output={"status": WorkflowStatus.WAITING_FOR_APPROVAL.value},
        )
        self._session.commit()
        return {
            "execution_result": {
                "status": "waiting_for_approval",
                "summary": "Workflow is paused until an approval decision is received.",
            }
        }

    def _execute_action(self, state: WorkflowState) -> WorkflowState:
        workflow = self._session.get(WorkflowRun, state["workflow_id"])
        step = self._audit.start_step(workflow_id=workflow.id, step_name="execute_action")
        try:
            action_record = self._session.scalars(
                select(ActionExecution)
                .where(ActionExecution.workflow_id == workflow.id)
                .order_by(ActionExecution.id.desc())
            ).first()
            if action_record is None:
                action_record = self._audit.create_action_execution(
                    workflow_id=workflow.id,
                    action_type=state["action"]["action_type"],
                    requires_approval=bool(state["action"]["requires_approval"]),
                    request=state["action"],
                    idempotency_key=f"{state['action']['action_type']}:{workflow.id}",
                )
            result = self._toolbox.execute_action(
                workflow_id=workflow.id,
                action=state["action"],
                action_execution=action_record,
            )
            self._audit.complete_step(step, output=result)
            self._audit.record_event(
                context=self._context(workflow),
                event_type="action.executed",
                payload=result,
            )
            self._session.commit()
            return {"execution_result": result}
        except Exception as exc:
            self._audit.fail_step(step, error=exc)
            self._session.commit()
            raise

    def _verify_result(self, state: WorkflowState) -> WorkflowState:
        workflow = self._session.get(WorkflowRun, state["workflow_id"])
        step = self._audit.start_step(workflow_id=workflow.id, step_name="verify_result")
        try:
            recommended_action = workflow.recommended_action_json or {}
            incident_type = (
                state["classification"]["incident_type"]
                if state.get("classification")
                else recommended_action.get("incident_type")
            )
            if incident_type is None:
                raise LookupError(f"Workflow {workflow.id} has no incident type for verification")
            verification = self._chat_model.verify_execution(
                incident_type=incident_type,
                action=state["action"],
                execution_result=state["execution_result"],
            )
            final_result = {
                "recommendation": state["action"]["summary"],
                "verification": verification.model_dump(mode="json"),
                "classification": state.get("classification")
                or (workflow.result_summary_json or {}).get("classification"),
                "execution_result": state["execution_result"],
            }
            final_status = WorkflowStatus(verification.workflow_status)
            self._audit.update_workflow_state(
                workflow,
                status=final_status,
                result=final_result,
            )
            event_type = "workflow.completed" if final_status == WorkflowStatus.COMPLETED else "workflow.failed"
            self._audit.complete_step(step, output=final_result)
            self._audit.record_event(
                context=self._context(workflow),
                event_type=event_type,
                payload=final_result,
            )
            self._session.commit()
            return {"final_result": final_result}
        except Exception as exc:
            self._audit.fail_step(step, error=exc)
            self._session.commit()
            raise

    def _risk_route(self, state: WorkflowState) -> str:
        if state["approval"]["requires_approval"]:
            return "await_approval"
        return "execute_action"

    def _context(self, workflow: WorkflowRun) -> EventContext:
        return EventContext(
            workflow_id=workflow.id,
            incident_id=workflow.incident_id,
            correlation_id=workflow.correlation_id,
            trace_id=workflow.trace_id,
        )

    def _fail_workflow(self, workflow: WorkflowRun, *, step_name: str, error: Exception) -> None:
        self._audit.update_workflow_state(
            workflow,
            status=WorkflowStatus.FAILED,
            error={"step": step_name, "message": str(error), "type": type(error).__name__},
        )
        self._audit.record_event(
            context=self._context(workflow),
            event_type="workflow.failed",
            payload={"step": step_name, "message": str(error), "type": type(error).__name__},
        )
        self._session.commit()

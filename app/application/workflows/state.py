from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    workflow_id: str
    incident_id: str
    incident: dict[str, Any]
    classification: dict[str, Any]
    context_summary: dict[str, Any]
    runbooks: list[dict[str, Any]]
    action: dict[str, Any]
    approval: dict[str, Any]
    execution_result: dict[str, Any]
    final_result: dict[str, Any]


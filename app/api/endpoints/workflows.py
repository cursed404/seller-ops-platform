from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import ApprovalRequestBody
from app.dependencies import build_incident_service
from app.infrastructure.db.session import get_session

router = APIRouter(tags=["workflows"])


@router.get("/workflows/{workflow_id}")
def get_workflow(
    workflow_id: str,
    session: Session = Depends(get_session),
) -> dict:
    service = build_incident_service(session)
    workflow = service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.get("/workflows/{workflow_id}/events")
def list_workflow_events(
    workflow_id: str,
    session: Session = Depends(get_session),
) -> list[dict]:
    service = build_incident_service(session)
    workflow = service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow["events"]


@router.post("/workflows/{workflow_id}/approve")
def approve_workflow(
    workflow_id: str,
    payload: ApprovalRequestBody,
    session: Session = Depends(get_session),
) -> dict:
    service = build_incident_service(session)
    try:
        return service.approve_workflow(
            workflow_id=workflow_id,
            approved=payload.approved,
            decided_by=payload.decided_by,
            note=payload.note,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


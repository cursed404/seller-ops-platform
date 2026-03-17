from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import IncidentCreateRequest, IncidentCreateResponse
from app.dependencies import build_incident_service
from app.infrastructure.db.session import get_session

router = APIRouter(tags=["incidents"])


@router.post("/incidents", response_model=IncidentCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_incident(
    payload: IncidentCreateRequest,
    session: Session = Depends(get_session),
) -> IncidentCreateResponse:
    service = build_incident_service(session)
    created = service.create_incident(
        title=payload.title,
        description=payload.description,
        order_id=payload.order_id,
        sku=payload.sku,
        sync_job_id=payload.sync_job_id,
        metadata=payload.metadata,
    )
    return IncidentCreateResponse(**created)


@router.get("/incidents/{incident_id}")
def get_incident(
    incident_id: str,
    session: Session = Depends(get_session),
) -> dict:
    service = build_incident_service(session)
    incident = service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


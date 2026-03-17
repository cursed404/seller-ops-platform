from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.application.services.queries import OperationsQueryService
from app.infrastructure.db.session import get_session

router = APIRouter(tags=["pricing"])


@router.get("/pricing/{sku}")
def get_pricing(
    sku: str,
    session: Session = Depends(get_session),
) -> list[dict]:
    service = OperationsQueryService(session)
    snapshots = service.get_pricing(sku)
    if not snapshots:
        raise HTTPException(status_code=404, detail="Pricing not found")
    return snapshots


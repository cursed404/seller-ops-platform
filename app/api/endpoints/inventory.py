from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.application.services.queries import OperationsQueryService
from app.infrastructure.db.session import get_session

router = APIRouter(tags=["inventory"])


@router.get("/inventory/{sku}")
def get_inventory(
    sku: str,
    session: Session = Depends(get_session),
) -> list[dict]:
    service = OperationsQueryService(session)
    snapshots = service.get_inventory(sku)
    if not snapshots:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return snapshots


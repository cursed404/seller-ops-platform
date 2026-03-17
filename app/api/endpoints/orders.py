from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.application.services.queries import OperationsQueryService
from app.infrastructure.db.session import get_session

router = APIRouter(tags=["orders"])


@router.get("/orders/{order_id}")
def get_order(
    order_id: str,
    session: Session = Depends(get_session),
) -> dict:
    service = OperationsQueryService(session)
    order = service.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


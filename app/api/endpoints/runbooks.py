from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.application.services.queries import OperationsQueryService
from app.infrastructure.db.session import get_session

router = APIRouter(tags=["runbooks"])


@router.get("/runbooks")
def get_runbooks(session: Session = Depends(get_session)) -> list[dict]:
    return OperationsQueryService(session).get_runbooks()


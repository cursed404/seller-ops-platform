from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import build_toolbox
from app.infrastructure.db.session import get_session

router = APIRouter(tags=["tools"])


@router.get("/tools")
def get_tools(session: Session = Depends(get_session)) -> list[dict]:
    return build_toolbox(session).list_tools()


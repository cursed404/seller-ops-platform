from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dependencies import get_publisher, get_redis
from app.infrastructure.db.session import get_session
from app.infrastructure.observability.metrics import metrics_response

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(
    session: Session = Depends(get_session),
) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    redis_client = get_redis()
    redis_client.ping()
    publisher = get_publisher()
    if not publisher.is_connected():
        raise HTTPException(status_code=503, detail="Kafka publisher is not connected")
    return {"status": "ready"}


@router.get("/metrics")
def metrics() -> Response:
    content, content_type = metrics_response()
    return Response(content=content, media_type=content_type)

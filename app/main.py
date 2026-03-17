from __future__ import annotations

from fastapi import FastAPI, Request, Response

from app.api.router import api_router
from app.infrastructure.observability.metrics import RequestTimer
from app.logging import configure_logging
from app.settings import get_settings

configure_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(api_router)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next) -> Response:
    timer = RequestTimer()
    response = await call_next(request)
    timer.observe(method=request.method, path=request.url.path, status_code=response.status_code)
    return response

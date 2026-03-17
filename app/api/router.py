from fastapi import APIRouter

from app.api.endpoints import (
    health,
    incidents,
    inventory,
    orders,
    pricing,
    runbooks,
    tools,
    workflows,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(incidents.router, prefix="/api/v1")
api_router.include_router(workflows.router, prefix="/api/v1")
api_router.include_router(orders.router, prefix="/api/v1")
api_router.include_router(inventory.router, prefix="/api/v1")
api_router.include_router(pricing.router, prefix="/api/v1")
api_router.include_router(runbooks.router, prefix="/api/v1")
api_router.include_router(tools.router, prefix="/api/v1")


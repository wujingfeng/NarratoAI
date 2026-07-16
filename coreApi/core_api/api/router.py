from __future__ import annotations

from fastapi import APIRouter

from core_api.api.routes.capabilities import router as capabilities_router
from core_api.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(
    capabilities_router, prefix="/capabilities", tags=["capabilities"]
)

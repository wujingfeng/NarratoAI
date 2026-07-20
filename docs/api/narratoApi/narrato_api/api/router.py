from __future__ import annotations

from fastapi import APIRouter

from narrato_api.api.health import router as health_router
from narrato_api.auth.router import router as auth_router
from narrato_api.assets.router import router as assets_router
from narrato_api.editor.router import router as editor_router
from narrato_api.projects.router import router as projects_router
from narrato_api.internal.router import router as internal_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(assets_router, tags=["uploads"])
api_router.include_router(editor_router, tags=["editor"])
api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(internal_router, tags=["internal"])

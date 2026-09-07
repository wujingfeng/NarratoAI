from __future__ import annotations

from fastapi import APIRouter

from narrato_api.api.health import router as health_router
from narrato_api.auth.router import router as auth_router
from narrato_api.assets.router import router as assets_router
from narrato_api.editor.router import router as editor_router
from narrato_api.projects.router import router as projects_router
from narrato_api.internal.router import router as internal_router
from narrato_api.products.narration_config import router as product_config_router
from narrato_api.products.video_translation import router as video_translation_router
from narrato_api.products.ai_video import router as ai_video_router
from narrato_api.admin.router import router as admin_router
from narrato_api.conversations.router import router as conversations_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(assets_router, tags=["uploads"])
api_router.include_router(editor_router, tags=["editor"])
api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(internal_router, tags=["internal"])
api_router.include_router(product_config_router, tags=["products"])
api_router.include_router(video_translation_router, tags=["video-translation"])
api_router.include_router(ai_video_router, tags=["ai-video"])
api_router.include_router(admin_router, tags=["admin"])
api_router.include_router(conversations_router, tags=["assistant"])

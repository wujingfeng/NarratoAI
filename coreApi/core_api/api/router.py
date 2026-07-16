from __future__ import annotations

from fastapi import APIRouter

from core_api.api.routes.capabilities import router as capabilities_router
from core_api.api.routes.health import router as health_router
from core_api.api.routes.asr import router as asr_router
from core_api.api.routes.media_probe import router as media_probe_router
from core_api.api.routes.tasks import router as tasks_router
from core_api.api.routes.video_analysis import router as video_analysis_router
from core_api.api.routes.script_generation import router as script_generation_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(
    capabilities_router, prefix="/capabilities", tags=["capabilities"]
)
api_router.include_router(
    media_probe_router, prefix="/media-probe", tags=["media-probe"]
)
api_router.include_router(asr_router, prefix="/asr", tags=["asr"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])

api_router.include_router(
    video_analysis_router, prefix="/video-analysis", tags=["video-analysis"]
)
api_router.include_router(
    script_generation_router, prefix="/script-generation", tags=["script-generation"]
)

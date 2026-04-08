from fastapi import APIRouter

from app.api.routers.assets import router as assets_router
from app.api.routers.auth import router as auth_router
from app.api.routers.common import router as common_router
from app.api.routers.conversations import router as conversations_router
from app.api.routers.health_check import router as health_check_router
from app.api.routers.jobs import router as jobs_router
from app.api.routers.settings import router as settings_router
from app.api.routers.tiktok_tasks import router as tiktok_router

from app.api.routers.projects import router as projects_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(common_router, prefix="/common", tags=["Common"])
api_router.include_router(assets_router, prefix="/assets", tags=["Assets"])
api_router.include_router(conversations_router, prefix="/conversations", tags=["Conversations"])
api_router.include_router(projects_router, prefix="/projects", tags=["Projects"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(settings_router, prefix="/settings", tags=["Settings"])
api_router.include_router(health_check_router, prefix="/health", tags=["Health-Check"])
api_router.include_router(tiktok_router, prefix="/tiktok", tags=["TikTok"])

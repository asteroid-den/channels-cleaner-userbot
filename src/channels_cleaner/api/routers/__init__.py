from fastapi import APIRouter

from channels_cleaner.api.models import ErrorResponse

from . import apply, auth, channels, decisions, health, results

# Every error has the same shape (api/errors.py); "default" also stands in for FastAPI's own 422 schema
router = APIRouter(prefix="/api", responses={"default": {"model": ErrorResponse, "description": "An error"}})

for module in (health, auth, channels, decisions, apply, results):
    router.include_router(module.router)

__all__ = ("router",)

"""Assembles every module router under the versioned prefix."""

from fastapi import APIRouter

from app.modules.identity.router import admin_router as identity_admin_router
from app.modules.identity.router import router as identity_router

api_router = APIRouter()
api_router.include_router(identity_router, tags=["identity"])
api_router.include_router(
    identity_admin_router, prefix="/admin/users", tags=["admin: users"]
)

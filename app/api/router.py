"""Assembles every module router under the versioned prefix."""

from fastapi import APIRouter

from app.modules.delivery_pricing.router import admin_router as pricing_admin_router
from app.modules.delivery_pricing.router import router as pricing_router
from app.modules.geo.router import admin_router as geo_admin_router
from app.modules.geo.router import router as geo_router
from app.modules.identity.router import admin_router as identity_admin_router
from app.modules.identity.router import router as identity_router

api_router = APIRouter()
api_router.include_router(identity_router, tags=["identity"])
api_router.include_router(
    identity_admin_router, prefix="/admin/users", tags=["admin: users"]
)

# geo (reference data + delivery-zone management)
api_router.include_router(geo_router)
api_router.include_router(geo_admin_router)

# delivery-pricing (quote engine + rate management)
api_router.include_router(pricing_router)
api_router.include_router(pricing_admin_router)
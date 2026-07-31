"""Assembles every module router under the versioned prefix."""

from fastapi import APIRouter

from app.modules.catalogue.router import admin_router as catalogue_admin_router
from app.modules.catalogue.router import router as catalogue_router
from app.modules.delivery.router import admin_router as delivery_admin_router
from app.modules.delivery.router import courier_router as delivery_courier_router
from app.modules.delivery_pricing.router import admin_router as pricing_admin_router
from app.modules.delivery_pricing.router import router as pricing_router
from app.modules.geo.router import admin_router as geo_admin_router
from app.modules.geo.router import router as geo_router
from app.modules.identity.router import admin_router as identity_admin_router
from app.modules.identity.router import router as identity_router
from app.modules.orders.router import admin_router as orders_admin_router
from app.modules.orders.router import router as orders_router
from app.modules.payments.router import admin_router as payments_admin_router
from app.modules.payments.router import router as payments_router

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

# catalogue (pieces, media, vocab, wishlist, publication)
api_router.include_router(catalogue_router)
api_router.include_router(catalogue_admin_router)

# orders (checkout, tracking, lifecycle)
api_router.include_router(orders_router)
api_router.include_router(orders_admin_router)

# payments (initiate, webhook, admin reconcile/refund)
api_router.include_router(payments_router)
api_router.include_router(payments_admin_router)

# delivery (courier assignment, signed courier link, status/events)
api_router.include_router(delivery_admin_router)
api_router.include_router(delivery_courier_router)
from fastapi import APIRouter
from app.api import auth, users, suppliers, selections, order_items, items, pickups, notifications, favorites, deliveries

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(suppliers.router)
api_router.include_router(selections.router)
api_router.include_router(order_items.router)
api_router.include_router(items.router)
api_router.include_router(pickups.router)
api_router.include_router(notifications.router)
api_router.include_router(favorites.router)
api_router.include_router(deliveries.router)

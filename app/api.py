from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.conf.database import get_db

# Imports des Schémas Pydantic
from app.schemas.user import UserCreate, UserResponse, UserLogin, UserUpdate
from app.schemas.supplier import SupplierCreate, SupplierResponse
from app.schemas.item import ItemCreate, ItemResponse
from app.schemas.selection import SelectionCreate, SelectionResponse
from app.schemas.order_item import OrderItemCreate, OrderItemResponse
from app.schemas.pickup import PickupCreate, PickupResponse
from app.schemas.delivery import DeliveryCreate, DeliveryResponse
from app.schemas.favorite import FavoriteCreate, FavoriteResponse
from app.schemas.notification import NotificationCreate, NotificationResponse

# Imports des Services Métier
from app.services.user_service import UserService
from app.services.supplier_service import SupplierService
from app.services.item_service import ItemService
from app.services.selection_service import SelectionService
from app.services.order_item_service import OrderItemService
from app.services.pickup_service import PickupService
from app.services.delivery_service import DeliveryService
from app.services.favorite_service import FavoriteService
from app.services.notification_service import NotificationService




# Routeur principal
api_router = APIRouter()


# ==========================================
# 1. AUTHENTIFICATION & USERS
# ==========================================
@api_router.post("/auth/register", response_model=UserResponse, tags=["Authentification"], status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if UserService.get_by_email(db, email=user_in.email):
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé.")
    return UserService.create(db, user_in)

@api_router.get("/users/", response_model=List[UserResponse], tags=["Utilisateurs"])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return UserService.get_all(db, skip=skip, limit=limit)


# ==========================================
# 2. SUPPLIERS (Fournisseurs)
# ==========================================
@api_router.post("/suppliers/", response_model=SupplierResponse, tags=["Fournisseurs"], status_code=status.HTTP_201_CREATED)
def create_supplier(supplier_in: SupplierCreate, db: Session = Depends(get_db)):
    return SupplierService.create(db, supplier_in)


# ==========================================
# 3. ITEMS (Articles)
# ==========================================
@api_router.post("/items/", response_model=ItemResponse, tags=["Articles"], status_code=status.HTTP_201_CREATED)
def create_item(item_in: ItemCreate, db: Session = Depends(get_db)):
    return ItemService.create(db, item_in)

@api_router.get("/items/", response_model=List[ItemResponse], tags=["Articles"])
def read_items(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return ItemService.get_all(db, skip=skip, limit=limit)


# ==========================================
# 4. SELECTIONS & ORDER_ITEMS
# ==========================================
@api_router.post("/selections/", response_model=SelectionResponse, tags=["Sélections / Commandes"], status_code=status.HTTP_201_CREATED)
def create_selection(selection_in: SelectionCreate, db: Session = Depends(get_db)):
    return SelectionService.create(db, selection_in)

@api_router.post("/order-items/", response_model=OrderItemResponse, tags=["Articles par Commande"], status_code=status.HTTP_201_CREATED)
def add_item_to_order(order_item_in: OrderItemCreate, db: Session = Depends(get_db)):
    return OrderItemService.create(db, order_item_in)

@api_router.get("/order-items/selection/{selection_id}", response_model=List[OrderItemResponse], tags=["Articles par Commande"])
def read_items_by_selection(selection_id: str, db: Session = Depends(get_db)):
    return OrderItemService.get_by_selection_id(db, selection_id)


# ==========================================
# 5. PICKUPS (Collectes)
# ==========================================
@api_router.post("/pickups/", response_model=PickupResponse, tags=["Collectes (Pickups)"], status_code=status.HTTP_201_CREATED)
def create_pickup(pickup_in: PickupCreate, db: Session = Depends(get_db)):
    return PickupService.create(db, pickup_in)


# ==========================================
# 6. DELIVERIES (Livraisons)
# ==========================================
@api_router.post("/deliveries/", response_model=DeliveryResponse, tags=["Livraisons"], status_code=status.HTTP_201_CREATED)
def create_delivery(delivery_in: DeliveryCreate, db: Session = Depends(get_db)):
    return DeliveryService.create(db, delivery_in)


# ==========================================
# 7. FAVORITES & NOTIFICATIONS
# ==========================================
@api_router.post("/favorites/", response_model=FavoriteResponse, tags=["Favoris"], status_code=status.HTTP_201_CREATED)
def add_favorite(favorite_in: FavoriteCreate, db: Session = Depends(get_db)):
    return FavoriteService.create(db, favorite_in)

@api_router.post("/notifications/", response_model=NotificationResponse, tags=["Notifications"], status_code=status.HTTP_201_CREATED)
def create_notification(notif_in: NotificationCreate, db: Session = Depends(get_db)):
    return NotificationService.create(db, notif_in)
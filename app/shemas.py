from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, EmailStr

# Configuration de base réutilisable pour la conversion automatique depuis SQLAlchemy
class ORMBase(BaseModel):
    class Config:
        from_attributes = True


# ==========================================
# 1. USER
# ==========================================
class UserBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    role: Optional[str] = "CLIENT"

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None

class UserResponse(UserBase, ORMBase):
    user_id: UUID
    is_active: bool
    created_at: datetime


# ==========================================
# 2. SUPPLIER
# ==========================================
class SupplierBase(BaseModel):
    shop_name: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class SupplierCreate(SupplierBase):
    user_id: UUID

class SupplierResponse(SupplierBase, ORMBase):
    supplier_id: UUID
    user_id: UUID


# ==========================================
# 3. ITEM
# ==========================================
class ItemBase(BaseModel):
    universe: str
    house: str
    item_state: Optional[str] = None
    price: Optional[float] = None
    story: Optional[str] = None
    size: Optional[int] = None
    item_status: Optional[str] = "AVAILABLE"

class ItemCreate(ItemBase):
    item_id: str
    supplier_id: Optional[UUID] = None

class ItemResponse(ItemBase, ORMBase):
    item_id: str
    created_at: Optional[datetime] = None


# ==========================================
# 4. SELECTION
# ==========================================
class SelectionBase(BaseModel):
    client_id: UUID
    total_amount: Optional[float] = 0.0
    status: Optional[str] = "PENDING"

class SelectionCreate(SelectionBase):
    selection_id: str

class SelectionResponse(SelectionBase, ORMBase):
    selection_id: str
    created_at: datetime


# ==========================================
# 5. ORDER_ITEM
# ==========================================
class OrderItemBase(BaseModel):
    selection_id: str
    item_id: str
    unit_price: Optional[float] = None

class OrderItemCreate(OrderItemBase):
    pass

class OrderItemResponse(OrderItemBase, ORMBase):
    id: UUID


# ==========================================
# 6. PICKUP
# ==========================================
class PickupBase(BaseModel):
    supplier_id: UUID
    pickup_status: Optional[str] = "PENDING"
    notes: Optional[str] = None

class PickupCreate(PickupBase):
    pass

class PickupResponse(PickupBase, ORMBase):
    pickup_id: UUID
    created_at: datetime


# ==========================================
# 7. DELIVERY
# ==========================================
class DeliveryBase(BaseModel):
    selection_id: str
    delivery_agent_id: Optional[UUID] = None
    delivery_status: Optional[str] = "IN_PROGRESS"

class DeliveryCreate(DeliveryBase):
    pass

class DeliveryResponse(DeliveryBase, ORMBase):
    delivery_id: UUID
    access_token: UUID
    token_expires_at: Optional[datetime] = None
    created_at: datetime


# ==========================================
# 8. FAVORITE
# ==========================================
class FavoriteBase(BaseModel):
    client_id: UUID
    item_id: str

class FavoriteCreate(FavoriteBase):
    pass

class FavoriteResponse(FavoriteBase, ORMBase):
    id: UUID
    created_at: datetime


# ==========================================
# 9. NOTIFICATION
# ==========================================
class NotificationBase(BaseModel):
    user_id: UUID
    title: str
    message: str
    is_read: Optional[bool] = False

class NotificationCreate(NotificationBase):
    pass

class NotificationResponse(NotificationBase, ORMBase):
    notification_id: UUID
    created_at: datetime
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

# Imports des modèles SQLAlchemy
from app.models import (
    User,
    Supplier,
    Item,
    Selection,
    OrderItem,
    Pickup,
    Delivery,
    Favorite,
    Notification
)

# Imports des schémas Pydantic
from app.schemas import (
    UserCreate, UserUpdate,
    SupplierCreate,
    ItemCreate,
    SelectionCreate,
    OrderItemCreate,
    PickupCreate,
    DeliveryCreate,
    FavoriteCreate,
    NotificationCreate
)


# ==========================================
# 1. USER SERVICE
# ==========================================
class UserService:
    @staticmethod
    def get_by_id(db: Session, user_id: UUID) -> Optional[User]:
        return db.query(User).filter(User.user_id == user_id).first()

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return db.query(User).offset(skip).limit(limit).all()

    @staticmethod
    def create(db: Session, user_in: UserCreate) -> User:
        # Pensez à hacher le mot de passe en production (ex: passlib / bcrypt)
        db_user = User(
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            email=user_in.email,
            phone=user_in.phone,
            role=user_in.role,
            hashed_password=user_in.password
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    @staticmethod
    def update(db: Session, db_user: User, user_in: UserUpdate) -> User:
        update_data = user_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_user, field, value)
        db.commit()
        db.refresh(db_user)
        return db_user


# ==========================================
# 2. SUPPLIER SERVICE
# ==========================================
class SupplierService:
    @staticmethod
    def get_by_id(db: Session, supplier_id: UUID) -> Optional[Supplier]:
        return db.query(Supplier).filter(Supplier.supplier_id == supplier_id).first()

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[Supplier]:
        return db.query(Supplier).offset(skip).limit(limit).all()

    @staticmethod
    def create(db: Session, supplier_in: SupplierCreate) -> Supplier:
        db_supplier = Supplier(**supplier_in.model_dump())
        db.add(db_supplier)
        db.commit()
        db.refresh(db_supplier)
        return db_supplier


# ==========================================
# 3. ITEM SERVICE
# ==========================================
class ItemService:
    @staticmethod
    def get_by_id(db: Session, item_id: str) -> Optional[Item]:
        return db.query(Item).filter(Item.item_id == item_id).first()

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[Item]:
        return db.query(Item).offset(skip).limit(limit).all()

    @staticmethod
    def create(db: Session, item_in: ItemCreate) -> Item:
        db_item = Item(**item_in.model_dump())
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item


# ==========================================
# 4. SELECTION SERVICE
# ==========================================
class SelectionService:
    @staticmethod
    def get_by_id(db: Session, selection_id: str) -> Optional[Selection]:
        return db.query(Selection).filter(Selection.selection_id == selection_id).first()

    @staticmethod
    def get_by_client(db: Session, client_id: UUID) -> List[Selection]:
        return db.query(Selection).filter(Selection.client_id == client_id).all()

    @staticmethod
    def create(db: Session, selection_in: SelectionCreate) -> Selection:
        db_selection = Selection(**selection_in.model_dump())
        db.add(db_selection)
        db.commit()
        db.refresh(db_selection)
        return db_selection


# ==========================================
# 5. ORDER ITEM SERVICE
# ==========================================
class OrderItemService:
    @staticmethod
    def get_by_selection_id(db: Session, selection_id: str) -> List[OrderItem]:
        return db.query(OrderItem).filter(OrderItem.selection_id == selection_id).all()

    @staticmethod
    def create(db: Session, order_item_in: OrderItemCreate) -> OrderItem:
        db_order_item = OrderItem(**order_item_in.model_dump())
        db.add(db_order_item)
        db.commit()
        db.refresh(db_order_item)
        return db_order_item


# ==========================================
# 6. PICKUP SERVICE
# ==========================================
class PickupService:
    @staticmethod
    def get_by_id(db: Session, pickup_id: UUID) -> Optional[Pickup]:
        return db.query(Pickup).filter(Pickup.pickup_id == pickup_id).first()

    @staticmethod
    def create(db: Session, pickup_in: PickupCreate) -> Pickup:
        db_pickup = Pickup(**pickup_in.model_dump())
        db.add(db_pickup)
        db.commit()
        db.refresh(db_pickup)
        return db_pickup


# ==========================================
# 7. DELIVERY SERVICE
# ==========================================
class DeliveryService:
    @staticmethod
    def get_by_id(db: Session, delivery_id: UUID) -> Optional[Delivery]:
        return db.query(Delivery).filter(Delivery.delivery_id == delivery_id).first()

    @staticmethod
    def create(db: Session, delivery_in: DeliveryCreate) -> Delivery:
        db_delivery = Delivery(**delivery_in.model_dump())
        db.add(db_delivery)
        db.commit()
        db.refresh(db_delivery)
        return db_delivery


# ==========================================
# 8. FAVORITE SERVICE
# ==========================================
class FavoriteService:
    @staticmethod
    def get_by_client(db: Session, client_id: UUID) -> List[Favorite]:
        return db.query(Favorite).filter(Favorite.client_id == client_id).all()

    @staticmethod
    def create(db: Session, favorite_in: FavoriteCreate) -> Favorite:
        db_favorite = Favorite(**favorite_in.model_dump())
        db.add(db_favorite)
        db.commit()
        db.refresh(db_favorite)
        return db_favorite


# ==========================================
# 9. NOTIFICATION SERVICE
# ==========================================
class NotificationService:
    @staticmethod
    def get_by_user(db: Session, user_id: UUID) -> List[Notification]:
        return db.query(Notification).filter(Notification.user_id == user_id).all()

    @staticmethod
    def create(db: Session, notif_in: NotificationCreate) -> Notification:
        db_notif = Notification(**notif_in.model_dump())
        db.add(db_notif)
        db.commit()
        db.refresh(db_notif)
        return db_notif
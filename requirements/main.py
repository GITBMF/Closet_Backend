import os
import uuid
from typing import List, Optional
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, TIMESTAMP, ForeignKey, JSON, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from sqlalchemy.sql import func
from fastapi import FastAPI, Depends, HTTPException, status
from starlette_admin.contrib.sqla import Admin, ModelView
from pydantic import BaseModel
import uvicorn

# ==========================================
# 1. PARAMÈTRES DE CONNEXION POSTGRESQL
# ==========================================
DB_USER = os.getenv("DB_USER", "dev_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "w%o5gn2-0sW_3R^x9*8d")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres_dev")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 2. DÉFINITION DES MODÈLES SQLALCHEMY
# ==========================================
class User(Base):
    __tablename__ = "users"
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True)
    hash_password = Column(String)
    phone = Column(String, unique=True)
    full_name = Column(String)
    role = Column(Integer)
    city = Column(String)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP)

    selections = relationship("Selection", back_populates="client")
    notifications = relationship("Notification", back_populates="user")
    items = relationship("Item", back_populates="supplier")
    favorites = relationship("Favorite", back_populates="client")
    deliveries = relationship("Delivery", back_populates="agent")
    pickups = relationship("Pickup", back_populates="agent")

    def __str__(self):
        return self.full_name or str(self.user_id)


class Selection(Base):
    __tablename__ = "selections"
    selection_id = Column(String, primary_key=True, nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    selection_status = Column(String, default="CONFIRMEE")
    qty = Column(Integer, nullable=False)
    total_selection = Column(Float)
    delivering_fee = Column(Float)
    code_promo = Column(String)
    total_amount = Column(Float)
    guest_token = Column(String)
    delivery_address = Column(String)
    delivery_date = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP)

    client = relationship("User", back_populates="selections")
    order_items = relationship("OrderItem", back_populates="selection")
    deliveries = relationship("Delivery", back_populates="selection")

    def __str__(self):
        return f"Selection {self.selection_id}"


class Supplier(Base):
    __tablename__ = "suppliers"
    supplier_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    validated = Column(Boolean)
    request_datetime = Column(TIMESTAMP, server_default=func.now())
    collab_type = Column(String, nullable=False)
    supplier_since = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)

    pickups = relationship("Pickup", back_populates="supplier")

    def __str__(self):
        return str(self.supplier_id)


class Item(Base):
    __tablename__ = "items"
    item_id = Column(String(8), primary_key=True, nullable=False)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    universe = Column(String, nullable=False)
    house = Column(String, nullable=False)
    item_state = Column(String)
    price = Column(Float)
    story = Column(String)
    size = Column(Integer)
    item_status = Column(String)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP)

    supplier = relationship("User", back_populates="items")
    order_items = relationship("OrderItem", back_populates="item")
    pickups = relationship("Pickup", back_populates="item")
    favorites = relationship("Favorite", back_populates="item")

    def __str__(self):
        return f"{self.house} ({self.item_id})"


class OrderItem(Base):
    __tablename__ = "order_items"
    item_id = Column(String, ForeignKey("items.item_id"), primary_key=True)
    selection_id = Column(String, ForeignKey("selections.selection_id"), nullable=False)

    selection = relationship("Selection", back_populates="order_items")
    item = relationship("Item", back_populates="order_items")


class Pickup(Base):
    __tablename__ = "pickups"
    pickup_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id"), nullable=False)
    pickup_agent = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    item_id = Column(String, ForeignKey("items.item_id"), nullable=False)
    pickup_address = Column(String, nullable=False)
    additional_indications = Column(String)
    pickup_date = Column(TIMESTAMP)
    pickup_status = Column(String, default="DEMANDE")
    requested_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP)

    supplier = relationship("Supplier", back_populates="pickups")
    agent = relationship("User", back_populates="pickups")
    item = relationship("Item", back_populates="pickups")


class Notification(Base):
    __tablename__ = "notifications"
    notification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    recipient_contact = Column(String, nullable=False)
    channel = Column(Integer)
    template = Column(String)
    db_infos = Column(JSON)
    notif_status = Column(String, default="EN ATTENTE")
    created_at = Column(TIMESTAMP, server_default=func.now())
    error_message = Column(String)
    updated_at = Column(TIMESTAMP)

    user = relationship("User", back_populates="notifications")


class Favorite(Base):
    __tablename__ = "favorites"
    client_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), primary_key=True)
    item_id = Column(String, ForeignKey("items.item_id"), primary_key=True)
    added_at = Column(TIMESTAMP)

    client = relationship("User", back_populates="favorites")
    item = relationship("Item", back_populates="favorites")


class Delivery(Base):
    __tablename__ = "deliveries"
    delivery_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    selection_id = Column(String, ForeignKey("selections.selection_id"), nullable=False)
    delivery_agent = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    delivery_status = Column(String, default="PRISE EN CHARGE")
    access_token = Column(UUID(as_uuid=True), default=uuid.uuid4)
    token_expires_at = Column(TIMESTAMP, server_default=text("now() + interval '7 days'"))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP)

    selection = relationship("Selection", back_populates="deliveries")
    agent = relationship("User", back_populates="deliveries")

# ==========================================
# 3. SCHÉMAS PYDANTIC (RÉPONSES & REQUÊTES)
# ==========================================

# --- USER ---
class UserBase(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[int] = None
    city: Optional[str] = None

class UserCreate(UserBase):
    hash_password: str

class UserResponse(UserBase):
    user_id: uuid.UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- SELECTION ---
class SelectionBase(BaseModel):
    client_id: Optional[uuid.UUID] = None
    selection_status: Optional[str] = "CONFIRMEE"
    qty: int
    total_selection: Optional[float] = None
    delivering_fee: Optional[float] = None
    code_promo: Optional[str] = None
    total_amount: Optional[float] = None
    guest_token: Optional[str] = None
    delivery_address: Optional[str] = None
    delivery_date: Optional[datetime] = None

class SelectionCreate(SelectionBase):
    selection_id: str

class SelectionResponse(SelectionBase):
    selection_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- SUPPLIER ---
class SupplierCreate(BaseModel):
    collab_type: str
    validated: Optional[bool] = False
    supplier_since: Optional[datetime] = None

class SupplierResponse(SupplierCreate):
    supplier_id: uuid.UUID
    request_datetime: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- ITEM ---
class ItemBase(BaseModel):
    supplier_id: Optional[uuid.UUID] = None
    universe: str
    house: str
    item_state: Optional[str] = None
    price: Optional[float] = None
    story: Optional[str] = None
    size: Optional[int] = None
    item_status: Optional[str] = None

class ItemCreate(ItemBase):
    item_id: str

class ItemResponse(ItemBase):
    item_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- ORDER ITEM ---
class OrderItemCreate(BaseModel):
    item_id: str
    selection_id: str

class OrderItemResponse(OrderItemCreate):
    class Config:
        from_attributes = True

# --- PICKUP ---
class PickupCreate(BaseModel):
    supplier_id: uuid.UUID
    pickup_agent: Optional[uuid.UUID] = None
    item_id: str
    pickup_address: str
    additional_indications: Optional[str] = None
    pickup_date: Optional[datetime] = None
    pickup_status: Optional[str] = "DEMANDE"

class PickupResponse(PickupCreate):
    pickup_id: uuid.UUID
    requested_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- NOTIFICATION ---
class NotificationCreate(BaseModel):
    user_id: uuid.UUID
    recipient_contact: str
    channel: Optional[int] = None
    template: Optional[str] = None
    db_infos: Optional[dict] = None
    notif_status: Optional[str] = "EN ATTENTE"
    error_message: Optional[str] = None

class NotificationResponse(NotificationCreate):
    notification_id: uuid.UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- FAVORITE ---
class FavoriteCreate(BaseModel):
    client_id: uuid.UUID
    item_id: str
    added_at: Optional[datetime] = None

class FavoriteResponse(FavoriteCreate):
    class Config:
        from_attributes = True

# --- DELIVERY ---
class DeliveryCreate(BaseModel):
    selection_id: str
    delivery_agent: Optional[uuid.UUID] = None
    delivery_status: Optional[str] = "PRISE EN CHARGE"

class DeliveryResponse(DeliveryCreate):
    delivery_id: uuid.UUID
    access_token: uuid.UUID
    token_expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ==========================================
# 4. INITIALISATION FASTAPI + ROUTES (GET / POST)
# ==========================================
app = FastAPI(title="Closet Backend")

@app.get("/")
def homepage():
    return {"message": "Bienvenue ! Consultez /docs pour l’API et /admin pour l’administration."}

# --- USERS ---
@app.get("/users", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = User(**user.model_dump())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# --- SELECTIONS ---
@app.get("/selections", response_model=List[SelectionResponse])
def get_selections(db: Session = Depends(get_db)):
    return db.query(Selection).all()

@app.post("/selections", response_model=SelectionResponse, status_code=status.HTTP_201_CREATED)
def create_selection(selection: SelectionCreate, db: Session = Depends(get_db)):
    db_selection = Selection(**selection.model_dump())
    db.add(db_selection)
    db.commit()
    db.refresh(db_selection)
    return db_selection

# --- SUPPLIERS ---
@app.get("/suppliers", response_model=List[SupplierResponse])
def get_suppliers(db: Session = Depends(get_db)):
    return db.query(Supplier).all()

@app.post("/suppliers", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(supplier: SupplierCreate, db: Session = Depends(get_db)):
    db_supplier = Supplier(**supplier.model_dump())
    db.add(db_supplier)
    db.commit()
    db.refresh(db_supplier)
    return db_supplier

# --- ITEMS ---
@app.get("/items", response_model=List[ItemResponse])
def get_items(db: Session = Depends(get_db)):
    return db.query(Item).all()

@app.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    db_item = Item(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

# --- ORDER ITEMS ---
@app.get("/order-items", response_model=List[OrderItemResponse])
def get_order_items(db: Session = Depends(get_db)):
    return db.query(OrderItem).all()

@app.post("/order-items", response_model=OrderItemResponse, status_code=status.HTTP_201_CREATED)
def create_order_item(order_item: OrderItemCreate, db: Session = Depends(get_db)):
    db_order_item = OrderItem(**order_item.model_dump())
    db.add(db_order_item)
    db.commit()
    db.refresh(db_order_item)
    return db_order_item

# --- PICKUPS ---
@app.get("/pickups", response_model=List[PickupResponse])
def get_pickups(db: Session = Depends(get_db)):
    return db.query(Pickup).all()

@app.post("/pickups", response_model=PickupResponse, status_code=status.HTTP_201_CREATED)
def create_pickup(pickup: PickupCreate, db: Session = Depends(get_db)):
    db_pickup = Pickup(**pickup.model_dump())
    db.add(db_pickup)
    db.commit()
    db.refresh(db_pickup)
    return db_pickup

# --- NOTIFICATIONS ---
@app.get("/notifications", response_model=List[NotificationResponse])
def get_notifications(db: Session = Depends(get_db)):
    return db.query(Notification).all()

@app.post("/notifications", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
def create_notification(notification: NotificationCreate, db: Session = Depends(get_db)):
    db_notif = Notification(**notification.model_dump())
    db.add(db_notif)
    db.commit()
    db.refresh(db_notif)
    return db_notif

# --- FAVORITES ---
@app.get("/favorites", response_model=List[FavoriteResponse])
def get_favorites(db: Session = Depends(get_db)):
    return db.query(Favorite).all()

@app.post("/favorites", response_model=FavoriteResponse, status_code=status.HTTP_201_CREATED)
def create_favorite(favorite: FavoriteCreate, db: Session = Depends(get_db)):
    db_fav = Favorite(**favorite.model_dump())
    db.add(db_fav)
    db.commit()
    db.refresh(db_fav)
    return db_fav

# --- DELIVERIES ---
@app.get("/deliveries", response_model=List[DeliveryResponse])
def get_deliveries(db: Session = Depends(get_db)):
    return db.query(Delivery).all()

@app.post("/deliveries", response_model=DeliveryResponse, status_code=status.HTTP_201_CREATED)
def create_delivery(delivery: DeliveryCreate, db: Session = Depends(get_db)):
    db_delivery = Delivery(**delivery.model_dump())
    db.add(db_delivery)
    db.commit()
    db.refresh(db_delivery)
    return db_delivery

# ==========================================
# 5. CONFIGURATION PANNEAU ADMIN
# ==========================================
admin = Admin(engine, title="Administration du Système")
admin.add_view(ModelView(User, label="Utilisateurs"))
admin.add_view(ModelView(Selection, label="Sélections / Commandes"))
admin.add_view(ModelView(Supplier, label="Fournisseurs"))
admin.add_view(ModelView(Item, label="Articles"))
admin.add_view(ModelView(OrderItem, label="Articles par Commande"))
admin.add_view(ModelView(Pickup, label="Collectes (Pickups)"))
admin.add_view(ModelView(Notification, label="Notifications"))
admin.add_view(ModelView(Favorite, label="Favoris"))
admin.add_view(ModelView(Delivery, label="Livraisons"))

admin.mount_to(app)

# ==========================================
# 6. LANCEMENT DU SERVEUR
# ==========================================
if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    # Passe directement l'instance 'app' pour éviter les soucis de nom de fichier
    uvicorn.run(app, host="127.0.0.1", port=8000)
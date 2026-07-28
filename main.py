import os
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, TIMESTAMP, ForeignKey, JSON, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func
from starlette.applications import Starlette
from starlette_admin.contrib.sqla import Admin, ModelView
import uvicorn
import urllib.parse
# ==========================================
# 1. PARAMÈTRES DE CONNEXION POSTGRESQL
# ==========================================
DB_USER = os.getenv("DB_USER", "dev_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "w%o5gn2-0sW_3R^x9*8d")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres_dev")

# URL de connexion PostgreSQL (utilisation de psycopg2)
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Moteur SQLAlchemy et Session
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarative SQLAlchemy
Base = declarative_base()


# ==========================================
# 2. DÉFINITION DES MODÈLES (SQLAlchemy)
# ==========================================

class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    email = Column(String, unique=True)
    hash_password = Column(String)
    phone = Column(String, unique=True)
    full_name = Column(String)
    role = Column(Integer)
    city = Column(String)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP)

    # Relations
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

    # Relations
    client = relationship("User", back_populates="selections")
    order_items = relationship("OrderItem", back_populates="selection")
    deliveries = relationship("Delivery", back_populates="selection")

    def __str__(self):
        return f"Selection {self.selection_id}"


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    validated = Column(Boolean)
    request_datetime = Column(TIMESTAMP, server_default=func.now())
    collab_type = Column(String, nullable=False)
    supplier_since = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)

    # Relations
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

    # Relations
    supplier = relationship("User", back_populates="items")
    order_items = relationship("OrderItem", back_populates="item")
    pickups = relationship("Pickup", back_populates="item")
    favorites = relationship("Favorite", back_populates="item")

    def __str__(self):
        return f"{self.house} ({self.item_id})"


class OrderItem(Base):
    __tablename__ = "order_item"

    item_id = Column(String, ForeignKey("items.item_id"), primary_key=True)
    selection_id = Column(String, ForeignKey("selections.selection_id"), nullable=False)

    # Relations
    selection = relationship("Selection", back_populates="order_items")
    item = relationship("Item", back_populates="order_items")


class Pickup(Base):
    __tablename__ = "pickups"

    pickup_id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id"), nullable=False)
    pickup_agent = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    item_id = Column(String, ForeignKey("items.item_id"), nullable=False)
    pickup_address = Column(String, nullable=False)
    additional_indications = Column(String)
    pickup_date = Column(TIMESTAMP)
    pickup_status = Column(String, default="DEMANDE")
    requested_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP)

    # Relations
    supplier = relationship("Supplier", back_populates="pickups")
    agent = relationship("User", back_populates="pickups")
    item = relationship("Item", back_populates="pickups")


class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    recipient_contact = Column(String, nullable=False)
    channel = Column(Integer)
    template = Column(String)
    db_infos = Column(JSON)
    notif_status = Column(String, default="EN ATTENTE")
    created_at = Column(TIMESTAMP, server_default=func.now())
    error_message = Column(String)
    updated_at = Column(TIMESTAMP)

    # Relations
    user = relationship("User", back_populates="notifications")


class Favorite(Base):
    __tablename__ = "favorites"

    client_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), primary_key=True)
    item_id = Column(String, ForeignKey("items.item_id"), primary_key=True)
    added_at = Column(TIMESTAMP)

    # Relations
    client = relationship("User", back_populates="favorites")
    item = relationship("Item", back_populates="favorites")


class Delivery(Base):
    __tablename__ = "deliveries"

    delivery_id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    selection_id = Column(String, ForeignKey("selections.selection_id"), nullable=False)
    delivery_agent = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    delivery_status = Column(String, default="PRISE EN CHARGE")
    access_token = Column(UUID(as_uuid=True), server_default=func.gen_random_uuid())
    token_expires_at = Column(TIMESTAMP, server_default=text("now() + interval '7 days'"))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP)

    # Relations
    selection = relationship("Selection", back_populates="deliveries")
    agent = relationship("User", back_populates="deliveries")


# ==========================================
# 3. INITIALISATION DE STARLETTE & STARLETTE-ADMIN
# ==========================================

app = Starlette()

# Création de l'interface Admin
admin = Admin(engine, title="Administration du Système")

# Ajout des 9 vues de modèles dans l'administration
admin.add_view(ModelView(User, label="Utilisateurs"))
admin.add_view(ModelView(Selection, label="Sélections / Commandes"))
admin.add_view(ModelView(Supplier, label="Fournisseurs"))
admin.add_view(ModelView(Item, label="Articles"))
admin.add_view(ModelView(OrderItem, label="Articles par Commande"))
admin.add_view(ModelView(Pickup, label="Collectes (Pickups)"))
admin.add_view(ModelView(Notification, label="Notifications"))
admin.add_view(ModelView(Favorite, label="Favoris"))
admin.add_view(ModelView(Delivery, label="Livraisons"))

# Monter l'admin sur l'application Starlette
admin.mount_to(app)

# ==========================================
# 4. EXÉCUTION DU SERVEUR UVICORN
# ==========================================

if __name__ == "__main__":
    # Crée les tables en BDD si elles n'existent pas encore
    Base.metadata.create_all(bind=engine)
    
    # Lancement du serveur sur http://127.0.0.1:8000
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.conf.config import settings

# Création du moteur SQLAlchemy
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True  # Vérifie que la connexion est toujours active avant de l'utiliser
)

# Fabrique de sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Classe de base pour déclarer les modèles SQLAlchemy (models.py)
Base = declarative_base()

# Dépendance FastAPI pour injecter la session BDD dans les endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
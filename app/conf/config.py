import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Mon API FastAPI"
    VERSION: str = "1.0.0"
    
    # URL de la base de données (PostgreSQL par défaut, modifiable dans le .env)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/mon_projet_db"
    )
    
    # Sécurité / JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super_cle_secrete_a_changer_en_production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 heures

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
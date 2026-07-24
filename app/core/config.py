"""Application settings, loaded from the environment.

One Settings class for the whole app. Never read os.environ elsewhere.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.dev", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # ---- environment -------------------------------------------------
    ENVIRONMENT: str = "dev"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ---- database ----------------------------------------------------
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "closet_dev"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DB_ECHO: bool = False

    # ---- JWT ---------------------------------------------------------
    JWT_SECRET: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 30
    # short-lived token issued between password check and 2FA code check
    MFA_CHALLENGE_MINUTES: int = 5

    # ---- password policy --------------------------------------------
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_RESET_HOURS: int = 2

    # ---- brute-force protection -------------------------------------
    MAX_FAILED_LOGINS: int = 5
    LOCKOUT_MINUTES: int = 15

    # ---- 2FA ---------------------------------------------------------
    TOTP_ISSUER: str = "ClosET"
    ADMIN_REQUIRES_2FA: bool = True

    # ---- first-run administrator -------------------------------------
    # If both e-mail and password are set AND no administrator exists yet,
    # one is created at startup. The account is flagged must_change_password,
    # so the value below is a single-use credential, never a standing one.
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    BOOTSTRAP_ADMIN_NAME: str = "Administrateur ClosET"

    # ---- internal ops panel (Starlette-Admin) ------------------------
    OPS_ENABLED: bool = True          # set false in staging/production
    OPS_ALLOW_IN_PROD: bool = False   # extra guard, see app/ops/admin.py
    OPS_BASE_URL: str = "/ops"
    OPS_SESSION_SECRET: str = ""      # falls back to JWT_SECRET
    OPS_LOGO_URL: str = ""

    # ---- misc --------------------------------------------------------
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])

    def _dsn(self, driver: str) -> str:
        """Build a DSN with credentials safely escaped.

        Passwords routinely contain characters that are special in a URL
        (%, ^, *, @, /, #). Hand-formatting an f-string corrupts them —
        URL.create percent-encodes each component correctly.
        """
        return URL.create(
            driver,
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)

    @property
    def database_url(self) -> str:
        """Async DSN used by the application."""
        return self._dsn("postgresql+asyncpg")

    @property
    def sync_database_url(self) -> str:
        """Sync DSN used by Alembic."""
        return self._dsn("postgresql+psycopg2")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
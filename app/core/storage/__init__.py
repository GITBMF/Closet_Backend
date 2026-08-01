"""Storage provider factory.

get_storage() reads settings and returns the configured provider. Swapping
MinIO -> S3 -> R2 is entirely a config change; this factory is the only place
that knows which concrete provider is active.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.storage.base import StorageError, StorageProvider, StoredObject
from app.core.storage.s3 import S3StorageProvider

__all__ = [
    "StorageProvider",
    "StoredObject",
    "StorageError",
    "get_storage",
]


@lru_cache
def get_storage() -> StorageProvider:
    provider = settings.STORAGE_PROVIDER.lower()
    if provider == "s3":
        return S3StorageProvider(
            bucket=settings.S3_BUCKET,
            public_base_url=settings.S3_PUBLIC_BASE_URL,
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            region=settings.S3_REGION,
            access_key=settings.S3_ACCESS_KEY or None,
            secret_key=settings.S3_SECRET_KEY or None,
            force_path_style=settings.S3_FORCE_PATH_STYLE,
        )
    raise ValueError(f"Unknown STORAGE_PROVIDER: {settings.STORAGE_PROVIDER!r}")
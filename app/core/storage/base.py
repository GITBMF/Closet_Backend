"""Storage provider abstraction.

The catalogue (and later, sourcing submissions) store media by URL. WHERE the
bytes live is an infrastructure choice that must be swappable: MinIO in dev,
AWS S3 / Cloudflare R2 in prod, all behind this one interface. Only env vars
change between them — never code that imports StorageProvider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class StoredObject:
    """The result of a successful upload."""

    key: str      # the object key within the bucket (what we delete by)
    url: str      # the public URL clients use to fetch it


class StorageError(Exception):
    """Raised when the storage backend fails (upload/delete)."""


class StorageProvider(ABC):
    """A place to put and remove binary objects and get back public URLs."""

    @abstractmethod
    async def put(
        self, *, key: str, data: bytes, content_type: str
    ) -> StoredObject:
        """Store `data` under `key`; return the key and its public URL."""

    @abstractmethod
    async def delete(self, *, key: str) -> None:
        """Remove the object at `key`. No error if it's already gone."""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """Build the public URL for a key without a network call."""
"""S3-compatible storage provider.

Works unchanged against MinIO (dev), AWS S3, and Cloudflare R2 — they all
speak the S3 API. The differences (endpoint, path-style addressing, public
URL base) are all configuration, injected here, so the provider code is
identical across environments.

boto3 is synchronous; we run its calls in a thread so we don't block the
event loop.
"""

from __future__ import annotations

import asyncio
from functools import partial

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.storage.base import StorageError, StorageProvider, StoredObject


class S3StorageProvider(StorageProvider):
    def __init__(
        self,
        *,
        bucket: str,
        public_base_url: str,
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        access_key: str | None = None,
        secret_key: str | None = None,
        force_path_style: bool = True,
    ) -> None:
        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/")
        addressing = "path" if force_path_style else "auto"
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(s3={"addressing_style": addressing}),
        )

    async def put(
        self, *, key: str, data: bytes, content_type: str
    ) -> StoredObject:
        fn = partial(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        try:
            await asyncio.to_thread(fn)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"upload failed: {exc}") from exc
        return StoredObject(key=key, url=self.public_url(key))

    async def delete(self, *, key: str) -> None:
        fn = partial(self._client.delete_object, Bucket=self._bucket, Key=key)
        try:
            await asyncio.to_thread(fn)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"delete failed: {exc}") from exc

    def public_url(self, key: str) -> str:
        return f"{self._public_base_url}/{key.lstrip('/')}"
"""
Storage helper — MinIO (S3-compatible).
"""

from __future__ import annotations

import io
from minio import Minio
from minio.error import S3Error

from app.core.config import settings


class StorageClient:
    def __init__(self):
        self._client: Minio | None = None

    def _get_client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_root_user,
                secret_key=settings.minio_root_password,
                secure=settings.minio_secure,
            )
            self._ensure_buckets()
        return self._client

    def _ensure_buckets(self):
        client = self._client
        for bucket in [settings.minio_bucket_files, settings.minio_bucket_exports]:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)

    async def put_object(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ):
        client = self._get_client()
        client.put_object(
            settings.minio_bucket_files,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    async def get_object(self, key: str) -> bytes:
        client = self._get_client()
        response = client.get_object(settings.minio_bucket_files, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def put_export(self, key: str, data: bytes):
        client = self._get_client()
        client.put_object(
            settings.minio_bucket_exports,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


storage = StorageClient()

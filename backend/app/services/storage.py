"""S3 storage service.

boto3 is synchronous, so each blocking call is offloaded to a worker thread via
``asyncio.to_thread`` to keep the async API non-blocking. The client honours
``AWS_ENDPOINT_URL`` when set, enabling LocalStack for local development.
"""

from __future__ import annotations

import asyncio
import logging

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger("counseliq.storage")


class StorageError(Exception):
    """Raised when an S3 operation fails."""


def _build_client(service_name: str):
    """Create a boto3 client, wiring in a custom endpoint when configured."""
    kwargs: dict[str, object] = {
        "region_name": settings.AWS_REGION,
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    if settings.AWS_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    if settings.AWS_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL
    return boto3.client(service_name, **kwargs)


class S3Service:
    """Thin async wrapper around the S3 client used for document storage."""

    def __init__(self) -> None:
        self._client = _build_client("s3")
        self._bucket = settings.S3_BUCKET_NAME

    async def upload_file(
        self, file_bytes: bytes, s3_key: str, content_type: str
    ) -> str:
        """Upload bytes to S3 and return the stored key."""
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=s3_key,
                Body=file_bytes,
                ContentType=content_type,
            )
        except ClientError as exc:
            logger.error("S3 upload failed for key %s: %s", s3_key, exc)
            raise StorageError(f"Failed to upload {s3_key}") from exc
        return s3_key

    async def generate_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
        """Return a time-limited presigned GET URL for a stored object."""
        try:
            return await asyncio.to_thread(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": s3_key},
                ExpiresIn=expires_in,
            )
        except ClientError as exc:
            logger.error("Presign failed for key %s: %s", s3_key, exc)
            raise StorageError(f"Failed to presign {s3_key}") from exc

    async def delete_file(self, s3_key: str) -> bool:
        """Delete an object. Returns True on success, False if it was missing."""
        try:
            await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=s3_key
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            logger.error("S3 head failed for key %s: %s", s3_key, exc)
            raise StorageError(f"Failed to delete {s3_key}") from exc

        try:
            await asyncio.to_thread(
                self._client.delete_object, Bucket=self._bucket, Key=s3_key
            )
        except ClientError as exc:
            logger.error("S3 delete failed for key %s: %s", s3_key, exc)
            raise StorageError(f"Failed to delete {s3_key}") from exc
        return True

    async def get_file_bytes(self, s3_key: str) -> bytes:
        """Download and return the raw bytes of an object."""
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=s3_key
            )
            return await asyncio.to_thread(response["Body"].read)
        except ClientError as exc:
            logger.error("S3 download failed for key %s: %s", s3_key, exc)
            raise StorageError(f"Failed to download {s3_key}") from exc


s3_service = S3Service()

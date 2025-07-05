"""
S3 client utility for Harness
"""

from typing import BinaryIO

import boto3

from backend.api.config import settings


class S3Client:
    """S3 client for file operations."""

    def __init__(self):
        """Initialize S3 client."""
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )

    async def upload_file(self, file_obj: BinaryIO, bucket: str, key: str) -> bool:
        """Upload file to S3."""
        try:
            self.client.upload_fileobj(file_obj, bucket, key)
            return True
        except Exception:
            return False

    async def download_file(self, bucket: str, key: str) -> bytes | None:
        """Download file from S3."""
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except Exception:
            return None

    async def delete_file(self, bucket: str, key: str) -> bool:
        """Delete file from S3."""
        try:
            self.client.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception:
            return False


# Global S3 client instance
s3_client = S3Client()

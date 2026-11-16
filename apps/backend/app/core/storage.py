"""Object storage behind one interface (ADR 0005): SeaweedFS S3 locally, Cloudflare R2 in staging/production.

Two buckets: `raw` (private, browser uploads land here via presigned PUT) and `public` (validated renditions,
served through the CDN / gateway). The database stores object keys, never URLs or bytes.
"""

from functools import lru_cache
from typing import Any, Protocol

import boto3
from botocore.config import Config

from app.core.config import get_settings

PRESIGN_TTL_S = 600  # 10 minutes (Blueprint 9.1)


class Storage(Protocol):
    def presign_put(self, key: str, content_type: str, max_bytes: int) -> str: ...
    def get_bytes(self, bucket: str, key: str, max_bytes: int) -> bytes: ...
    def put_bytes(self, bucket: str, key: str, data: bytes, content_type: str) -> None: ...
    def delete(self, bucket: str, key: str) -> None: ...
    def public_url(self, key: str) -> str: ...
    @property
    def raw_bucket(self) -> str: ...
    @property
    def public_bucket(self) -> str: ...


class TooLarge(Exception):
    pass


class S3Storage:
    def __init__(self) -> None:
        s = get_settings()
        cfg = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        self._internal: Any = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name=s.s3_region,
            config=cfg,
        )
        # Presigned URLs are signed for the host the browser will use (gateway locally, R2 in production).
        self._presigner: Any = boto3.client(
            "s3",
            endpoint_url=s.s3_presign_endpoint or s.s3_endpoint,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name=s.s3_region,
            config=cfg,
        )
        self._raw, self._public, self._public_base = s.s3_bucket_raw, s.s3_bucket_public, s.media_public_base.rstrip("/")

    @property
    def raw_bucket(self) -> str:
        return self._raw

    @property
    def public_bucket(self) -> str:
        return self._public

    def ensure_buckets(self) -> None:
        existing = {b["Name"] for b in self._internal.list_buckets().get("Buckets", [])}
        for bucket in (self._raw, self._public):
            if bucket not in existing:
                self._internal.create_bucket(Bucket=bucket)

    def presign_put(self, key: str, content_type: str, max_bytes: int) -> str:
        return str(
            self._presigner.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._raw, "Key": key, "ContentType": content_type},
                ExpiresIn=PRESIGN_TTL_S,
            )
        )

    def get_bytes(self, bucket: str, key: str, max_bytes: int) -> bytes:
        head = self._internal.head_object(Bucket=bucket, Key=key)
        if int(head["ContentLength"]) > max_bytes:
            raise TooLarge(key)
        body = self._internal.get_object(Bucket=bucket, Key=key)["Body"]
        return bytes(body.read(max_bytes + 1))

    def put_bytes(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self._internal.put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=content_type, CacheControl="public, max-age=31536000, immutable"
        )

    def delete(self, bucket: str, key: str) -> None:
        self._internal.delete_object(Bucket=bucket, Key=key)

    def public_url(self, key: str) -> str:
        return f"{self._public_base}/{key}"


class MemoryStorage:
    """In-process storage for tests."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    raw_bucket = "raw"
    public_bucket = "public"

    def presign_put(self, key: str, content_type: str, max_bytes: int) -> str:
        return f"memory://raw/{key}?ct={content_type}"

    def get_bytes(self, bucket: str, key: str, max_bytes: int) -> bytes:
        data = self.objects[(bucket, key)][0]
        if len(data) > max_bytes:
            raise TooLarge(key)
        return data

    def put_bytes(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.objects[(bucket, key)] = (data, content_type)

    def delete(self, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)

    def public_url(self, key: str) -> str:
        return f"/media/{key}"


_override: Storage | None = None


@lru_cache(maxsize=1)
def _s3() -> S3Storage:
    return S3Storage()


def get_storage() -> Storage:
    return _override if _override is not None else _s3()


def set_storage_for_tests(storage: Storage | None) -> None:
    global _override
    _override = storage

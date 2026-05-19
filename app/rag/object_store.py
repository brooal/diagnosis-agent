from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from minio import Minio


@dataclass(frozen=True)
class MinioConfig:
    endpoint: str = "127.0.0.1:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "diagnosis-rag"
    secure: bool = False
    region: str | None = None
    raw_prefix: str = "rag/raw"

    @classmethod
    def from_env(cls) -> "MinioConfig":
        return cls(
            endpoint=os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            bucket=os.getenv("MINIO_BUCKET", "diagnosis-rag"),
            secure=_as_bool(os.getenv("MINIO_SECURE"), default=False),
            region=os.getenv("MINIO_REGION") or None,
            raw_prefix=os.getenv("MINIO_RAG_RAW_PREFIX", "rag/raw").strip("/"),
        )


class MinioObjectStore:
    def __init__(
        self,
        config: MinioConfig,
        *,
        client: Minio | None = None,
    ) -> None:
        self.config = config
        self.client = client or Minio(
            endpoint=config.endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            secure=config.secure,
            region=config.region,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.config.bucket):
            self.client.make_bucket(self.config.bucket, location=self.config.region)

    def put_bytes(
        self,
        data: bytes,
        *,
        object_key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        self.ensure_bucket()
        self.client.put_object(
            bucket_name=self.config.bucket,
            object_name=object_key,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
            metadata=metadata,
        )
        return self.object_uri(object_key)

    def put_file(
        self,
        file_path: str | Path,
        *,
        object_key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        path = Path(file_path)
        self.ensure_bucket()
        self.client.fput_object(
            bucket_name=self.config.bucket,
            object_name=object_key,
            file_path=str(path),
            content_type=content_type or guess_content_type(path.name),
            metadata=metadata,
        )
        return self.object_uri(object_key)

    def object_uri(self, object_key: str) -> str:
        return f"minio://{self.config.bucket}/{object_key}"


def build_original_object_key(
    *,
    doc_type: str,
    document_uid: str,
    version: str,
    filename: str,
    prefix: str = "rag/raw",
) -> str:
    safe_doc_type = _sanitize_path_part(doc_type)
    safe_version = _sanitize_path_part(version)
    safe_filename = _sanitize_filename(filename)
    return "/".join(
        [
            prefix.strip("/"),
            safe_doc_type,
            document_uid,
            safe_version,
            safe_filename,
        ]
    )


def guess_content_type(filename: str) -> str:
    if filename.lower().endswith(".md"):
        return "text/markdown"
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(file_path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as file:
        _update_hash(digest, file, chunk_size=chunk_size)
    return digest.hexdigest()


def _update_hash(digest: "hashlib._Hash", file: BinaryIO, *, chunk_size: int) -> None:
    while True:
        chunk = file.read(chunk_size)
        if not chunk:
            break
        digest.update(chunk)


def _sanitize_path_part(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip())
    return cleaned.strip(".-") or "unknown"


def _sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    cleaned = re.sub(r"[^a-zA-Z0-9_.\-\u4e00-\u9fff]+", "-", name.strip())
    return cleaned.strip(".-") or "document"


def _as_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default

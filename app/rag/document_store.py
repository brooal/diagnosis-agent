from __future__ import annotations

from pathlib import Path

from app.rag.models import RagDocumentRecord
from app.rag.object_store import (
    MinioObjectStore,
    build_original_object_key,
    guess_content_type,
    sha256_bytes,
    sha256_file,
)
from app.rag.repository import RagDocumentRepository, new_document_uid


class RagDocumentStore:
    def __init__(
        self,
        *,
        repository: RagDocumentRepository,
        object_store: MinioObjectStore,
    ) -> None:
        self.repository = repository
        self.object_store = object_store

    def save_original_file(
        self,
        file_path: str | Path,
        *,
        doc_type: str,
        title: str | None = None,
        source_type: str = "upload",
        document_uid: str | None = None,
        version: str = "1",
        content_type: str | None = None,
        metadata: dict | None = None,
    ) -> RagDocumentRecord:
        path = Path(file_path)
        document_uid = document_uid or new_document_uid()
        checksum = sha256_file(path)
        object_key = build_original_object_key(
            doc_type=doc_type,
            document_uid=document_uid,
            version=version,
            filename=path.name,
            prefix=self.object_store.config.raw_prefix,
        )
        resolved_content_type = content_type or guess_content_type(path.name)
        source_uri = self.object_store.put_file(
            path,
            object_key=object_key,
            content_type=resolved_content_type,
            metadata=_object_metadata(
                document_uid=document_uid,
                doc_type=doc_type,
                checksum_sha256=checksum,
            ),
        )
        return self.repository.create(
            document_uid=document_uid,
            doc_type=doc_type,
            title=title,
            source_type=source_type,
            source_uri=source_uri,
            object_bucket=self.object_store.config.bucket,
            object_key=object_key,
            original_filename=path.name,
            content_type=resolved_content_type,
            checksum_sha256=checksum,
            version=version,
            status="uploaded",
            metadata=metadata,
        )

    def save_original_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        doc_type: str,
        title: str | None = None,
        source_type: str = "upload",
        document_uid: str | None = None,
        version: str = "1",
        content_type: str | None = None,
        metadata: dict | None = None,
    ) -> RagDocumentRecord:
        document_uid = document_uid or new_document_uid()
        checksum = sha256_bytes(data)
        object_key = build_original_object_key(
            doc_type=doc_type,
            document_uid=document_uid,
            version=version,
            filename=filename,
            prefix=self.object_store.config.raw_prefix,
        )
        resolved_content_type = content_type or guess_content_type(filename)
        source_uri = self.object_store.put_bytes(
            data,
            object_key=object_key,
            content_type=resolved_content_type,
            metadata=_object_metadata(
                document_uid=document_uid,
                doc_type=doc_type,
                checksum_sha256=checksum,
            ),
        )
        return self.repository.create(
            document_uid=document_uid,
            doc_type=doc_type,
            title=title,
            source_type=source_type,
            source_uri=source_uri,
            object_bucket=self.object_store.config.bucket,
            object_key=object_key,
            original_filename=filename,
            content_type=resolved_content_type,
            checksum_sha256=checksum,
            version=version,
            status="uploaded",
            metadata=metadata,
        )


def _object_metadata(
    *,
    document_uid: str,
    doc_type: str,
    checksum_sha256: str,
) -> dict[str, str]:
    return {
        "document_uid": document_uid,
        "doc_type": doc_type,
        "checksum_sha256": checksum_sha256,
    }

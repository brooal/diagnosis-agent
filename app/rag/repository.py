from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.rag.models import RagDocumentRecord
from app.utils.times import now_shanghai


def new_document_uid() -> str:
    return f"ragdoc_{uuid4().hex[:12]}"


class RagDocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        doc_type: str,
        source_type: str,
        source_uri: str,
        checksum_sha256: str,
        document_uid: str | None = None,
        title: str | None = None,
        object_bucket: str | None = None,
        object_key: str | None = None,
        original_filename: str | None = None,
        content_type: str | None = None,
        version: str = "1",
        status: str = "uploaded",
        metadata: dict | None = None,
    ) -> RagDocumentRecord:
        row = RagDocumentRecord(
            document_uid=document_uid or new_document_uid(),
            doc_type=doc_type,
            title=title,
            source_type=source_type,
            source_uri=source_uri,
            object_bucket=object_bucket,
            object_key=object_key,
            original_filename=original_filename,
            content_type=content_type,
            checksum_sha256=checksum_sha256,
            version=version,
            status=status,
            metadata_json=metadata or {},
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self, document_uid: str) -> RagDocumentRecord | None:
        return (
            self.db.query(RagDocumentRecord)
            .filter(RagDocumentRecord.document_uid == document_uid)
            .one_or_none()
        )

    def find_by_checksum(
        self,
        checksum_sha256: str,
        *,
        doc_type: str | None = None,
    ) -> list[RagDocumentRecord]:
        query = self.db.query(RagDocumentRecord).filter(
            RagDocumentRecord.checksum_sha256 == checksum_sha256
        )
        if doc_type:
            query = query.filter(RagDocumentRecord.doc_type == doc_type)
        return query.order_by(RagDocumentRecord.id.desc()).all()

    def list_by_status(self, status: str, *, limit: int = 100) -> list[RagDocumentRecord]:
        return (
            self.db.query(RagDocumentRecord)
            .filter(RagDocumentRecord.status == status)
            .order_by(RagDocumentRecord.id.asc())
            .limit(limit)
            .all()
        )

    def update_status(
        self,
        document_uid: str,
        *,
        status: str,
        error: str | None = None,
    ) -> RagDocumentRecord:
        row = self._require(document_uid)
        row.status = status
        row.error = error
        row.updated_at = now_shanghai()
        self.db.commit()
        self.db.refresh(row)
        return row

    def mark_indexed(
        self,
        document_uid: str,
        *,
        qdrant_collection: str,
        chunk_count: int,
        embedding_model: str,
        embedding_dimension: int,
        sparse_model: str,
        parser_version: str | None = None,
        chunker_version: str | None = None,
    ) -> RagDocumentRecord:
        row = self._require(document_uid)
        row.status = "indexed"
        row.qdrant_collection = qdrant_collection
        row.chunk_count = chunk_count
        row.embedding_model = embedding_model
        row.embedding_dimension = embedding_dimension
        row.sparse_model = sparse_model
        row.parser_version = parser_version
        row.chunker_version = chunker_version
        row.error = None
        row.updated_at = now_shanghai()
        self.db.commit()
        self.db.refresh(row)
        return row

    def _require(self, document_uid: str) -> RagDocumentRecord:
        row = self.get(document_uid)
        if row is None:
            raise ValueError(f"Unknown RAG document: {document_uid}")
        return row

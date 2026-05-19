from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.rag.document_store import RagDocumentStore
from app.rag.models import RagDocumentRecord
from app.rag.object_store import (
    MinioConfig,
    MinioObjectStore,
    build_original_object_key,
    sha256_bytes,
)
from app.rag.repository import RagDocumentRepository


class FakeMinioClient:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], dict] = {}

    def bucket_exists(self, bucket_name: str) -> bool:
        return bucket_name in self.buckets

    def make_bucket(self, bucket_name: str, location: str | None = None) -> None:
        self.buckets.add(bucket_name)

    def put_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data,
        length: int,
        content_type: str,
        metadata: dict | None = None,
    ) -> None:
        self.objects[(bucket_name, object_name)] = {
            "data": data.read(length),
            "content_type": content_type,
            "metadata": metadata,
        }

    def fput_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        file_path: str,
        content_type: str,
        metadata: dict | None = None,
    ) -> None:
        self.objects[(bucket_name, object_name)] = {
            "data": Path(file_path).read_bytes(),
            "content_type": content_type,
            "metadata": metadata,
        }


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_build_original_object_key_sanitizes_path_parts() -> None:
    key = build_original_object_key(
        doc_type="system/design document",
        document_uid="ragdoc_1",
        version="v 1",
        filename="../联锁 设计.pdf",
    )

    assert key == "rag/raw/system-design-document/ragdoc_1/v-1/联锁-设计.pdf"


def test_minio_config_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("MINIO_ENDPOINT", "minio.example:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "access")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    monkeypatch.setenv("MINIO_BUCKET", "rag-bucket")
    monkeypatch.setenv("MINIO_SECURE", "true")
    monkeypatch.setenv("MINIO_REGION", "cn-north-1")
    monkeypatch.setenv("MINIO_RAG_RAW_PREFIX", "custom/raw")

    config = MinioConfig.from_env()

    assert config.endpoint == "minio.example:9000"
    assert config.access_key == "access"
    assert config.secret_key == "secret"
    assert config.bucket == "rag-bucket"
    assert config.secure is True
    assert config.region == "cn-north-1"
    assert config.raw_prefix == "custom/raw"


def test_document_store_saves_original_bytes_to_minio_and_db() -> None:
    db = _session()
    fake_client = FakeMinioClient()
    object_store = MinioObjectStore(
        MinioConfig(bucket="diagnosis-rag", raw_prefix="rag/raw"),
        client=fake_client,
    )
    document_store = RagDocumentStore(
        repository=RagDocumentRepository(db),
        object_store=object_store,
    )
    content = "# 人工诊断经验".encode()

    record = document_store.save_original_bytes(
        content,
        filename="case.md",
        doc_type="human_diagnosis_case",
        title="人工诊断案例",
        document_uid="ragdoc_test",
        metadata={"domain": "beam"},
    )

    object_key = "rag/raw/human_diagnosis_case/ragdoc_test/1/case.md"
    assert record.document_uid == "ragdoc_test"
    assert record.source_uri == f"minio://diagnosis-rag/{object_key}"
    assert record.object_bucket == "diagnosis-rag"
    assert record.object_key == object_key
    assert record.status == "uploaded"
    assert record.chunk_count == 0
    assert record.checksum_sha256 == sha256_bytes(content)
    assert record.metadata_json == {"domain": "beam"}

    saved_object = fake_client.objects[("diagnosis-rag", object_key)]
    assert saved_object["data"] == content
    assert saved_object["content_type"] == "text/markdown"
    assert saved_object["metadata"]["document_uid"] == "ragdoc_test"

    persisted = db.query(RagDocumentRecord).filter_by(document_uid="ragdoc_test").one()
    assert persisted.source_uri == record.source_uri


def test_repository_marks_document_indexed() -> None:
    db = _session()
    repository = RagDocumentRepository(db)
    record = repository.create(
        document_uid="ragdoc_index",
        doc_type="agent_case_summary",
        source_type="agent_case",
        source_uri="diagnosis_case:case_1",
        checksum_sha256="0" * 64,
    )

    updated = repository.mark_indexed(
        record.document_uid,
        qdrant_collection="diagnosis_rag",
        chunk_count=3,
        embedding_model="BAAI/bge-m3",
        embedding_dimension=1024,
        sparse_model="Qdrant/bm25",
        parser_version="v1",
        chunker_version="v1",
    )

    assert updated.status == "indexed"
    assert updated.qdrant_collection == "diagnosis_rag"
    assert updated.chunk_count == 3
    assert updated.embedding_model == "BAAI/bge-m3"

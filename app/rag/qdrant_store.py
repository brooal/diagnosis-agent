from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.rag.embeddings import SparseEmbedding
from app.rag.schemas import RagChunk, RagSearchResult

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


@dataclass(frozen=True)
class QdrantStoreConfig:
    collection_name: str = "diagnosis_rag"
    vector_size: int = 1024
    distance: models.Distance = models.Distance.COSINE
    sparse_modifier: models.Modifier = models.Modifier.IDF
    url: str | None = None
    api_key: str | None = None
    path: str | None = ".qdrant"

    @classmethod
    def from_env(cls) -> "QdrantStoreConfig":
        return cls(
            collection_name=os.getenv("QDRANT_COLLECTION", "diagnosis_rag"),
            vector_size=int(
                os.getenv(
                    "QDRANT_VECTOR_SIZE",
                    os.getenv("RAG_EMBEDDING_DIMENSION", "1024"),
                )
            ),
            url=os.getenv("QDRANT_URL") or None,
            api_key=os.getenv("QDRANT_API_KEY") or None,
            path=os.getenv("QDRANT_PATH", ".qdrant") or None,
        )


class QdrantRagStore:
    def __init__(
        self,
        config: QdrantStoreConfig,
        *,
        client: QdrantClient | None = None,
    ) -> None:
        self.config = config
        self.client = client or self._build_client(config)

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.config.collection_name):
            return
        self.client.create_collection(
            collection_name=self.config.collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=self.config.vector_size,
                    distance=self.config.distance,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: models.SparseVectorParams(
                    modifier=self.config.sparse_modifier,
                )
            },
        )

    def recreate_collection(self) -> None:
        if self.client.collection_exists(self.config.collection_name):
            self.client.delete_collection(self.config.collection_name)
        self.ensure_collection()

    def upsert_chunks(
        self,
        chunks: list[RagChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[SparseEmbedding],
    ) -> None:
        if len(chunks) != len(dense_vectors) or len(chunks) != len(sparse_vectors):
            raise ValueError("chunks, dense_vectors and sparse_vectors must have the same length.")
        self.ensure_collection()
        points = [
            models.PointStruct(
                id=chunk.chunk_id,
                vector={
                    DENSE_VECTOR_NAME: dense_vector,
                    SPARSE_VECTOR_NAME: _to_qdrant_sparse_vector(sparse_vector),
                },
                payload={
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "source": chunk.source,
                    "metadata": chunk.metadata,
                },
            )
            for chunk, dense_vector, sparse_vector in zip(
                chunks,
                dense_vectors,
                sparse_vectors,
                strict=True,
            )
        ]
        if points:
            self.client.upsert(
                collection_name=self.config.collection_name,
                points=points,
            )

    def search(
        self,
        query_vector: list[float],
        *,
        limit: int = 5,
        metadata_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[RagSearchResult]:
        self.ensure_collection()
        response = self.client.query_points(
            collection_name=self.config.collection_name,
            query=query_vector,
            using=DENSE_VECTOR_NAME,
            limit=limit,
            query_filter=_build_filter(metadata_filter),
            with_payload=True,
            score_threshold=score_threshold,
        )
        results: list[RagSearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                RagSearchResult(
                    chunk_id=str(payload.get("chunk_id") or point.id),
                    document_id=str(payload.get("document_id") or ""),
                    text=str(payload.get("text") or ""),
                    score=float(point.score),
                    source=payload.get("source"),
                    metadata=dict(payload.get("metadata") or {}),
                )
            )
        return results

    def sparse_search(
        self,
        query_vector: SparseEmbedding,
        *,
        metadata_filter: dict[str, Any] | None = None,
        limit: int = 5,
        score_threshold: float | None = None,
    ) -> list[RagSearchResult]:
        self.ensure_collection()
        if not query_vector.indices:
            return []
        response = self.client.query_points(
            collection_name=self.config.collection_name,
            query=_to_qdrant_sparse_vector(query_vector),
            using=SPARSE_VECTOR_NAME,
            limit=limit,
            query_filter=_build_filter(metadata_filter),
            with_payload=True,
            score_threshold=score_threshold,
        )
        results: list[RagSearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                RagSearchResult(
                    chunk_id=str(payload.get("chunk_id") or point.id),
                    document_id=str(payload.get("document_id") or ""),
                    text=str(payload.get("text") or ""),
                    score=float(point.score),
                    source=payload.get("source"),
                    metadata=dict(payload.get("metadata") or {}),
                )
            )
        return results

    def delete_collection(self) -> None:
        if self.client.collection_exists(self.config.collection_name):
            self.client.delete_collection(self.config.collection_name)

    def _build_client(self, config: QdrantStoreConfig) -> QdrantClient:
        if config.url:
            return QdrantClient(url=config.url, api_key=config.api_key)
        if config.path == ":memory:":
            return QdrantClient(":memory:")
        return QdrantClient(path=config.path)


def _build_filter(metadata_filter: dict[str, Any] | None) -> models.Filter | None:
    if not metadata_filter:
        return None
    conditions = [
        models.FieldCondition(
            key=f"metadata.{key}",
            match=models.MatchValue(value=value),
        )
        for key, value in metadata_filter.items()
    ]
    return models.Filter(must=conditions)


def _to_qdrant_sparse_vector(vector: SparseEmbedding) -> models.SparseVector:
    return models.SparseVector(indices=vector.indices, values=vector.values)

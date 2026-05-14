from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from app.rag.embeddings import (
    EmbeddingProvider,
    HashingSparseEmbeddingProvider,
    SparseEmbeddingProvider,
)
from app.rag.qdrant_store import QdrantRagStore
from app.rag.schemas import RagChunk, RagDocument, RagSearchResult

HUMAN_DIAGNOSIS_CASE = "human_diagnosis_case"
SYSTEM_DESIGN_DOCUMENT = "system_design_document"
AGENT_CASE_SUMMARY = "agent_case_summary"


class RagService:
    def __init__(
        self,
        *,
        store: QdrantRagStore,
        embeddings: EmbeddingProvider,
        sparse_embeddings: SparseEmbeddingProvider | None = None,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        self.store = store
        self.embeddings = embeddings
        self.sparse_embeddings = sparse_embeddings or HashingSparseEmbeddingProvider()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def initialize(self, *, recreate: bool = False) -> None:
        if recreate:
            self.store.recreate_collection()
            return
        self.store.ensure_collection()

    def index_documents(self, documents: Iterable[RagDocument]) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        for document in documents:
            chunks.extend(self.chunk_document(document))
        texts = [chunk.text for chunk in chunks]
        dense_vectors = self.embeddings.embed_texts(texts)
        sparse_vectors = self.sparse_embeddings.embed_texts(texts)
        self.store.upsert_chunks(chunks, dense_vectors, sparse_vectors)
        return chunks

    def chunk_document(self, document: RagDocument) -> list[RagChunk]:
        text = document.text.strip()
        if not text:
            return []

        chunks: list[RagChunk] = []
        start = 0
        index = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunk_id = _stable_chunk_id(document.document_id, index, chunk_text)
                chunks.append(
                    RagChunk(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        text=chunk_text,
                        source=document.source,
                        metadata={
                            **document.metadata,
                            "chunk_index": index,
                        },
                    )
                )
                index += 1
            if end >= len(text):
                break
            start = max(end - self.chunk_overlap, start + 1)
        return chunks

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        include_system_design: bool = False,
        metadata_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[RagSearchResult]:
        if limit <= 0 or limit % 5 != 0:
            raise ValueError("RAG search limit must be a positive multiple of 5.")

        dense_vector = self.embeddings.embed_query(query)
        sparse_vector = self.sparse_embeddings.embed_query(query)
        doc_type_limits = _allocate_doc_type_limits(
            limit=limit,
            include_system_design=include_system_design,
        )

        results: list[RagSearchResult] = []
        for doc_type, doc_type_limit in doc_type_limits:
            doc_type_filter = _with_doc_type(metadata_filter, doc_type)
            dense_results = self.store.search(
                dense_vector,
                limit=limit,
                metadata_filter=doc_type_filter,
                score_threshold=score_threshold,
            )
            sparse_results = self.store.sparse_search(
                sparse_vector,
                limit=limit,
                metadata_filter=doc_type_filter,
                score_threshold=score_threshold,
            )
            fused_results = _rrf_fuse(
                rankings=[dense_results, sparse_results],
                limit=doc_type_limit,
            )
            results.extend(fused_results)

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]


def _allocate_doc_type_limits(
    *,
    limit: int,
    include_system_design: bool,
) -> list[tuple[str, int]]:
    if include_system_design:
        return _allocate_by_weights(
            limit=limit,
            weights=[
                (HUMAN_DIAGNOSIS_CASE, 1),
                (SYSTEM_DESIGN_DOCUMENT, 3),
                (AGENT_CASE_SUMMARY, 1),
            ],
        )
    return _allocate_by_weights(
        limit=limit,
        weights=[
            (HUMAN_DIAGNOSIS_CASE, 3),
            (AGENT_CASE_SUMMARY, 2),
        ],
    )


def _with_doc_type(
    metadata_filter: dict[str, Any] | None,
    doc_type: str,
) -> dict[str, Any]:
    merged = dict(metadata_filter or {})
    merged["doc_type"] = doc_type
    return merged


def _allocate_by_weights(
    *,
    limit: int,
    weights: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    total_weight = sum(weight for _, weight in weights)
    raw = [(doc_type, limit * weight / total_weight) for doc_type, weight in weights]
    allocations = [(doc_type, int(value)) for doc_type, value in raw]
    allocated = sum(value for _, value in allocations)

    remainders = sorted(
        [
            (raw_value - int(raw_value), index)
            for index, (_, raw_value) in enumerate(raw)
        ],
        reverse=True,
    )
    remainder_index = 0
    while allocated < limit:
        _, index = remainders[remainder_index % len(remainders)]
        doc_type, value = allocations[index]
        allocations[index] = (doc_type, value + 1)
        allocated += 1
        remainder_index += 1

    if limit >= len(weights):
        for index, (doc_type, value) in enumerate(allocations):
            if value == 0:
                donor_index = max(
                    range(len(allocations)),
                    key=lambda item: allocations[item][1],
                )
                donor_type, donor_value = allocations[donor_index]
                if donor_value <= 1:
                    continue
                allocations[donor_index] = (donor_type, donor_value - 1)
                allocations[index] = (doc_type, 1)
    return allocations


def _rrf_fuse(
    *,
    rankings: list[list[RagSearchResult]],
    limit: int,
    k: int = 60,
) -> list[RagSearchResult]:
    by_chunk_id: dict[str, RagSearchResult] = {}
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, result in enumerate(ranking, start=1):
            by_chunk_id.setdefault(result.chunk_id, result)
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (k + rank)

    fused = [
        RagSearchResult(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            text=result.text,
            score=scores[result.chunk_id],
            source=result.source,
            metadata=result.metadata,
        )
        for result in by_chunk_id.values()
    ]
    fused.sort(key=lambda item: item.score, reverse=True)
    return fused[:limit]


def _stable_chunk_id(document_id: str, index: int, text: str) -> str:
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, document_id)
    return str(uuid.uuid5(namespace, f"{index}:{text}"))

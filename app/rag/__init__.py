from app.rag.document_processor import RagDocumentProcessor
from app.rag.document_store import RagDocumentStore
from app.rag.embeddings import (
    EmbeddingConfig,
    EmbeddingProvider,
    FastEmbedBM25SparseEmbeddingProvider,
    HashingEmbeddingProvider,
    HashingSparseEmbeddingProvider,
    OpenAIEmbeddingProvider,
    SparseEmbedding,
    SparseEmbeddingConfig,
    SparseEmbeddingProvider,
    build_embedding_provider,
    build_sparse_embedding_provider,
)
from app.rag.models import RagDocumentRecord
from app.rag.object_store import (
    MinioConfig,
    MinioObjectStore,
    build_original_object_key,
    guess_content_type,
    sha256_bytes,
    sha256_file,
)
from app.rag.qdrant_store import QdrantRagStore, QdrantStoreConfig
from app.rag.repository import RagDocumentRepository
from app.rag.schemas import RagChunk, RagDocument, RagSearchResult
from app.rag.service import RagService


def build_rag_service() -> RagService:
    dense_embeddings = build_embedding_provider()
    sparse_embeddings = build_sparse_embedding_provider()
    store = QdrantRagStore(QdrantStoreConfig.from_env())
    return RagService(
        store=store,
        embeddings=dense_embeddings,
        sparse_embeddings=sparse_embeddings,
    )

__all__ = [
    "EmbeddingProvider",
    "EmbeddingConfig",
    "SparseEmbedding",
    "SparseEmbeddingProvider",
    "SparseEmbeddingConfig",
    "HashingEmbeddingProvider",
    "HashingSparseEmbeddingProvider",
    "FastEmbedBM25SparseEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "RagDocumentProcessor",
    "RagDocumentStore",
    "RagDocumentRecord",
    "RagDocumentRepository",
    "MinioConfig",
    "MinioObjectStore",
    "QdrantRagStore",
    "QdrantStoreConfig",
    "RagChunk",
    "RagDocument",
    "RagSearchResult",
    "RagService",
    "build_rag_service",
    "build_embedding_provider",
    "build_sparse_embedding_provider",
    "build_original_object_key",
    "guess_content_type",
    "sha256_bytes",
    "sha256_file",
]

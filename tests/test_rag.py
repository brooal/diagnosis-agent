from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag import (
    EmbeddingConfig,
    HashingEmbeddingProvider,
    HashingSparseEmbeddingProvider,
    QdrantRagStore,
    QdrantStoreConfig,
    RagDocumentProcessor,
    RagDocument,
    RagService,
    build_embedding_provider,
    build_sparse_embedding_provider,
)
from app.rag.embeddings import SparseEmbeddingConfig
from app.rag.schemas import RagSearchResult


def test_rag_service_indexes_and_searches_documents() -> None:
    embeddings = HashingEmbeddingProvider(dimension=64)
    store = QdrantRagStore(
        QdrantStoreConfig(
            collection_name="test_rag",
            vector_size=embeddings.dimension,
            path=":memory:",
        )
    )
    service = RagService(
        store=store,
        embeddings=embeddings,
        chunk_size=80,
        chunk_overlap=10,
    )

    service.initialize(recreate=True)
    chunks = service.index_documents(
        [
            RagDocument(
                document_id="beam_doc",
                text="束流掉束通常表现为 beam current 在短时间内快速下降。",
                source="manual",
                metadata={"domain": "beam", "doc_type": "human_diagnosis_case"},
            ),
            RagDocument(
                document_id="power_doc",
                text="四极铁电源异常可以通过 power current PV 的跌落来定位。",
                source="manual",
                metadata={"domain": "power", "doc_type": "agent_case_summary"},
            ),
        ]
    )

    assert len(chunks) == 2
    results = service.search("beam current 快速下降", limit=5)

    assert results
    assert results[0].document_id == "beam_doc"
    assert results[0].metadata["domain"] == "beam"


def test_rag_service_supports_metadata_filter() -> None:
    embeddings = HashingEmbeddingProvider(dimension=64)
    store = QdrantRagStore(
        QdrantStoreConfig(
            collection_name="test_rag_filter",
            vector_size=embeddings.dimension,
            path=":memory:",
        )
    )
    service = RagService(store=store, embeddings=embeddings)
    service.initialize(recreate=True)
    service.index_documents(
        [
            RagDocument(
                document_id="beam_doc",
                text="beam current drop",
                metadata={"domain": "beam", "doc_type": "human_diagnosis_case"},
            ),
            RagDocument(
                document_id="power_doc",
                text="power current drop",
                metadata={"domain": "power", "doc_type": "agent_case_summary"},
            ),
        ]
    )

    results = service.search(
        "current drop",
        limit=5,
        metadata_filter={"domain": "power"},
    )

    assert results
    assert {result.document_id for result in results} == {"power_doc"}


def test_rag_search_uses_doc_type_allocation_without_system_design() -> None:
    service = _build_test_service("test_rag_allocation_without_system")
    service.index_documents(
        [
            *[
                RagDocument(
                    document_id=f"human_{index}",
                    text=f"beam trip human diagnosis case {index}",
                    metadata={"doc_type": "human_diagnosis_case"},
                )
                for index in range(4)
            ],
            *[
                RagDocument(
                    document_id=f"agent_{index}",
                    text=f"beam trip agent case summary {index}",
                    metadata={"doc_type": "agent_case_summary"},
                )
                for index in range(4)
            ],
            RagDocument(
                document_id="system_0",
                text="beam trip system design document",
                metadata={"doc_type": "system_design_document"},
            ),
        ]
    )

    results = service.search("beam trip", limit=5)
    doc_types = [result.metadata["doc_type"] for result in results]

    assert len(results) == 5
    assert doc_types.count("human_diagnosis_case") == 3
    assert doc_types.count("agent_case_summary") == 2
    assert "system_design_document" not in doc_types


def test_rag_search_uses_doc_type_allocation_with_system_design() -> None:
    service = _build_test_service("test_rag_allocation_with_system")
    service.index_documents(
        [
            *[
                RagDocument(
                    document_id=f"human_{index}",
                    text=f"interlock human diagnosis case {index}",
                    metadata={"doc_type": "human_diagnosis_case"},
                )
                for index in range(3)
            ],
            *[
                RagDocument(
                    document_id=f"system_{index}",
                    text=f"interlock system design document {index}",
                    metadata={"doc_type": "system_design_document"},
                )
                for index in range(8)
            ],
            *[
                RagDocument(
                    document_id=f"agent_{index}",
                    text=f"interlock agent case summary {index}",
                    metadata={"doc_type": "agent_case_summary"},
                )
                for index in range(3)
            ],
        ]
    )

    results = service.search("interlock", limit=10, include_system_design=True)
    doc_types = [result.metadata["doc_type"] for result in results]

    assert len(results) == 10
    assert doc_types.count("human_diagnosis_case") == 1
    assert doc_types.count("system_design_document") == 8
    assert doc_types.count("agent_case_summary") == 1


def test_rag_search_requires_limit_multiple_of_five() -> None:
    service = _build_test_service("test_rag_limit_validation")

    try:
        service.search("beam trip", limit=6)
    except ValueError as exc:
        assert "multiple of 5" in str(exc)
    else:
        raise AssertionError("Expected limit validation error.")


def test_rag_search_retrieves_limit_candidates_per_doc_type_before_rrf() -> None:
    embeddings = HashingEmbeddingProvider(dimension=8)
    sparse_embeddings = HashingSparseEmbeddingProvider(dimension=128)
    store = FakeHybridStore()
    service = RagService(
        store=store,
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
    )

    results = service.search("beam trip unique keyword", limit=10, include_system_design=True)

    assert store.dense_limits == [
        ("human_diagnosis_case", 10),
        ("system_design_document", 10),
        ("agent_case_summary", 10),
    ]
    assert store.sparse_limits == [
        ("human_diagnosis_case", 10),
        ("system_design_document", 10),
        ("agent_case_summary", 10),
    ]
    doc_types = [result.metadata["doc_type"] for result in results]
    assert doc_types.count("human_diagnosis_case") == 1
    assert doc_types.count("system_design_document") == 8
    assert doc_types.count("agent_case_summary") == 1
    assert any("keyword" in result.text for result in results)


def test_embedding_provider_uses_env_dimension_and_model(monkeypatch) -> None:
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("RAG_EMBEDDING_DIMENSION", "1024")

    config = EmbeddingConfig.from_env()
    provider = build_embedding_provider(config)

    assert provider.model == "BAAI/bge-m3"
    assert provider.dimension == 1024
    assert len(provider.embed_query("束流掉束")) == 1024


def test_sparse_embedding_provider_uses_env_model_and_hashing_provider(monkeypatch) -> None:
    monkeypatch.setenv("RAG_SPARSE_EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setenv("RAG_SPARSE_EMBEDDING_MODEL", "Qdrant/bm25")
    monkeypatch.setenv("RAG_SPARSE_EMBEDDING_DIMENSION", "1024")

    config = SparseEmbeddingConfig.from_env()
    provider = build_sparse_embedding_provider(config)
    vector = provider.embed_query("beam trip 掉束")

    assert provider.model == "Qdrant/bm25"
    assert vector.indices
    assert len(vector.indices) == len(vector.values)
    assert max(vector.indices) < 1024


def test_document_processor_builds_three_document_types() -> None:
    processor = RagDocumentProcessor()

    human_case = processor.process_human_diagnosis_case(
        case_id="case_1",
        text="人工经验: 束流掉束后检查四极铁电源。",
        source="case.md",
        metadata={"fault_type": "beam_trip"},
    )
    design_docs = processor.process_system_design_document(
        document_id="interlock_design",
        source="interlock.pdf",
        metadata={"system": "personnel_safety_interlock"},
        sections=[
            {
                "section_id": "sec_1",
                "title": "联锁逻辑",
                "page_start": 1,
                "page_end": 2,
                "text": "人身安全联锁系统开发设计说明。",
            }
        ],
    )
    agent_case = processor.process_agent_case_summary(
        case_uid="case_agent_1",
        user_query="诊断这段时间的束流状态",
        final_answer="检测到束流掉束。",
        candidate_causes=[{"cause_type": "beam_trip"}],
        tools_used=["fetch_beam_samples"],
        skills_used=["beam_state_diagnosis"],
    )

    assert human_case[0].metadata["doc_type"] == "human_diagnosis_case"
    assert human_case[0].metadata["chunk_strategy"] == "case"
    assert design_docs[0].metadata["doc_type"] == "system_design_document"
    assert design_docs[0].metadata["chunk_strategy"] == "section"
    assert agent_case[0].metadata["doc_type"] == "agent_case_summary"
    assert agent_case[0].metadata["chunk_strategy"] == "summary_card"


def _build_test_service(collection_name: str) -> RagService:
    embeddings = HashingEmbeddingProvider(dimension=64)
    store = QdrantRagStore(
        QdrantStoreConfig(
            collection_name=collection_name,
            vector_size=embeddings.dimension,
            path=":memory:",
        )
    )
    service = RagService(store=store, embeddings=embeddings)
    service.initialize(recreate=True)
    return service


class FakeHybridStore:
    def __init__(self) -> None:
        self.dense_limits: list[tuple[str, int]] = []
        self.sparse_limits: list[tuple[str, int]] = []

    def search(
        self,
        query_vector,
        *,
        limit: int,
        metadata_filter,
        score_threshold=None,
    ) -> list[RagSearchResult]:
        doc_type = metadata_filter["doc_type"]
        self.dense_limits.append((doc_type, limit))
        return [
            RagSearchResult(
                chunk_id=f"vector_{doc_type}_{index}",
                document_id=f"vector_{doc_type}_{index}",
                text=f"vector only {doc_type} {index}",
                score=1.0 / (index + 1),
                metadata={"doc_type": doc_type},
            )
            for index in range(limit)
        ]

    def sparse_search(
        self,
        query_vector,
        *,
        metadata_filter,
        limit: int,
        score_threshold=None,
    ) -> list[RagSearchResult]:
        doc_type = metadata_filter["doc_type"]
        self.sparse_limits.append((doc_type, limit))
        return [
            RagSearchResult(
                chunk_id=f"bm25_{doc_type}_{index}",
                document_id=f"bm25_{doc_type}_{index}",
                text=(
                    f"beam trip unique keyword {doc_type} {index}"
                    if index == 0
                    else f"unrelated {doc_type} {index}"
                ),
                score=0.0,
                metadata={"doc_type": doc_type},
            )
            for index in range(limit)
        ]

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from collections import Counter
from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


@dataclass(frozen=True)
class SparseEmbedding:
    indices: list[int]
    values: list[float]


class SparseEmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...

    def embed_texts(self, texts: list[str]) -> list[SparseEmbedding]: ...

    def embed_query(self, text: str) -> SparseEmbedding:
        return self.embed_texts([text])[0]


class HashingEmbeddingProvider:
    def __init__(self, dimension: int = 1024, model: str = "BAAI/bge-m3") -> None:
        self._dimension = dimension
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class HashingSparseEmbeddingProvider:
    def __init__(
        self,
        *,
        dimension: int = 1_048_576,
        model: str = "Qdrant/bm25",
    ) -> None:
        self._dimension = dimension
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def embed_texts(self, texts: list[str]) -> list[SparseEmbedding]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> SparseEmbedding:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> SparseEmbedding:
        counts: Counter[int] = Counter()
        for token in _tokenize_sparse_text(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self._dimension
            counts[index] += 1

        if not counts:
            return SparseEmbedding(indices=[], values=[])

        indices = sorted(counts)
        values = [1.0 + math.log(counts[index]) for index in indices]
        return SparseEmbedding(indices=indices, values=values)


class FastEmbedBM25SparseEmbeddingProvider:
    def __init__(self, *, model: str = "Qdrant/bm25") -> None:
        try:
            from fastembed import SparseTextEmbedding
        except ImportError as exc:
            raise ImportError(
                "fastembed is required for RAG_SPARSE_EMBEDDING_PROVIDER=fastembed. "
                "Keep the provider as 'hashing' in this environment, or install fastembed."
            ) from exc

        self._model = model
        self._embedder = SparseTextEmbedding(model_name=model)

    @property
    def model(self) -> str:
        return self._model

    def embed_texts(self, texts: list[str]) -> list[SparseEmbedding]:
        return [_to_sparse_embedding(item) for item in self._embedder.embed(texts)]

    def embed_query(self, text: str) -> SparseEmbedding:
        return self.embed_texts([text])[0]


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        from openai import OpenAI

        self.model = model
        self._dimension = dimension
        self.client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [list(item.embedding) for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "hashing"
    model: str = "BAAI/bge-m3"
    dimension: int = 1024

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        return cls(
            provider=os.getenv("RAG_EMBEDDING_PROVIDER", "hashing"),
            model=os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-m3"),
            dimension=int(os.getenv("RAG_EMBEDDING_DIMENSION", "1024")),
        )


@dataclass(frozen=True)
class SparseEmbeddingConfig:
    provider: str = "hashing"
    model: str = "Qdrant/bm25"
    dimension: int = 1_048_576

    @classmethod
    def from_env(cls) -> "SparseEmbeddingConfig":
        return cls(
            provider=os.getenv("RAG_SPARSE_EMBEDDING_PROVIDER", "hashing"),
            model=os.getenv("RAG_SPARSE_EMBEDDING_MODEL", "Qdrant/bm25"),
            dimension=int(os.getenv("RAG_SPARSE_EMBEDDING_DIMENSION", "1048576")),
        )


def build_embedding_provider(config: EmbeddingConfig | None = None) -> EmbeddingProvider:
    config = config or EmbeddingConfig.from_env()
    provider = config.provider.lower()
    if provider == "hashing":
        return HashingEmbeddingProvider(dimension=config.dimension, model=config.model)
    if provider == "openai":
        return OpenAIEmbeddingProvider(model=config.model, dimension=config.dimension)
    if provider in {"bge-m3", "local"}:
        raise NotImplementedError(
            "Local BGE-M3 embedding is configured but not implemented in this environment."
        )
    raise ValueError(f"Unknown RAG embedding provider: {config.provider}")


def build_sparse_embedding_provider(
    config: SparseEmbeddingConfig | None = None,
) -> SparseEmbeddingProvider:
    config = config or SparseEmbeddingConfig.from_env()
    provider = config.provider.lower()
    if provider == "hashing":
        return HashingSparseEmbeddingProvider(
            dimension=config.dimension,
            model=config.model,
        )
    if provider in {"fastembed", "qdrant-bm25", "bm25"}:
        return FastEmbedBM25SparseEmbeddingProvider(model=config.model)
    raise ValueError(f"Unknown RAG sparse embedding provider: {config.provider}")


def _tokenize_sparse_text(text: str) -> list[str]:
    ascii_tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    chinese_bigrams = [
        "".join(chinese_chars[index : index + 2])
        for index in range(len(chinese_chars) - 1)
    ]
    return ascii_tokens + chinese_chars + chinese_bigrams


def _to_sparse_embedding(item: object) -> SparseEmbedding:
    indices = getattr(item, "indices", None)
    values = getattr(item, "values", None)
    if indices is None and isinstance(item, dict):
        indices = item.get("indices")
        values = item.get("values")
    if indices is None or values is None:
        raise TypeError(f"Unsupported sparse embedding object: {type(item)!r}")
    return SparseEmbedding(
        indices=[int(index) for index in indices],
        values=[float(value) for value in values],
    )

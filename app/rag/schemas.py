from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RagDocument:
    document_id: str
    text: str
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    document_id: str
    text: str
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RagSearchResult:
    chunk_id: str
    document_id: str
    text: str
    score: float
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

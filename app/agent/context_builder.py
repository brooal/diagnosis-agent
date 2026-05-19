from __future__ import annotations

from typing import Any

from app.harness.service import HarnessService
from app.rag.service import RagService


def build_runtime_context(
    harness: HarnessService,
    *,
    thread_uid: str,
    current_turn_uid: str | None = None,
    max_turns: int = 10,
) -> dict[str, Any]:
    recent_turns = harness.get_recent_turns(
        thread_uid=thread_uid,
        limit=max_turns,
        exclude_turn_uid=current_turn_uid,
    )
    return {
        "recent_turns": [
            {
                "turn_uid": turn.turn_uid,
                "role": turn.role,
                "content": turn.content,
                "created_at": turn.created_at.isoformat(),
            }
            for turn in recent_turns
        ]
    }


def build_rag_query(state: dict[str, Any]) -> str:
    parts: list[str] = []
    user_query = state.get("user_query")
    if user_query:
        parts.append(f"用户问题: {user_query}")
    intent = state.get("intent")
    if intent:
        parts.append(f"当前意图: {intent}")
    time_window = state.get("time_window")
    if time_window:
        parts.append(f"时间窗口: {time_window}")
    scope = state.get("scope")
    if scope:
        parts.append(f"诊断范围: {scope}")
    return "\n".join(parts).strip() or "加速器故障诊断"


def build_rag_context(
    rag: RagService,
    state: dict[str, Any],
    *,
    limit: int = 5,
    include_system_design: bool = False,
) -> dict[str, Any]:
    query = build_rag_query(state)
    results = rag.search(
        query,
        limit=limit,
        include_system_design=include_system_design,
    )
    return {
        "enabled": True,
        "query": query,
        "limit": limit,
        "include_system_design": include_system_design,
        "results": [
            {
                "chunk_id": result.chunk_id,
                "document_id": result.document_id,
                "doc_type": result.metadata.get("doc_type"),
                "source": result.source,
                "score": result.score,
                "text": result.text,
                "metadata": result.metadata,
            }
            for result in results
        ],
    }

# app/agent/state.py

from __future__ import annotations

from typing import Any, Literal, TypedDict


class DiagnosisState(TypedDict, total=False):
    # Harness IDs
    thread_uid: str
    turn_uid: str
    run_uid: str
    case_uid: str

    # 输入
    trigger_source: Literal["chat", "auto"]
    user_query: str | None
    intent: str | None
    time_window: dict[str, str] | None
    scope: dict[str, Any]
    conversation_context: dict[str, Any]
    enable_rag: bool
    rag_limit: int
    rag_include_system_design: bool
    rag_context: dict[str, Any]
    rag_history: list[dict[str, Any]]

    # ReAct 执行控制
    step: int
    max_steps: int
    done: bool
    status: Literal["running", "completed", "failed"]

    # ReAct 当前动作
    current_thought: str | None
    current_action: dict[str, Any] | None

    # ReAct 历史
    react_history: list[dict[str, Any]]
    tool_history: list[dict[str, Any]]
    skill_history: list[dict[str, Any]]
    observations: list[dict[str, Any]]

    # 证据和候选原因
    evidence: list[dict[str, Any]]
    candidate_causes: list[dict[str, Any]]

    # 输出
    final_answer: str | None
    llm_usage: dict[str, Any]

    # 错误
    error: str | None

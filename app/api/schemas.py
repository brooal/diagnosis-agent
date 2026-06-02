from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TimeWindow(BaseModel):
    start: str = Field(..., description="ISO datetime string.")
    end: str = Field(..., description="ISO datetime string.")


class AgentChatRequest(BaseModel):
    user_query: str = Field(..., min_length=1)
    time_window: TimeWindow | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    thread_uid: str | None = None
    enable_rag: bool | None = None
    rag_limit: int | None = Field(default=None, gt=0)
    rag_include_system_design: bool | None = None


class AgentAutoRequest(BaseModel):
    fault_type: str = Field(..., min_length=1)
    time_window: TimeWindow | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    enable_rag: bool | None = None
    rag_limit: int | None = Field(default=None, gt=0)
    rag_include_system_design: bool | None = None


class BeamManualDiagnosisRequest(BaseModel):
    time_window: TimeWindow


class BeamAutoProbeRequest(BaseModel):
    use_llm_summary: bool = False
    email_to: str | None = None


class AgentChatResponse(BaseModel):
    status: str
    thread_uid: str | None = None
    turn_uid: str | None = None
    case_uid: str | None = None
    run_uid: str | None = None
    final_answer: str | None = None
    error: str | None = None
    rag_context: dict[str, Any] | None = None
    react_history: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    candidate_causes: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"


class ThreadSummary(BaseModel):
    thread_uid: str
    title: str | None = None
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    last_message: str | None = None
    last_run_status: str | None = None
    run_count: int = 0


class ThreadUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class TurnRecord(BaseModel):
    turn_uid: str
    role: str
    content: str
    created_at: str | None = None


class RunSummary(BaseModel):
    run_uid: str
    case_uid: str
    turn_uid: str
    status: str
    trigger_source: str
    user_query: str | None = None
    intent: str | None = None
    time_window: dict[str, Any] | None = None
    candidate_cause_count: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    final_answer: str | None = None


class ThreadDetail(BaseModel):
    thread: ThreadSummary
    turns: list[TurnRecord] = Field(default_factory=list)
    runs: list[RunSummary] = Field(default_factory=list)


class RunDetail(BaseModel):
    run: dict[str, Any]
    case: dict[str, Any] | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    skill_calls: list[dict[str, Any]] = Field(default_factory=list)

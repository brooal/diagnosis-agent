# app/harness/models.py

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.session import Base


class HarnessThread(Base):
    __tablename__ = "harness_thread"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HarnessTurn(Base):
    __tablename__ = "harness_turn"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    thread_uid: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(32))  # user / system / auto
    content: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HarnessRun(Base):
    __tablename__ = "harness_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    thread_uid: Mapped[str] = mapped_column(String(64), index=True)
    turn_uid: Mapped[str] = mapped_column(String(64), index=True)
    case_uid: Mapped[str] = mapped_column(String(64), index=True)

    status: Mapped[str] = mapped_column(String(32), default="running")
    trigger_source: Mapped[str] = mapped_column(String(32))

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)


class HarnessItem(Base):
    __tablename__ = "harness_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    run_uid: Mapped[str] = mapped_column(String(64), index=True)
    case_uid: Mapped[str] = mapped_column(String(64), index=True)

    item_type: Mapped[str] = mapped_column(String(64))
    # user_message / assistant_message / plan / tool_call / skill_call / evidence / final_answer

    content: Mapped[dict] = mapped_column(JSON)
    seq: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DiagnosisCase(Base):
    __tablename__ = "diagnosis_case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    thread_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    turn_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    trigger_source: Mapped[str] = mapped_column(String(32))
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")

    time_window: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_causes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DiagnosisToolCall(Base):
    __tablename__ = "diagnosis_tool_call"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    case_uid: Mapped[str] = mapped_column(String(64), index=True)
    run_uid: Mapped[str] = mapped_column(String(64), index=True)

    step: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(128))
    arguments: Mapped[dict] = mapped_column(JSON)

    ok: Mapped[bool] = mapped_column(Boolean)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DiagnosisSkillCall(Base):
    __tablename__ = "diagnosis_skill_call"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    case_uid: Mapped[str] = mapped_column(String(64), index=True)
    run_uid: Mapped[str] = mapped_column(String(64), index=True)

    step: Mapped[int] = mapped_column(Integer)
    skill_name: Mapped[str] = mapped_column(String(128))
    arguments: Mapped[dict] = mapped_column(JSON)

    ok: Mapped[bool] = mapped_column(Boolean)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    candidate_causes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DiagnosisTraceEvent(Base):
    __tablename__ = "diagnosis_trace_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    case_uid: Mapped[str] = mapped_column(String(64), index=True)
    run_uid: Mapped[str] = mapped_column(String(64), index=True)

    seq: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
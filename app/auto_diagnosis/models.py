from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.session import Base
from app.utils.times import now_shanghai


class AutoMonitorRun(Base):
    __tablename__ = "auto_monitor_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    monitor_type: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)

    schedule_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detect_window: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_shanghai)


class AutoBeamIncident(Base):
    __tablename__ = "auto_beam_incident"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    incident_key: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    classification: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)

    first_seen_at: Mapped[str] = mapped_column(String(64))
    last_seen_at: Mapped[str] = mapped_column(String(64))
    recovered_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normal_window_count: Mapped[int] = mapped_column(Integer, default=0)

    primary_cause: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate_causes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_report_sent_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_shanghai)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_shanghai)


class AutoNotification(Base):
    __tablename__ = "auto_notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    incident_uid: Mapped[str] = mapped_column(String(64), index=True)
    notification_type: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="email")
    status: Mapped[str] = mapped_column(String(32), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    recipients: Mapped[list | None] = mapped_column(JSON, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_shanghai)

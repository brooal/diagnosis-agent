from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

IncidentStatus = Literal["active", "closed"]
MonitorAction = Literal["skipped", "normal", "new_incident", "updated_incident", "recovered", "error"]


@dataclass
class BeamFaultEvent:
    incident_key: str
    classification: str
    severity: str
    event_time: str
    summary: str
    primary_cause: dict[str, Any] | None = None
    candidate_causes: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class BeamPipelineResult:
    status: str
    detect_window: dict[str, str]
    events: list[BeamFaultEvent] = field(default_factory=list)
    raw_output: dict[str, Any] = field(default_factory=dict)
    summary: str | None = None
    error: str | None = None


@dataclass
class BeamMonitorResult:
    action: MonitorAction
    schedule: dict[str, Any] | None
    detect_window: dict[str, str]
    incident_uid: str | None = None
    event: BeamFaultEvent | None = None
    summary: str | None = None
    report: str | None = None
    notification_sent: bool = False
    error: str | None = None
    data_source: dict[str, Any] | None = None

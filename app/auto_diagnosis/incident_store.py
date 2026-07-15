from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.auto_diagnosis.models import AutoBeamIncident, AutoMonitorRun, AutoNotification
from app.auto_diagnosis.schemas import BeamFaultEvent
from app.utils.json import make_json_safe
from app.utils.times import now_shanghai


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class AutoIncidentStore:
    def __init__(self, db: Session):
        self.db = db

    def record_monitor_run(
        self,
        *,
        monitor_type: str,
        action: str,
        status: str,
        schedule_status: str | None,
        detect_window: dict | None,
        summary: str | None = None,
        error: str | None = None,
    ) -> str:
        run_uid = _uid("autorun")
        row = AutoMonitorRun(
            run_uid=run_uid,
            monitor_type=monitor_type,
            action=action,
            status=status,
            schedule_status=schedule_status,
            detect_window=make_json_safe(detect_window),
            summary=summary,
            error=error,
        )
        self.db.add(row)
        self._commit()
        return run_uid

    def find_active_incident(self, incident_key: str) -> AutoBeamIncident | None:
        return (
            self.db.query(AutoBeamIncident)
            .filter_by(incident_key=incident_key, status="active")
            .order_by(AutoBeamIncident.id.desc())
            .first()
        )

    def latest_active_incident(self) -> AutoBeamIncident | None:
        return (
            self.db.query(AutoBeamIncident)
            .filter_by(status="active")
            .order_by(AutoBeamIncident.id.desc())
            .first()
        )

    def find_mergeable_active_incident(
        self,
        event: BeamFaultEvent,
        *,
        merge_seconds: int,
    ) -> AutoBeamIncident | None:
        latest = self.latest_active_incident()
        if latest is None:
            return None
        if latest.classification != event.classification:
            return None
        gap = _seconds_between(latest.last_seen_at, _event_observed_time(event))
        if gap is None or gap < 0 or gap > merge_seconds:
            return None
        return latest

    def find_recent_active_incident(
        self,
        event: BeamFaultEvent,
        *,
        merge_seconds: int,
    ) -> AutoBeamIncident | None:
        latest = self.latest_active_incident()
        if latest is None:
            return None
        gap = _seconds_between(latest.last_seen_at, _event_observed_time(event))
        if gap is None or gap < 0 or gap > merge_seconds:
            return None
        return latest

    def create_incident(self, event: BeamFaultEvent, *, report: str | None = None) -> AutoBeamIncident:
        evidence = make_json_safe(event.evidence)
        if isinstance(evidence, dict):
            evidence.setdefault("report_window", evidence.get("detect_window"))
            evidence.setdefault("fault_time", event.event_time)
        incident = AutoBeamIncident(
            incident_uid=_uid("incident"),
            incident_key=event.incident_key,
            status="active",
            classification=event.classification,
            severity=event.severity,
            first_seen_at=event.event_time,
            last_seen_at=_event_observed_time(event),
            normal_window_count=0,
            primary_cause=make_json_safe(_event_primary_cause(event)),
            candidate_causes=make_json_safe(event.candidate_causes),
            evidence=evidence,
            report=report,
            updated_at=now_shanghai(),
        )
        self.db.add(incident)
        self._commit()
        return incident

    def update_incident(
        self,
        incident: AutoBeamIncident,
        event: BeamFaultEvent,
        *,
        report: str | None = None,
    ) -> AutoBeamIncident:
        evidence = make_json_safe(event.evidence)
        if isinstance(evidence, dict):
            previous_evidence = incident.evidence if isinstance(incident.evidence, dict) else {}
            if previous_evidence.get("report_window"):
                evidence["report_window"] = previous_evidence["report_window"]
            if previous_evidence.get("fault_time"):
                evidence["fault_time"] = previous_evidence["fault_time"]
            if previous_evidence.get("llm_usage"):
                evidence["llm_usage"] = previous_evidence["llm_usage"]
        incident.last_seen_at = _event_observed_time(event)
        incident.normal_window_count = 0
        incident.evidence = evidence
        if report:
            incident.report = report
        incident.updated_at = now_shanghai()
        self._commit()
        return incident

    def mark_normal_window(self, incident: AutoBeamIncident) -> AutoBeamIncident:
        incident.normal_window_count += 1
        incident.updated_at = now_shanghai()
        self._commit()
        return incident

    def mark_recovery_unconfirmed(
        self,
        incident: AutoBeamIncident,
        *,
        observed_at: str,
    ) -> AutoBeamIncident:
        incident.normal_window_count = 0
        incident.last_seen_at = observed_at
        incident.updated_at = now_shanghai()
        self._commit()
        return incident

    def close_incident(self, incident: AutoBeamIncident, *, recovered_at: str) -> AutoBeamIncident:
        incident.status = "closed"
        incident.recovered_at = recovered_at
        incident.updated_at = now_shanghai()
        self._commit()
        return incident

    def mark_report_sent(self, incident: AutoBeamIncident, *, sent_at: str) -> None:
        incident.last_report_sent_at = sent_at
        incident.updated_at = now_shanghai()
        self._commit()

    def find_incident(self, incident_uid: str) -> AutoBeamIncident | None:
        return (
            self.db.query(AutoBeamIncident)
            .filter_by(incident_uid=incident_uid)
            .first()
        )

    def record_notification(
        self,
        *,
        incident_uid: str,
        notification_type: str,
        status: str,
        subject: str,
        recipients: list[str],
        body: str | None,
        error: str | None = None,
    ) -> str:
        notification_uid = _uid("notice")
        row = AutoNotification(
            notification_uid=notification_uid,
            incident_uid=incident_uid,
            notification_type=notification_type,
            status=status,
            subject=subject,
            recipients=make_json_safe(recipients),
            body=body,
            error=error,
        )
        self.db.add(row)
        self._commit()
        return notification_uid

    def failed_email_notifications(self, *, limit: int) -> list[AutoNotification]:
        return (
            self.db.query(AutoNotification)
            .filter_by(channel="email", status="failed")
            .order_by(AutoNotification.id.asc())
            .limit(limit)
            .all()
        )

    def update_notification_status(
        self,
        notification: AutoNotification,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        notification.status = status
        notification.error = error
        self._commit()

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise


def _event_primary_cause(event: BeamFaultEvent) -> dict | None:
    if event.primary_cause:
        return event.primary_cause
    return event.candidate_causes[0] if event.candidate_causes else None


def _event_observed_time(event: BeamFaultEvent) -> str:
    evidence = event.evidence if isinstance(event.evidence, dict) else {}
    window = evidence.get("detect_window")
    if isinstance(window, dict) and window.get("end"):
        return str(window["end"])
    return event.event_time


def _seconds_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        return (datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).total_seconds()
    except Exception:
        return None

from __future__ import annotations

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

    def create_incident(self, event: BeamFaultEvent, *, report: str | None = None) -> AutoBeamIncident:
        incident = AutoBeamIncident(
            incident_uid=_uid("incident"),
            incident_key=event.incident_key,
            status="active",
            classification=event.classification,
            severity=event.severity,
            first_seen_at=event.event_time,
            last_seen_at=event.event_time,
            normal_window_count=0,
            primary_cause=make_json_safe(event.primary_cause),
            candidate_causes=make_json_safe(event.candidate_causes),
            evidence=make_json_safe(event.evidence),
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
        incident.classification = event.classification
        incident.severity = event.severity
        incident.last_seen_at = event.event_time
        incident.normal_window_count = 0
        incident.primary_cause = make_json_safe(event.primary_cause)
        incident.candidate_causes = make_json_safe(event.candidate_causes)
        incident.evidence = make_json_safe(event.evidence)
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

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

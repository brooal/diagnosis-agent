from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auto_diagnosis.beam_monitor import BeamAutoMonitor
from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.manual_diagnosis import BeamManualDiagnosisRunner
from app.auto_diagnosis.models import AutoBeamIncident, AutoMonitorRun, AutoNotification
from app.auto_diagnosis.operation_schedule import get_hls2_2026_plan, is_operation_day
from app.data_sources.schemas import PVRawSample, PVSample
from app.db.session import Base


class FakeSummarizer:
    def summarize_new_incident(self, *, event, schedule, detect_window):
        return f"summary for {event.classification}"


class FakeEmailer:
    def send(self, *, subject: str, body: str):
        return type("Result", (), {"sent": False, "status": "dry_run", "error": None})()


class FakeManualSummarizer:
    def summarize_manual_diagnosis(self, *, diagnosis, fallback):
        return f"llm summary: {fallback}"


def _session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class FakePVRepo:
    def __init__(
        self,
        *,
        beam_values: list[float],
        mode_values: list[int] | None = None,
        alarm_values: dict[int, int] | None = None,
        power_values: list[float] | None = None,
    ):
        self.beam_values = beam_values
        self.mode_values = mode_values or []
        self.alarm_values = alarm_values or {}
        self.power_values = power_values or []

    def fetch_sample_channel_samples(self, channel_id, start_time, end_time, limit=None):
        return [
            PVSample(
                channel_name="RNG:BEAM:CURR",
                smpl_time=f"2026-05-11T12:00:{index:02d}+08:00",
                nanosecs=0,
                float_val=value,
            )
            for index, value in enumerate(self.beam_values)
        ]

    def fetch_raw_channel_samples(self, channel_ids, start_time, end_time, limit=None):
        rows = []
        if channel_ids == [2418]:
            rows.extend(
                PVRawSample(
                    channel_id=2418,
                    channel_name="RNG:OPERATION:MODE:bo",
                    smpl_time=f"2026-05-11T12:00:{index:02d}+08:00",
                    nanosecs=0,
                    num_val=value,
                )
                for index, value in enumerate(self.mode_values)
            )
            return rows

        for channel_id in channel_ids:
            if channel_id in self.alarm_values:
                rows.append(
                    PVRawSample(
                        channel_id=channel_id,
                        channel_name=_alarm_name(channel_id),
                        smpl_time="2026-05-11T12:00:00+08:00",
                        nanosecs=0,
                        num_val=self.alarm_values[channel_id],
                    )
                )
        return rows

    def fetch_pattern_samples(self, pattern, start_time, end_time, limit=None):
        return [
            PVSample(
                channel_name="SR_PS_QM:test:current:ai",
                smpl_time=f"2026-05-11T12:00:{index:02d}+08:00",
                nanosecs=0,
                float_val=value,
            )
            for index, value in enumerate(self.power_values)
        ]


def _alarm_name(channel_id: int) -> str:
    return {
        2422: "RNG:TOPOFF:IE:Err:mbbo",
        2426: "RNG:TOPOFF:BEAM:Err:mbbo",
    }.get(channel_id, f"channel:{channel_id}")


def test_hls2_2026_operation_schedule() -> None:
    assert get_hls2_2026_plan("2026-05-12") == {
        "date": "2026-05-12",
        "status": "Operation",
        "status_cn": "供光运行",
    }
    assert is_operation_day("2026-05-12") is True
    assert is_operation_day("2026-05-26") is False


def test_beam_auto_monitor_skips_non_operation_day() -> None:
    session_factory = _session_factory()
    db = session_factory()
    config = AutoDiagnosisConfig(require_operation_schedule=True)
    monitor = BeamAutoMonitor(
        db=db,
        config=config,
        repo=FakePVRepo(beam_values=[498.0]),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 26, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "skipped"
    assert result.schedule["status"] == "Maintenance"
    assert db.query(AutoMonitorRun).one().status == "non_operation"


def test_beam_auto_monitor_creates_incident_on_operation_day() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(
            beam_values=[498.0, 420.0, 80.0, 20.0],
            mode_values=[0],
            alarm_values={2426: 1},
        ),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "new_incident"
    assert result.event.classification == "drop"
    incident = db.query(AutoBeamIncident).one()
    assert incident.status == "active"
    assert incident.severity == "critical"
    assert incident.primary_cause["meaning"] == "Low Current"
    assert db.query(AutoNotification).one().status == "dry_run"


def test_beam_auto_monitor_creates_decay_incident_from_mode_and_ie_alarm() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(
            beam_values=[498.0, 496.0, 494.0, 492.0],
            mode_values=[0],
            alarm_values={2422: 1},
        ),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "new_incident"
    assert result.event.classification == "decay"
    incident = db.query(AutoBeamIncident).one()
    assert incident.severity == "warning"
    assert incident.primary_cause["meaning"] == "Injecting Efficiency Low"


def test_beam_auto_monitor_ignores_slight_boundary_deviation_without_mode_or_alarm() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(
            beam_values=[495.1, 495.0, 494.9, 494.85, 495.05],
            mode_values=[1],
        ),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "normal"
    assert db.query(AutoBeamIncident).count() == 0
    run = db.query(AutoMonitorRun).one()
    assert run.status == "ok"


def test_beam_auto_monitor_adds_quadrupole_cause_for_drop() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(
            beam_values=[498.0, 80.0, 20.0],
            power_values=[12.0, 0.0],
        ),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "new_incident"
    assert result.event.classification == "drop"
    assert result.event.primary_cause["cause_type"] == "quadrupole_power_fault"
    assert result.event.evidence["quadrupole_power"]["power_fault_count"] == 1


def test_beam_auto_monitor_updates_same_incident_without_new_notification() -> None:
    session_factory = _session_factory()
    db = session_factory()
    repo = FakePVRepo(
        beam_values=[498.0, 496.0, 494.0, 492.0],
        mode_values=[0],
        alarm_values={2422: 1},
    )
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=repo,
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    first = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
    second = monitor.run_once(now=datetime(2026, 5, 11, 12, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert first.action == "new_incident"
    assert second.action == "updated_incident"
    assert db.query(AutoBeamIncident).count() == 1
    assert db.query(AutoNotification).count() == 1


def test_beam_auto_monitor_merges_sustained_drop_without_mode_or_alarm() -> None:
    session_factory = _session_factory()
    db = session_factory()
    repo = FakePVRepo(beam_values=[30.0, 28.0, 27.0])
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=repo,
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    first = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
    second = monitor.run_once(now=datetime(2026, 5, 11, 12, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert first.action == "new_incident"
    assert second.action == "updated_incident"
    assert db.query(AutoBeamIncident).count() == 1
    assert db.query(AutoNotification).count() == 1


def test_beam_auto_monitor_builds_http_repository_by_default(monkeypatch) -> None:
    from app.auto_diagnosis import beam_monitor

    session_factory = _session_factory()
    db = session_factory()

    def fake_build_archive_repository(*, backend):
        assert backend == "http"
        return FakePVRepo(beam_values=[498.0, 498.1]), None

    monkeypatch.delenv("AUTO_BEAM_DATA_BACKEND", raising=False)
    monkeypatch.setattr(beam_monitor, "build_archive_repository", fake_build_archive_repository)

    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=False),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )
    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "normal"
    assert result.data_source == {"backend": "http", "repository": "FakePVRepo"}


def test_beam_manual_diagnosis_runs_user_time_range_without_persisting_incident() -> None:
    session_factory = _session_factory()
    db = session_factory()
    result = BeamManualDiagnosisRunner(
        repo=FakePVRepo(
            beam_values=[498.0, 430.0, 80.0, 25.0],
            mode_values=[0],
            alarm_values={2426: 1},
        ),
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        summarizer=FakeManualSummarizer(),
    ).run(
        start="2026-05-11T12:00:00+08:00",
        end="2026-05-11T12:01:00+08:00",
    )

    assert result["trigger_source"] == "user"
    assert result["status"] == "completed"
    assert result["diagnosis_status"] == "fault"
    assert result["event"]["classification"] == "drop"
    assert result["event"]["primary_cause"]["meaning"] == "Low Current"
    assert result["final_answer"].startswith("llm summary:")
    assert db.query(AutoBeamIncident).count() == 0
    assert db.query(AutoNotification).count() == 0

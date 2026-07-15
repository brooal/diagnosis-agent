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
from app.auto_diagnosis.incident_store import AutoIncidentStore
from app.auto_diagnosis.manual_diagnosis import BeamManualDiagnosisRunner
from app.auto_diagnosis.models import AutoBeamIncident, AutoMonitorRun, AutoNotification
from app.auto_diagnosis.operation_schedule import get_hls2_2026_plan, is_operation_day
from app.auto_diagnosis.scheduler import BeamAutoDiagnosisScheduler, retry_failed_email_notifications
from app.data_sources.schemas import PVRawSample, PVSample
from app.db.session import Base


class FakeSummarizer:
    def summarize_new_incident(self, *, event, schedule, detect_window):
        return f"summary for {event.classification}"


class FakeUsageSummarizer:
    def summarize_new_incident_with_usage(self, *, event, schedule, detect_window):
        return type(
            "SummaryResult",
            (),
            {
                "text": f"summary for {event.classification}",
                "token_usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "model": "fake-model",
                    "source": "provider",
                },
            },
        )()


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
        beam_context_values: list[float] | None = None,
        mode_values: list[int] | None = None,
        previous_mode_value: int | None = None,
        alarm_values: dict[int, int] | None = None,
        power_values: list[float] | None = None,
    ):
        self.beam_values = beam_values
        self.beam_context_values = beam_context_values
        self.mode_values = mode_values or []
        self.previous_mode_value = previous_mode_value
        self.alarm_values = alarm_values or {}
        self.power_values = power_values or []
        self._sample_call_count = 0

    def fetch_sample_channel_samples(self, channel_id, start_time, end_time, limit=None):
        self._sample_call_count += 1
        is_context_call = self.beam_context_values is not None and self._sample_call_count == 2
        values = self.beam_context_values if is_context_call else self.beam_values
        minute = "59" if is_context_call else "00"
        return [
            PVSample(
                channel_name="RNG:BEAM:CURR",
                smpl_time=f"2026-05-11T11:{minute}:{index:02d}+08:00" if is_context_call else f"2026-05-11T12:00:{index:02d}+08:00",
                nanosecs=0,
                float_val=value,
            )
            for index, value in enumerate(values or [])
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

    def fetch_latest_raw_sample_before(self, channel_id, before_time):
        if channel_id != 2418 or self.previous_mode_value is None:
            return None
        return PVRawSample(
            channel_id=2418,
            channel_name="RNG:OPERATION:MODE:bo",
            smpl_time="2026-05-11T11:59:55+08:00",
            nanosecs=0,
            num_val=self.previous_mode_value,
        )

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


def test_beam_auto_monitor_estimates_drop_onset_from_context_baseline() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(
            beam_values=[337.8, 0.016, 0.014],
            beam_context_values=[498.2, 497.9],
            mode_values=[0],
            alarm_values={2426: 1},
        ),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "new_incident"
    assert result.event.classification == "drop"
    beam = result.event.evidence["beam"]
    assert beam["drop_baseline_value"] == 497.9
    assert beam["estimated_drop_start_time"] == "2026-05-11T12:00:00+08:00"
    assert result.event.evidence["report_window"]["start"] == "2026-05-11T12:00:00+08:00"


def test_beam_auto_monitor_classifies_seventy_percent_step_as_drop() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(beam_values=[500.0, 350.0], mode_values=[1]),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.event.classification == "drop"
    assert result.event.evidence["beam"]["drop_step_ratio"] == 0.7


def test_beam_auto_monitor_does_not_apply_step_rule_above_seventy_percent() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(beam_values=[500.0, 351.0], mode_values=[1]),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "normal"
    assert result.event is None


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


def test_beam_auto_monitor_classifies_beam_error_alarm_as_drop() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(
            beam_values=[498.0, 497.5, 496.8, 496.2],
            mode_values=[0],
            alarm_values={2426: 1},
        ),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "new_incident"
    assert result.event.classification == "drop"
    assert result.event.primary_cause["pv"] == "RNG:TOPOFF:BEAM:Err:mbbo"
    assert result.event.primary_cause["meaning"] == "Low Current"


def test_beam_auto_monitor_inherits_mode_zero_at_window_start() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(
            beam_values=[498.0, 497.8, 497.6],
            mode_values=[],
            previous_mode_value=0,
        ),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "new_incident"
    assert result.event.classification == "decay"
    assert result.event.evidence["mode"]["inherited_zero_at_window_start"] is True
    assert result.event.evidence["mode"]["zero_times"][0]["inherited"] is True


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


def test_beam_auto_monitor_treats_active_alarm_as_cause_only_when_beam_and_mode_normal() -> None:
    session_factory = _session_factory()
    db = session_factory()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=FakePVRepo(
            beam_values=[499.0, 499.2, 499.1],
            mode_values=[1],
            alarm_values={2422: 1},
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


def test_beam_auto_monitor_preserves_llm_usage_on_incident_update() -> None:
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
        summarizer=FakeUsageSummarizer(),
        emailer=FakeEmailer(),
    )

    first = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
    second = monitor.run_once(now=datetime(2026, 5, 11, 12, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert first.action == "new_incident"
    assert second.action == "updated_incident"
    incident = db.query(AutoBeamIncident).one()
    assert incident.evidence["llm_usage"]["total_tokens"] == 120
    assert incident.evidence["llm_usage"]["model"] == "fake-model"


def test_beam_auto_monitor_preserves_initial_primary_cause_on_later_updates() -> None:
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
    repo.alarm_values = {}
    second = monitor.run_once(now=datetime(2026, 5, 11, 12, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert first.action == "new_incident"
    assert second.action == "updated_incident"
    incident = db.query(AutoBeamIncident).one()
    assert incident.primary_cause["pv"] == "RNG:TOPOFF:IE:Err:mbbo"
    assert incident.candidate_causes[0]["pv"] == "RNG:TOPOFF:IE:Err:mbbo"


def test_beam_auto_monitor_does_not_merge_stale_active_incident() -> None:
    session_factory = _session_factory()
    db = session_factory()
    db.add(
        AutoBeamIncident(
            incident_uid="incident_stale",
            incident_key="decay:mode:old",
            status="active",
            classification="decay",
            severity="warning",
            first_seen_at="2026-05-11T11:00:00+08:00",
            last_seen_at="2026-05-11T11:00:00+08:00",
            normal_window_count=0,
        )
    )
    db.commit()
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True, incident_merge_seconds=300),
        repo=FakePVRepo(
            beam_values=[498.0, 496.0, 494.0, 492.0],
            mode_values=[0],
        ),
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "new_incident"
    assert result.incident_uid != "incident_stale"
    assert db.query(AutoBeamIncident).count() == 2
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


def test_beam_auto_monitor_treats_post_drop_decay_as_same_incident() -> None:
    session_factory = _session_factory()
    db = session_factory()
    repo = FakePVRepo(
        beam_values=[498.0, 40.0, 20.0],
        mode_values=[0],
        alarm_values={2426: 1},
    )
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=repo,
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    first = monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
    repo.beam_values = [107.5, 107.1, 106.8]
    repo.mode_values = []
    repo.previous_mode_value = 0
    repo.alarm_values = {}
    repo._sample_call_count = 0
    second = monitor.run_once(now=datetime(2026, 5, 11, 12, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert first.action == "new_incident"
    assert second.action == "updated_incident"
    incident = db.query(AutoBeamIncident).one()
    assert incident.classification == "drop"
    assert incident.severity == "critical"
    assert db.query(AutoNotification).count() == 1


def test_beam_auto_monitor_keeps_initial_classification_and_cause_until_recovery() -> None:
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
    repo.beam_values = [500.0, 300.0, 20.0]
    repo.mode_values = [0]
    repo.alarm_values = {2426: 1}
    repo._sample_call_count = 0
    second = monitor.run_once(now=datetime(2026, 5, 11, 12, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert first.action == "new_incident"
    assert second.action == "updated_incident"
    incident = db.query(AutoBeamIncident).one()
    assert incident.classification == "decay"
    assert incident.severity == "warning"
    assert incident.primary_cause["pv"] == "RNG:TOPOFF:IE:Err:mbbo"
    assert db.query(AutoNotification).count() == 1


def test_beam_auto_monitor_requires_three_strict_recovery_windows() -> None:
    session_factory = _session_factory()
    db = session_factory()
    repo = FakePVRepo(
        beam_values=[500.0, 300.0, 20.0],
        mode_values=[0],
        alarm_values={2426: 1},
    )
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(
            require_operation_schedule=True,
            incident_recovery_confirm_windows=3,
        ),
        repo=repo,
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
    repo.beam_values = [498.0, 498.2, 497.9]
    repo.mode_values = [1]
    repo.previous_mode_value = 1
    repo.alarm_values = {}
    repo._sample_call_count = 0

    first_normal = monitor.run_once(now=datetime(2026, 5, 11, 12, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    second_normal = monitor.run_once(now=datetime(2026, 5, 11, 12, 1, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
    third_normal = monitor.run_once(now=datetime(2026, 5, 11, 12, 2, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert first_normal.action == "normal"
    assert second_normal.action == "normal"
    assert third_normal.action == "recovered"
    incident = db.query(AutoBeamIncident).one()
    assert incident.status == "closed"
    assert incident.normal_window_count == 3


def test_beam_auto_monitor_does_not_recover_low_beam_with_mode_one() -> None:
    session_factory = _session_factory()
    db = session_factory()
    repo = FakePVRepo(
        beam_values=[500.0, 300.0, 20.0],
        mode_values=[0],
        alarm_values={2426: 1},
    )
    monitor = BeamAutoMonitor(
        db=db,
        config=AutoDiagnosisConfig(require_operation_schedule=True),
        repo=repo,
        summarizer=FakeSummarizer(),
        emailer=FakeEmailer(),
    )

    monitor.run_once(now=datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
    repo.beam_values = [107.0, 108.0, 109.0]
    repo.mode_values = [1]
    repo.previous_mode_value = 1
    repo.alarm_values = {}
    repo._sample_call_count = 0
    result = monitor.run_once(now=datetime(2026, 5, 11, 12, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result.action == "updated_incident"
    incident = db.query(AutoBeamIncident).one()
    assert incident.status == "active"
    assert incident.normal_window_count == 0


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


def test_beam_auto_scheduler_uses_continuous_detection_window() -> None:
    scheduler = BeamAutoDiagnosisScheduler(
        AutoDiagnosisConfig(detect_window_seconds=30),
    )
    first_start, first_end = scheduler._next_detect_window(
        datetime(2026, 5, 11, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    )
    scheduler._last_checked_end = first_end
    second_start, second_end = scheduler._next_detect_window(
        datetime(2026, 5, 11, 12, 1, 20, tzinfo=ZoneInfo("Asia/Shanghai"))
    )

    assert first_start == "2026-05-11T12:00:00+08:00"
    assert first_end == "2026-05-11T12:00:30+08:00"
    assert second_start == first_end
    assert second_end == "2026-05-11T12:01:20+08:00"


def test_retry_failed_email_notifications_marks_sent(monkeypatch) -> None:
    session_factory = _session_factory()
    db = session_factory()
    incident = AutoBeamIncident(
        incident_uid="incident_retry",
        incident_key="decay:mode:retry",
        status="active",
        classification="decay",
        severity="warning",
        first_seen_at="2026-05-11T12:00:00+08:00",
        last_seen_at="2026-05-11T12:00:00+08:00",
        normal_window_count=0,
    )
    db.add(incident)
    db.commit()
    AutoIncidentStore(db).record_notification(
        incident_uid="incident_retry",
        notification_type="new_incident",
        status="failed",
        subject="retry subject",
        recipients=["to@example.test"],
        body="retry body",
        error="ConnectionResetError: reset",
    )

    class SentEmailer:
        def __init__(self, config):
            self.config = config

        def send(self, *, subject, body):
            assert subject == "retry subject"
            assert body == "retry body"
            return type("Result", (), {"sent": True, "status": "sent", "error": None})()

    monkeypatch.setattr("app.auto_diagnosis.scheduler.AutoDiagnosisEmailer", SentEmailer)

    processed = retry_failed_email_notifications(
        db=db,
        config=AutoDiagnosisConfig(
            email_enabled=True,
            email_dry_run=False,
            email_to=["to@example.test"],
            notification_retry_batch_size=10,
        ),
    )

    notification = db.query(AutoNotification).one()
    assert processed == 1
    assert notification.status == "sent"
    assert notification.error is None
    assert db.query(AutoBeamIncident).one().last_report_sent_at is not None


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

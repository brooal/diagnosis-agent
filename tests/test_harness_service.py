from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import Base
from app.harness.models import DiagnosisCase, DiagnosisSkillCall, HarnessThread
from app.harness.service import HarnessService
from app.utils.times import now_shanghai


def _make_service() -> tuple[HarnessService, object]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    return HarnessService(session), session


def test_skill_call_json_payloads_accept_datetimes() -> None:
    service, session = _make_service()
    observed_at = datetime(2026, 5, 24, 22, 32, 17, tzinfo=ZoneInfo("Asia/Shanghai"))

    thread_uid = service.create_thread("diagnosis")
    turn_uid = service.create_turn(thread_uid, "user", "诊断束流")
    case_uid = service.create_case(
        thread_uid=thread_uid,
        turn_uid=turn_uid,
        trigger_source="chat",
        intent=None,
        time_window={"start": observed_at, "end": observed_at},
        scope={},
    )
    run_uid = service.create_run(
        thread_uid=thread_uid,
        turn_uid=turn_uid,
        case_uid=case_uid,
        trigger_source="chat",
    )

    service.add_skill_call(
        run_uid=run_uid,
        case_uid=case_uid,
        step=0,
        skill_name="beam_state_diagnosis",
        arguments={"fault_time": observed_at},
        ok=True,
        summary="ok",
        evidence=[{"time": observed_at}],
        candidate_causes=[{"time": observed_at, "nested": {"at": observed_at}}],
        error=None,
        reason="test",
    )
    service.complete_run(
        run_uid=run_uid,
        case_uid=case_uid,
        final_answer="ok",
        candidate_causes=[{"time": observed_at}],
    )

    skill_call = session.query(DiagnosisSkillCall).filter_by(run_uid=run_uid).one()
    case = session.query(DiagnosisCase).filter_by(case_uid=case_uid).one()

    assert skill_call.arguments["fault_time"] == "2026-05-24T22:32:17+08:00"
    assert skill_call.evidence[0]["time"] == "2026-05-24T22:32:17+08:00"
    assert skill_call.candidate_causes[0]["nested"]["at"] == "2026-05-24T22:32:17+08:00"
    assert case.time_window["start"] == "2026-05-24T22:32:17+08:00"
    assert case.candidate_causes[0]["time"] == "2026-05-24T22:32:17+08:00"


def test_local_database_timestamps_use_shanghai_clock() -> None:
    service, session = _make_service()
    before = now_shanghai()

    thread_uid = service.create_thread("diagnosis")

    after = now_shanghai()
    thread = session.query(HarnessThread).filter_by(thread_uid=thread_uid).one()

    assert before - timedelta(seconds=1) <= thread.created_at <= after + timedelta(seconds=1)
    assert thread.created_at.tzinfo is None

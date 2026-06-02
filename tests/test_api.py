from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def test_frontend_index_is_served() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Diagnosis Agent Workbench" in response.text


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_agent_chat_endpoint_uses_runner(monkeypatch) -> None:
    from app.api import routes

    class FakeRunner:
        def __init__(self) -> None:
            self.closed = False

        def run_chat(self, **kwargs):
            assert kwargs["user_query"] == "诊断测试"
            assert kwargs["time_window"] == {
                "start": "2026-05-21T10:03:00+08:00",
                "end": "2026-05-21T10:04:00+08:00",
            }
            return {
                "status": "completed",
                "thread_uid": "thread_test",
                "turn_uid": "turn_test",
                "case_uid": "case_test",
                "run_uid": "run_test",
                "final_answer": "ok",
                "react_history": [{"step": 0}],
                "observations": [],
                "evidence": [],
                "candidate_causes": [],
            }

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(routes, "DiagnosisAgentRunner", FakeRunner)
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent/chat",
        json={
            "user_query": "诊断测试",
            "time_window": {
                "start": "2026-05-21T10:03:00+08:00",
                "end": "2026-05-21T10:04:00+08:00",
            },
            "scope": {"beam_current_pv": "RNG:BEAM:CURR"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["run_uid"] == "run_test"
    assert body["final_answer"] == "ok"


def test_agent_chat_endpoint_allows_natural_language_only(monkeypatch) -> None:
    from app.api import routes

    class FakeRunner:
        def run_chat(self, **kwargs):
            assert kwargs["user_query"] == "今天10:00到10:05帮我分析是否掉束"
            assert kwargs["time_window"] is None
            assert kwargs["scope"] == {}
            return {
                "status": "completed",
                "thread_uid": "thread_natural",
                "turn_uid": "turn_natural",
                "case_uid": "case_natural",
                "run_uid": "run_natural",
                "final_answer": "need model extraction",
                "react_history": [],
                "observations": [],
                "evidence": [],
                "candidate_causes": [],
            }

        def close(self) -> None:
            pass

    monkeypatch.setattr(routes, "DiagnosisAgentRunner", FakeRunner)
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent/chat",
        json={"user_query": "今天10:00到10:05帮我分析是否掉束"},
    )

    assert response.status_code == 200
    assert response.json()["run_uid"] == "run_natural"


def test_agent_chat_endpoint_serializes_datetime_state(monkeypatch) -> None:
    from app.api import routes

    observed_at = datetime(2026, 5, 24, 22, 32, 17, tzinfo=ZoneInfo("Asia/Shanghai"))

    class FakeRunner:
        def run_chat(self, **kwargs):
            return {
                "status": "completed",
                "thread_uid": "thread_datetime",
                "turn_uid": "turn_datetime",
                "case_uid": "case_datetime",
                "run_uid": "run_datetime",
                "final_answer": "ok",
                "react_history": [],
                "observations": [{"output": {"time": observed_at}}],
                "evidence": [{"time": observed_at}],
                "candidate_causes": [{"time": observed_at}],
            }

        def close(self) -> None:
            pass

    monkeypatch.setattr(routes, "DiagnosisAgentRunner", FakeRunner)
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent/chat",
        json={"user_query": "诊断束流"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["observations"][0]["output"]["time"] == "2026-05-24T22:32:17+08:00"
    assert body["evidence"][0]["time"] == "2026-05-24T22:32:17+08:00"
    assert body["candidate_causes"][0]["time"] == "2026-05-24T22:32:17+08:00"


def test_agent_auto_endpoint_uses_runner(monkeypatch) -> None:
    from app.api import routes

    class FakeRunner:
        def run_auto(self, **kwargs):
            assert kwargs["fault_type"] == "PSS安全联锁中断诊断"
            assert kwargs["time_window"] == {
                "start": "2026-05-21T10:00:00+08:00",
                "end": "2026-05-21T10:10:00+08:00",
            }
            return {
                "status": "completed",
                "thread_uid": "thread_auto",
                "turn_uid": "turn_auto",
                "case_uid": "case_auto",
                "run_uid": "run_auto",
                "final_answer": "auto ok",
                "react_history": [],
                "observations": [],
                "evidence": [],
                "candidate_causes": [],
            }

        def close(self) -> None:
            pass

    monkeypatch.setattr(routes, "DiagnosisAgentRunner", FakeRunner)
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent/auto",
        json={
            "fault_type": "PSS安全联锁中断诊断",
            "time_window": {
                "start": "2026-05-21T10:00:00+08:00",
                "end": "2026-05-21T10:10:00+08:00",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["final_answer"] == "auto ok"


def test_history_endpoints_return_threads_and_run_detail(monkeypatch) -> None:
    from app.api import routes
    from app.db.session import Base
    from app.harness.models import (
        DiagnosisCase,
        DiagnosisSkillCall,
        HarnessItem,
        HarnessRun,
        HarnessThread,
        HarnessTurn,
    )

    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    session.add(HarnessThread(thread_uid="thread_history", title="历史诊断", status="active"))
    session.add(
        HarnessTurn(
            turn_uid="turn_history",
            thread_uid="thread_history",
            role="user",
            content="诊断PSS",
        )
    )
    session.add(
        HarnessRun(
            run_uid="run_history",
            thread_uid="thread_history",
            turn_uid="turn_history",
            case_uid="case_history",
            status="completed",
            trigger_source="chat",
            final_answer="done",
        )
    )
    session.add(
        DiagnosisCase(
            case_uid="case_history",
            thread_uid="thread_history",
            turn_uid="turn_history",
            run_uid="run_history",
            trigger_source="chat",
            status="completed",
            candidate_causes=[{"cause_type": "emergency_stop"}],
        )
    )
    session.add(
        HarnessItem(
            run_uid="run_history",
            case_uid="case_history",
            item_type="skill_called",
            content={"summary": "ok"},
            seq=1,
        )
    )
    session.add(
        DiagnosisSkillCall(
            run_uid="run_history",
            case_uid="case_history",
            step=0,
            skill_name="pss_interlock_interrupt_diagnosis",
            arguments={},
            ok=True,
            summary="ok",
            evidence=[],
            candidate_causes=[],
        )
    )
    session.commit()
    session.close()

    monkeypatch.setattr(routes, "SessionLocal", session_factory)
    monkeypatch.setattr(routes, "init_db", lambda: None)
    client = TestClient(app)

    threads = client.get("/api/v1/threads").json()
    assert threads[0]["thread_uid"] == "thread_history"
    assert threads[0]["run_count"] == 1

    thread = client.get("/api/v1/threads/thread_history").json()
    assert thread["turns"][0]["content"] == "诊断PSS"
    assert thread["runs"][0]["run_uid"] == "run_history"

    run = client.get("/api/v1/runs/run_history").json()
    assert run["run"]["final_answer"] == "done"
    assert run["case"]["candidate_causes"][0]["cause_type"] == "emergency_stop"
    assert run["items"][0]["item_type"] == "skill_called"
    assert run["skill_calls"][0]["skill_name"] == "pss_interlock_interrupt_diagnosis"
    assert "trace_events" not in run
    assert thread["runs"][0]["time_window"] is None
    assert thread["runs"][0]["candidate_cause_count"] == 1

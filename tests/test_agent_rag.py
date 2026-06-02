from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.nodes import retrieve_rag_node
from app.llm.prompts import build_react_messages
from app.rag.schemas import RagSearchResult


class FakeRecorder:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def append(
        self,
        *,
        run_uid: str,
        case_uid: str,
        event_type: str,
        payload: dict,
    ) -> None:
        self.events.append(
            {
                "run_uid": run_uid,
                "case_uid": case_uid,
                "event_type": event_type,
                "payload": payload,
            }
        )


class FakeRag:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(
        self,
        query: str,
        *,
        limit: int,
        include_system_design: bool,
    ) -> list[RagSearchResult]:
        self.calls.append(
            {
                "query": query,
                "limit": limit,
                "include_system_design": include_system_design,
            }
        )
        return [
            RagSearchResult(
                chunk_id="chunk_1",
                document_id="doc_1",
                text="历史人工诊断记录显示同类现象与四极铁电源波动相关。",
                score=0.9,
                source="case.md",
                metadata={"doc_type": "human_diagnosis_case", "case_id": "case_1"},
            )
        ]


class BrokenRag:
    def search(self, *args, **kwargs) -> list[RagSearchResult]:
        raise RuntimeError("qdrant unavailable")


def _base_state(**overrides):
    state = {
        "run_uid": "run_1",
        "case_uid": "case_1",
        "user_query": "检测这段时间的束流状态",
        "time_window": {
            "start": "2026-05-18 10:00:00",
            "end": "2026-05-18 10:05:00",
        },
        "scope": {},
        "enable_rag": True,
        "rag_limit": 5,
        "rag_include_system_design": True,
        "rag_history": [],
    }
    state.update(overrides)
    return state


def test_retrieve_rag_node_searches_when_enabled() -> None:
    rag = FakeRag()
    recorder = FakeRecorder()

    state = retrieve_rag_node(_base_state(), rag=rag, recorder=recorder)

    assert rag.calls == [
        {
            "query": (
                "用户问题: 检测这段时间的束流状态\n"
                "时间窗口: {'start': '2026-05-18 10:00:00', "
                "'end': '2026-05-18 10:05:00'}"
            ),
            "limit": 5,
            "include_system_design": True,
        }
    ]
    assert state["rag_context"]["enabled"] is True
    assert state["rag_context"]["results"][0]["doc_type"] == "human_diagnosis_case"
    assert state["rag_history"] == [state["rag_context"]]
    assert recorder.events[0]["event_type"] == "rag_retrieved"


def test_retrieve_rag_node_skips_when_disabled() -> None:
    rag = FakeRag()
    recorder = FakeRecorder()

    state = retrieve_rag_node(
        _base_state(enable_rag=False),
        rag=rag,
        recorder=recorder,
    )

    assert rag.calls == []
    assert recorder.events == []
    assert state["rag_context"] == {"enabled": False, "results": []}


def test_retrieve_rag_node_failure_does_not_fail_state() -> None:
    recorder = FakeRecorder()

    state = retrieve_rag_node(_base_state(), rag=BrokenRag(), recorder=recorder)

    assert state["rag_context"]["enabled"] is True
    assert state["rag_context"]["results"] == []
    assert "RuntimeError: qdrant unavailable" == state["rag_context"]["error"]
    assert recorder.events[0]["event_type"] == "rag_retrieval_failed"


def test_react_prompt_renders_rag_context_as_text() -> None:
    messages = build_react_messages(
        user_query="检测这段时间的束流状态",
        time_window=None,
        scope=None,
        conversation_context=None,
        rag_context={
            "enabled": True,
            "results": [
                {
                    "doc_type": "human_diagnosis_case",
                    "source": "case.md",
                    "text": "历史经验内容",
                    "metadata": {"case_id": "case_1"},
                }
            ],
        },
        tool_specs=[],
        skill_specs=[],
        react_history=[],
        observations=[],
        evidence=[],
        candidate_causes=[],
    )

    payload = json.loads(messages[1]["content"])
    assert isinstance(payload["retrieved_context"], str)
    assert "[RAG-1] 类型：human_diagnosis_case" in payload["retrieved_context"]
    assert "历史经验内容" in payload["retrieved_context"]


def test_react_prompt_accepts_datetime_evidence() -> None:
    observed_at = datetime(2026, 5, 24, 22, 32, 17, tzinfo=ZoneInfo("Asia/Shanghai"))

    messages = build_react_messages(
        user_query="诊断束流状况",
        time_window=None,
        scope=None,
        conversation_context=None,
        rag_context=None,
        tool_specs=[],
        skill_specs=[],
        react_history=[],
        observations=[{"output": {"time": observed_at}}],
        evidence=[{"time": observed_at}],
        candidate_causes=[{"time": observed_at}],
    )

    payload = json.loads(messages[1]["content"])
    assert payload["recent_observations"][0]["output"]["time"] == "2026-05-24T22:32:17+08:00"
    assert payload["evidence"][0]["time"] == "2026-05-24T22:32:17+08:00"
    assert payload["candidate_causes"][0]["time"] == "2026-05-24T22:32:17+08:00"

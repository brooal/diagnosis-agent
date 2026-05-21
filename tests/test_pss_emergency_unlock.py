from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.pss_emergency_unlock import analyze_pss_emergency_unlock
from app.skills import build_skill_registry
from app.tools.base import ToolResult, get_tool_registry, set_tool_runtime


class FakePssSettings:
    pss_pv_prefix = "HALF-BTP:PSS:"
    pss_event_lookback_seconds = 120
    pss_event_lookahead_seconds = 30


class FakePssTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append((name, arguments))
        if name != "diagnose_pss_emergency_unlock":
            raise AssertionError(f"unexpected tool call: {name}")
        output = analyze_pss_emergency_unlock(**arguments)
        return ToolResult(ok=True, summary=output["summary"], output=output)


def test_analyze_pss_emergency_unlock_uses_demo_data() -> None:
    output = analyze_pss_emergency_unlock(use_demo_data=True)

    assert output["event_found"] is True
    assert output["event_type"] == "pss_emergency_unlock"
    assert output["primary_cause"]["cause_type"] == "pss_emergency_stop"
    assert output["primary_cause"]["pv"] == "HALF-BTP:PSS:emergencyStopButton_3:bi"


def test_analyze_pss_emergency_unlock_accepts_event_records() -> None:
    output = analyze_pss_emergency_unlock(
        event={
            "pv": "HALF-BTP:PSS:sysStatus_Eunlocked:bi",
            "value": 1,
            "time": "2026-05-21T10:03:15+08:00",
        },
        context_events=[
            {
                "pv": "HALF-BTP:PSS:gammaOverlimit_2:bi",
                "value": 1,
                "time": "2026-05-21T10:03:12+08:00",
            },
            {
                "pv": "HALF-BTP:PSS:sysStatus_Eunlocked:bi",
                "value": 1,
                "time": "2026-05-21T10:03:15+08:00",
            },
        ],
    )

    assert output["event_found"] is True
    assert output["primary_cause"]["cause_type"] == "pss_gamma_overlimit"
    assert output["primary_cause"]["offset_seconds"] == -3.0


def test_analyze_pss_emergency_unlock_reports_no_event() -> None:
    output = analyze_pss_emergency_unlock(
        context_events=[
            {
                "pv": "HALF-BTP:PSS:sysStatus_unlocked:bi",
                "value": 1,
                "time": "2026-05-21T10:03:15+08:00",
            }
        ]
    )

    assert output["event_found"] is False
    assert output["primary_cause"] is None


def test_pss_tool_is_registered_as_hidden_diagnosis_tool() -> None:
    importlib.import_module("app.tools.diagnosis_tools")
    registry = get_tool_registry()
    set_tool_runtime(settings=FakePssSettings())

    spec = registry.get("diagnose_pss_emergency_unlock")
    assert spec.category == "diagnosis"
    assert spec.read_only is True
    assert spec.expose_to_agent is False

    result = registry.call("diagnose_pss_emergency_unlock", {"use_demo_data": True})
    assert result.ok
    assert result.output["primary_cause"]["cause_type"] == "pss_emergency_stop"


def test_pss_emergency_unlock_skill_calls_tool() -> None:
    registry = build_skill_registry()
    tools = FakePssTools()

    result = registry.call(
        "pss_emergency_unlock_diagnosis",
        {"use_demo_data": True},
        state={},
        tools=tools,
    )

    assert result.ok
    assert result.output["event_found"] is True
    assert result.candidate_causes[0]["cause_type"] == "pss_emergency_stop"
    assert tools.calls == [("diagnose_pss_emergency_unlock", {"use_demo_data": True})]

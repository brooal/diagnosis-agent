from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.pss_interlock_interrupt import analyze_pss_interlock_interrupt
from app.data_sources.fake_pss_archive import (
    build_current_fake_pss_raw_samples,
    build_fake_pss_archive_tables,
)
from app.skills import build_skill_registry
from app.tools.base import ToolResult, get_tool_registry, set_tool_runtime


class FakePssSettings:
    pss_pv_prefix = "HALF-TP:PSS:"
    pss_use_remote_db = False
    pss_event_lookback_seconds = 5
    pss_event_lookahead_seconds = 2


class FakePssTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append((name, arguments))
        if name != "diagnose_pss_interlock_interrupt":
            raise AssertionError(f"unexpected tool call: {name}")
        analysis_arguments = dict(arguments)
        use_remote_db = bool(analysis_arguments.pop("use_remote_db", False))
        output = analyze_pss_interlock_interrupt(
            **analysis_arguments,
            use_fake_data=not use_remote_db,
        )
        return ToolResult(ok=True, summary=output["summary"], output=output)


def test_fake_pss_archive_tables_match_real_schema_fields() -> None:
    tables = build_fake_pss_archive_tables(prefix="HALF-TP:PSS:")

    assert set(tables) == {"channel", "sample_raw"}
    assert set(tables["channel"][0]) == {
        "channel_id",
        "name",
        "descr",
        "grp_id",
        "smpl_mode_id",
        "smpl_val",
        "smpl_per",
        "retent_id",
        "retent_val",
    }
    assert set(tables["sample_raw"][0]) == {
        "smpl_time",
        "nanosecs",
        "channel_id",
        "severity_id",
        "status_id",
        "num_val",
        "float_val",
        "str_val",
        "datatype",
        "array_val",
    }


def test_analyze_pss_interlock_interrupt_uses_fake_data() -> None:
    output = analyze_pss_interlock_interrupt(use_fake_data=True, prefix="HALF-TP:PSS:")

    assert output["event_found"] is True
    assert output["event_type"] == "pss_interlock_to_unlock"
    assert output["primary_cause"]["cause_type"] == "emergency_stop"
    assert output["primary_cause"]["pv"] == "HALF-TP:PSS:emergencyStopButton_3:bi"
    assert output["companion_events"][0]["cause_type"] == "emergency_unlocked_status"


def test_analyze_pss_interlock_interrupt_accepts_event_records() -> None:
    output = analyze_pss_interlock_interrupt(
        prefix="HALF-TP:PSS:",
        context_events=[
            {
                "pv": "HALF-TP:PSS:sysStatus_interlocked:bi",
                "value": 1,
                "time": "2026-05-21T10:03:10+08:00",
            },
            {
                "pv": "HALF-TP:PSS:gammaOverlimit_2:bi",
                "value": 0,
                "time": "2026-05-21T10:03:10+08:00",
            },
            {
                "pv": "HALF-TP:PSS:gammaOverlimit_2:bi",
                "value": 1,
                "time": "2026-05-21T10:03:12+08:00",
            },
            {
                "pv": "HALF-TP:PSS:sysStatus_interlocked:bi",
                "value": 0,
                "time": "2026-05-21T10:03:14+08:00",
            },
            {
                "pv": "HALF-TP:PSS:sysStatus_unlocked:bi",
                "value": 0,
                "time": "2026-05-21T10:03:14+08:00",
            },
            {
                "pv": "HALF-TP:PSS:sysStatus_unlocked:bi",
                "value": 1,
                "time": "2026-05-21T10:03:15+08:00",
            },
            {
                "pv": "HALF-TP:PSS:sysStatus_Eunlocked:bi",
                "value": 0,
                "time": "2026-05-21T10:03:14+08:00",
            },
            {
                "pv": "HALF-TP:PSS:sysStatus_Eunlocked:bi",
                "value": 1,
                "time": "2026-05-21T10:03:15+08:00",
            },
        ],
    )

    assert output["event_found"] is True
    assert output["primary_cause"]["cause_type"] == "radiation_overlimit"
    assert output["primary_cause"]["offset_seconds"] == -3.0
    assert all(item["cause_type"] != "manual_emergency_unlock" for item in output["candidates"])


def test_analyze_pss_interlock_interrupt_reports_no_event_without_state_transition() -> None:
    output = analyze_pss_interlock_interrupt(
        prefix="HALF-TP:PSS:",
        context_events=[
            {
                "pv": "HALF-TP:PSS:sysStatus_Eunlocked:bi",
                "value": 1,
                "time": "2026-05-21T10:03:15+08:00",
            }
        ],
    )

    assert output["event_found"] is False
    assert output["primary_cause"] is None


def test_pss_tool_is_registered_as_hidden_diagnosis_tool() -> None:
    importlib.import_module("app.tools.diagnosis_tools")
    registry = get_tool_registry()
    set_tool_runtime(settings=FakePssSettings())

    spec = registry.get("diagnose_pss_interlock_interrupt")
    assert spec.category == "diagnosis"
    assert spec.read_only is True
    assert spec.expose_to_agent is False

    result = registry.call("diagnose_pss_interlock_interrupt", {"use_remote_db": False})
    assert result.ok
    assert result.output["primary_cause"]["cause_type"] == "emergency_stop"


def test_pss_tool_fake_runtime_covers_expected_scenarios() -> None:
    importlib.import_module("app.tools.diagnosis_tools")
    registry = get_tool_registry()
    set_tool_runtime(settings=FakePssSettings())

    cases = [
        ("S1", "2026-05-09T09:15:00+08:00", "2026-05-09T09:20:00+08:00", "manual_unlock"),
        ("S2", "2026-05-11T14:40:00+08:00", "2026-05-11T14:45:00+08:00", "door_open"),
        ("S3", "2026-05-13T08:05:00+08:00", "2026-05-13T08:08:00+08:00", "emergency_stop"),
        (
            "S4",
            "2026-05-15T16:25:00+08:00",
            "2026-05-15T16:31:00+08:00",
            "radiation_overlimit",
        ),
        (
            "S5",
            "2026-05-17T11:50:00+08:00",
            "2026-05-17T11:56:00+08:00",
            "cardbox_not_ready",
        ),
        ("S6", "2026-05-19T19:18:00+08:00", "2026-05-19T19:25:00+08:00", "plc_io_fault"),
        ("S7", "2026-05-21T13:05:00+08:00", "2026-05-21T13:12:00+08:00", None),
    ]
    for scenario_id, start, end, cause_type in cases:
        result = registry.call(
            "diagnose_pss_interlock_interrupt",
            {
                "use_remote_db": False,
                "prefix": "HALF-TP:PSS:",
                "start": start,
                "end": end,
            },
        )

        assert result.ok, scenario_id
        assert result.output["event_found"] is True, scenario_id
        primary = result.output["primary_cause"]
        if cause_type is None:
            assert primary is None, scenario_id
            assert result.output["events"][0]["confidence"] == "low"
        else:
            assert primary["cause_type"] == cause_type, scenario_id


def test_current_fake_pss_data_uses_current_time_and_selected_scenario() -> None:
    samples, metadata = build_current_fake_pss_raw_samples(
        prefix="HALF-TP:PSS:",
        scenario_id="S4",
        current_time="2026-06-02T10:20:30+08:00",
    )

    assert metadata["mode"] == "current_fake"
    assert metadata["scenario_id"] == "S4"
    assert metadata["event_time"] == "2026-06-02T10:20:30+08:00"
    assert metadata["query_window"]["start"] == "2026-06-02T10:20:15+08:00"
    assert metadata["query_window"]["end"] == "2026-06-02T10:20:35+08:00"
    assert any(item.channel_name == "HALF-TP:PSS:gammaOverlimit_2:bi" for item in samples)


def test_pss_tool_current_fake_runtime_returns_fake_metadata() -> None:
    importlib.import_module("app.tools.diagnosis_tools")
    registry = get_tool_registry()
    set_tool_runtime(settings=FakePssSettings())

    result = registry.call(
        "diagnose_pss_interlock_interrupt",
        {
            "use_remote_db": False,
            "use_current_fake_data": True,
            "fake_scenario_id": "S5",
            "prefix": "HALF-TP:PSS:",
        },
    )

    assert result.ok
    assert result.output["event_found"] is True
    assert result.output["fake_data"]["mode"] == "current_fake"
    assert result.output["fake_data"]["scenario_id"] == "S5"
    assert result.output["primary_cause"]["cause_type"] == "cardbox_not_ready"


def test_pss_interlock_interrupt_skill_calls_tool() -> None:
    registry = build_skill_registry()
    tools = FakePssTools()

    result = registry.call(
        "pss_interlock_interrupt_diagnosis",
        {"use_remote_db": False, "prefix": "HALF-TP:PSS:"},
        state={},
        tools=tools,
    )

    assert result.ok
    assert result.output["event_found"] is True
    assert result.output["event_type"] == "pss_interlock_to_unlock"
    assert result.candidate_causes[0]["cause_type"] == "emergency_stop"
    assert tools.calls == [
        ("diagnose_pss_interlock_interrupt", {"use_remote_db": False, "prefix": "HALF-TP:PSS:"})
    ]

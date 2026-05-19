from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools import build_tool_registry
from app.tools.base import ToolRegistry, ToolResult, get_tool_registry, set_tool_runtime, tool


@dataclass
class FakeQueryResult:
    columns: list[str]
    rows: list[list[str]]
    row_count: int
    truncated: bool
    max_rows: int | None


class FakeRemoteDB:
    def ping(self) -> dict:
        return {"timezone_ok": True, "server": "fake"}

    def readonly_query(self, sql: str, max_rows: int | None = None) -> FakeQueryResult:
        return FakeQueryResult(
            columns=["id"],
            rows=[[sql]],
            row_count=1,
            truncated=False,
            max_rows=max_rows,
        )


class FakePVRepo:
    def fetch_raw_channel_samples(
        self,
        channel_ids: list[int],
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[SimpleNamespace]:
        return []

    def fetch_latest_raw_sample_before(
        self,
        channel_id: int,
        before_time: str,
    ) -> SimpleNamespace | None:
        return None

    def fetch_channel_samples(
        self,
        channel_name: str,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[SimpleNamespace]:
        samples = [
            SimpleNamespace(
                channel_name=channel_name,
                smpl_time="2026-05-06T10:00:00+09:00",
                nanosecs=0,
                float_val=500.0,
            ),
            SimpleNamespace(
                channel_name=channel_name,
                smpl_time="2026-05-06T10:02:31+09:00",
                nanosecs=0,
                float_val=10.0,
            ),
        ]
        if limit is not None:
            return samples[:limit]
        return samples

    def fetch_pattern_samples(
        self,
        pattern: str,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[SimpleNamespace]:
        samples = [
            SimpleNamespace(
                channel_name="QF01:PS:CURRENT",
                smpl_time="2026-05-06T10:02:29+09:00",
                nanosecs=0,
                float_val=100.0,
            ),
            SimpleNamespace(
                channel_name="QF01:PS:CURRENT",
                smpl_time="2026-05-06T10:02:31+09:00",
                nanosecs=0,
                float_val=0.0,
            ),
        ]
        if limit is not None:
            return samples[:limit]
        return samples


class FakeSettings:
    default_beam_channel = "RING:BEAM:CURRENT"
    beam_normal_low = 480.0
    beam_normal_high = 520.0
    beam_absolute_drop_threshold = 100.0
    beam_relative_drop_threshold = 0.4
    power_window_seconds = 10
    default_power_pattern = "%QF%"
    power_relative_drop_threshold = 0.2
    decay_lookback_minutes = 30
    decay_lookahead_minutes = 10
    decay_recovery_lookahead_minutes = 30
    decay_alarm_pre_window_minutes = 10
    decay_alarm_post_window_seconds = 60
    decay_exact_match_window_seconds = 1
    decay_drop_ratio_threshold = 0.03
    decay_abnormal_point_ratio_threshold = 0.6
    decay_abnormal_duration_seconds = 10
    decay_near_zero_ratio = 0.15
    decay_absolute_low_threshold = 100.0


def _ensure_builtin_modules_loaded() -> ToolRegistry:
    for module_name in (
        "app.tools.db_tools",
        "app.tools.pv_tools",
        "app.tools.diagnosis_tools",
    ):
        importlib.import_module(module_name)
    return get_tool_registry()


def test_tool_decorator_registers_function_with_metadata() -> None:
    registry = get_tool_registry()
    unique_name = "test_inline_registry_probe"

    if any(spec["name"] == unique_name for spec in registry.list_spec(False)):
        pytest.skip("inline registry probe already registered")

    @tool(
        name=unique_name,
        description="inline registry probe",
        parameters={"type": "object", "properties": {}, "required": []},
        category="test",
        read_only=True,
        expose_to_agent=False,
    )
    def inline_registry_probe() -> ToolResult:
        return ToolResult(ok=True, summary="ok", output={"ok": True})

    spec = registry.get(unique_name)
    assert spec.name == unique_name
    assert spec.category == "test"
    assert spec.read_only is True
    assert spec.expose_to_agent is False


def test_build_tool_registry_filters_agent_visible_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DIAG_DATABASE_URL",
        "postgresql+psycopg://user:password@localhost:5432/diag",
    )
    registry = build_tool_registry()

    visible_names = {spec["name"] for spec in registry.list_spec(expose_to_agent_only=True)}
    all_names = {spec["name"] for spec in registry.list_spec(expose_to_agent_only=False)}

    assert {
        "test_db_connection",
        "readonly_sql_query",
        "fetch_beam_samples",
        "fetch_power_samples",
    } <= visible_names
    assert "diagnose_beam_fault" not in visible_names
    assert "diagnose_topoff_decay" not in visible_names
    assert "diagnose_power_faults" not in visible_names
    assert "diagnose_incident" not in visible_names
    assert {
        "diagnose_beam_fault",
        "diagnose_topoff_decay",
        "diagnose_power_faults",
        "diagnose_incident",
    } <= all_names


def test_builtin_tools_use_runtime_dependencies_and_validate_required_arguments() -> None:
    registry = _ensure_builtin_modules_loaded()
    set_tool_runtime(
        remote_db=FakeRemoteDB(),
        pv_repo=FakePVRepo(),
        settings=FakeSettings(),
    )

    ping = registry.call("test_db_connection", {})
    assert ping.ok
    assert ping.output["server"] == "fake"

    missing_sql = registry.call("readonly_sql_query", {})
    assert not missing_sql.ok
    assert missing_sql.error == "missing_required_arguments"
    assert missing_sql.output == {"missing_required": ["sql"]}

    beam_samples = registry.call(
        "fetch_beam_samples",
        {
            "beam_channel": "RING:BEAM:CURRENT",
            "start": "2026-05-06T10:00:00+09:00",
            "end": "2026-05-06T10:05:00+09:00",
        },
    )
    assert beam_samples.ok
    assert len(beam_samples.output) == 2

    missing_fault_time = registry.call("diagnose_power_faults", {})
    assert not missing_fault_time.ok
    assert missing_fault_time.error == "missing_required_arguments"

    beam_fault = registry.call(
        "diagnose_beam_fault",
        {
            "start": "2026-05-06T10:00:00+09:00",
            "end": "2026-05-06T10:05:00+09:00",
            "beam_channel": "RING:BEAM:CURRENT",
        },
    )
    assert beam_fault.ok
    assert beam_fault.output["fault_count"] == 1

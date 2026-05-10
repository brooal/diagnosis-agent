# app/tools/diagnosis_tools.py

from __future__ import annotations

from app.analysis.beam_fault import analyze_beam_faults
from app.analysis.power_fault import analyze_power_faults
from app.analysis.incident import analyze_incident
from app.config import get_settings
from app.data_sources.pv_repository import PVRepository
from app.data_sources.time_utils import build_center_window, parse_time_arg
from app.tools.base import ToolResult, ToolSpec


class DiagnosisTools:
    def __init__(self, repo: PVRepository) -> None:
        self.repo = repo
        self.settings = get_settings()

    def diagnose_beam_fault(
        self,
        start: str,
        end: str,
        beam_channel: str | None = None,
        normal_low: float | None = None,
        normal_high: float | None = None,
        absolute_drop_threshold: float | None = None,
        relative_drop_threshold: float | None = None,
    ) -> ToolResult:
        try:
            start_time = parse_time_arg(start)
            end_time = parse_time_arg(end)
            beam_channel = beam_channel or self.settings.default_beam_channel

            samples = self.repo.fetch_channel_samples(
                channel_name=beam_channel,
                start_time=start_time,
                end_time=end_time,
            )

            output = analyze_beam_faults(
                samples=samples,
                beam_channel=beam_channel,
                start_time=start_time,
                end_time=end_time,
                normal_low=normal_low or self.settings.beam_normal_low,
                normal_high=normal_high or self.settings.beam_normal_high,
                absolute_drop_threshold=(
                    absolute_drop_threshold
                    or self.settings.beam_absolute_drop_threshold
                ),
                relative_drop_threshold=(
                    relative_drop_threshold
                    or self.settings.beam_relative_drop_threshold
                ),
            )

            return ToolResult(
                ok=True,
                output=output,
                summary=output["message"],
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                output={},
                summary="束流掉束诊断失败。",
                error=f"{type(exc).__name__}: {exc}",
            )

    def diagnose_power_faults(
        self,
        fault_time: str,
        window_seconds: int | None = None,
        power_pattern: str | None = None,
        relative_drop_threshold: float | None = None,
    ) -> ToolResult:
        try:
            fault_time = parse_time_arg(fault_time)
            window_seconds = window_seconds or self.settings.power_window_seconds
            power_pattern = power_pattern or self.settings.default_power_pattern

            start_time, end_time = build_center_window(fault_time, window_seconds)

            samples = self.repo.fetch_pattern_samples(
                pattern=power_pattern,
                start_time=start_time,
                end_time=end_time,
            )

            output = analyze_power_faults(
                samples=samples,
                fault_time=fault_time,
                window_seconds=window_seconds,
                power_pattern=power_pattern,
                relative_drop_threshold=(
                    relative_drop_threshold
                    or self.settings.power_relative_drop_threshold
                ),
            )

            return ToolResult(
                ok=True,
                output=output,
                summary=output["message"],
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                output={},
                summary="电源异常定位失败。",
                error=f"{type(exc).__name__}: {exc}",
            )

    def diagnose_incident(
        self,
        start: str,
        end: str,
        beam_channel: str | None = None,
        power_pattern: str | None = None,
        window_seconds: int | None = None,
        normal_low: float | None = None,
        normal_high: float | None = None,
        absolute_drop_threshold: float | None = None,
        beam_relative_drop_threshold: float | None = None,
        power_relative_drop_threshold: float | None = None,
    ) -> ToolResult:
        try:
            start_time = parse_time_arg(start)
            end_time = parse_time_arg(end)

            output = analyze_incident(
                repo=self.repo,
                start_time=start_time,
                end_time=end_time,
                beam_channel=beam_channel,
                power_pattern=power_pattern,
                window_seconds=window_seconds,
                normal_low=normal_low,
                normal_high=normal_high,
                absolute_drop_threshold=absolute_drop_threshold,
                beam_relative_drop_threshold=beam_relative_drop_threshold,
                power_relative_drop_threshold=power_relative_drop_threshold,
            )

            return ToolResult(
                ok=True,
                output=output,
                summary=output["message"],
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                output={},
                summary="综合 incident 诊断失败。",
                error=f"{type(exc).__name__}: {exc}",
            )

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="diagnose_beam_fault",
                description=(
                    "分析一个时间段内的束流 PV，判断是否发生束流掉束。"
                    "对应旧脚本 beam-fault 命令。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "beam_channel": {"type": "string"},
                        "normal_low": {"type": "number"},
                        "normal_high": {"type": "number"},
                        "absolute_drop_threshold": {"type": "number"},
                        "relative_drop_threshold": {"type": "number"},
                    },
                    "required": ["start", "end"],
                },
                handler=self.diagnose_beam_fault,
            ),
            ToolSpec(
                name="diagnose_power_faults",
                description=(
                    "以某个束流故障时间为中心，查询前后窗口内的电源 PV，"
                    "寻找候选电源跌落。对应旧脚本 power-faults 命令。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "fault_time": {"type": "string"},
                        "window_seconds": {"type": "integer"},
                        "power_pattern": {"type": "string"},
                        "relative_drop_threshold": {"type": "number"},
                    },
                    "required": ["fault_time"],
                },
                handler=self.diagnose_power_faults,
            ),
            ToolSpec(
                name="diagnose_incident",
                description=(
                    "先检测时间段内是否存在束流掉束，再围绕掉束时间查询电源异常，"
                    "输出综合诊断结果。对应旧脚本 incident 命令。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "beam_channel": {"type": "string"},
                        "power_pattern": {"type": "string"},
                        "window_seconds": {"type": "integer"},
                        "normal_low": {"type": "number"},
                        "normal_high": {"type": "number"},
                        "absolute_drop_threshold": {"type": "number"},
                        "beam_relative_drop_threshold": {"type": "number"},
                        "power_relative_drop_threshold": {"type": "number"},
                    },
                    "required": ["start", "end"],
                },
                handler=self.diagnose_incident,
            ),
        ]
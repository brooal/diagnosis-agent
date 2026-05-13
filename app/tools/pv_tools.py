from __future__ import annotations

from app.data_sources.pv_repository import PVRepository
from app.data_sources.time_utils import parse_time_arg
from app.tools.base import ToolResult, get_tool_runtime, tool


class PVTools:
    def __init__(self, repo: PVRepository) -> None:
        self.repo = repo

    def fetch_beam_samples(
        self,
        beam_channel: str,
        start: str,
        end: str,
        limit: int | None = None,
    ) -> ToolResult:
        try:
            start_time = parse_time_arg(start)
            end_time = parse_time_arg(end)

            samples = self.repo.fetch_channel_samples(
                channel_name=beam_channel,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )

            output = [
                {
                    "channel_name": item.channel_name,
                    "smpl_time": item.smpl_time,
                    "nanosecs": item.nanosecs,
                    "float_val": item.float_val,
                }
                for item in samples
            ]

            return ToolResult(
                ok=True,
                output=output,
                summary=f"查询到 {len(samples)} 条束流通道样本。",
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                output=[],
                summary="查询束流样本失败。",
                error=f"{type(exc).__name__}: {exc}",
            )

    def fetch_power_samples(
        self,
        power_pattern: str,
        start: str,
        end: str,
        limit: int | None = None,
    ) -> ToolResult:
        try:
            start_time = parse_time_arg(start)
            end_time = parse_time_arg(end)

            samples = self.repo.fetch_pattern_samples(
                pattern=power_pattern,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )

            output = [
                {
                    "channel_name": item.channel_name,
                    "smpl_time": item.smpl_time,
                    "nanosecs": item.nanosecs,
                    "float_val": item.float_val,
                }
                for item in samples
            ]

            return ToolResult(
                ok=True,
                output=output,
                summary=f"查询到 {len(samples)} 条电源通道样本。",
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                output=[],
                summary="查询电源样本失败。",
                error=f"{type(exc).__name__}: {exc}",
            )

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="fetch_beam_samples",
                description="查询指定束流通道在时间范围内的原始样本。",
                parameters={
                    "type": "object",
                    "properties": {
                        "beam_channel": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["beam_channel", "start", "end"],
                },
                handler=self.fetch_beam_samples,
            ),
            ToolSpec(
                name="fetch_power_samples",
                description="按照 ILIKE 模式查询电源通道在时间范围内的原始样本。",
                parameters={
                    "type": "object",
                    "properties": {
                        "power_pattern": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["power_pattern", "start", "end"],
                },
                handler=self.fetch_power_samples,
            ),
        ]
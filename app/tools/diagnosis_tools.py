from __future__ import annotations

from app.analysis.beam_decay import DecayAnalysisConfig, analyze_topoff_decay
from app.analysis.beam_fault import analyze_beam_faults
from app.analysis.incident import analyze_incident
from app.analysis.power_fault import analyze_power_faults
from app.analysis.pss_emergency_unlock import analyze_pss_emergency_unlock
from app.config import get_settings
from app.data_sources.time_utils import build_center_window, parse_time_arg
from app.tools.base import ToolResult, get_tool_runtime, tool


def _diagnose_beam_fault_with(
    repo: object,
    *,
    settings: object,
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
        beam_channel = beam_channel or settings.default_beam_channel
        samples = repo.fetch_channel_samples(
            channel_name=beam_channel,
            start_time=start_time,
            end_time=end_time,
        )
        output = analyze_beam_faults(
            samples=samples,
            beam_channel=beam_channel,
            start_time=start_time,
            end_time=end_time,
            normal_low=normal_low or settings.beam_normal_low,
            normal_high=normal_high or settings.beam_normal_high,
            absolute_drop_threshold=(
                absolute_drop_threshold or settings.beam_absolute_drop_threshold
            ),
            relative_drop_threshold=(
                relative_drop_threshold or settings.beam_relative_drop_threshold
            ),
        )
        return ToolResult(ok=True, output=output, summary=output["message"])
    except Exception as exc:
        return ToolResult(
            ok=False,
            output={},
            summary="束流掉束诊断失败。",
            error=f"{type(exc).__name__}: {exc}",
        )


def _diagnose_power_faults_with(
    repo: object,
    *,
    settings: object,
    fault_time: str,
    window_seconds: int | None = None,
    power_pattern: str | None = None,
    relative_drop_threshold: float | None = None,
) -> ToolResult:
    try:
        parsed_fault_time = parse_time_arg(fault_time)
        window_seconds = window_seconds or settings.power_window_seconds
        power_pattern = power_pattern or settings.default_power_pattern
        start_time, end_time = build_center_window(parsed_fault_time, window_seconds)
        samples = repo.fetch_pattern_samples(
            pattern=power_pattern,
            start_time=start_time,
            end_time=end_time,
        )
        output = analyze_power_faults(
            samples=samples,
            fault_time=parsed_fault_time,
            window_seconds=window_seconds,
            power_pattern=power_pattern,
            relative_drop_threshold=(
                relative_drop_threshold or settings.power_relative_drop_threshold
            ),
        )
        return ToolResult(ok=True, output=output, summary=output["message"])
    except Exception as exc:
        return ToolResult(
            ok=False,
            output={},
            summary="电源异常定位失败。",
            error=f"{type(exc).__name__}: {exc}",
        )


def _diagnose_incident_with(
    repo: object,
    *,
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
            repo=repo,
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
        return ToolResult(ok=True, output=output, summary=output["message"])
    except Exception as exc:
        return ToolResult(
            ok=False,
            output={},
            summary="综合 incident 诊断失败。",
            error=f"{type(exc).__name__}: {exc}",
        )


def _diagnose_topoff_decay_with(
    repo: object,
    *,
    settings: object,
    start: str | None = None,
    end: str | None = None,
    fault_time: str | None = None,
    beam_channel: str | None = None,
    lookback_minutes: int | None = None,
    lookahead_minutes: int | None = None,
) -> ToolResult:
    try:
        config = DecayAnalysisConfig(
            lookback_minutes=lookback_minutes or settings.decay_lookback_minutes,
            lookahead_minutes=lookahead_minutes or settings.decay_lookahead_minutes,
            recovery_lookahead_minutes=settings.decay_recovery_lookahead_minutes,
            alarm_pre_window_minutes=settings.decay_alarm_pre_window_minutes,
            alarm_post_window_seconds=settings.decay_alarm_post_window_seconds,
            exact_match_window_seconds=settings.decay_exact_match_window_seconds,
            drop_ratio_threshold=settings.decay_drop_ratio_threshold,
            abnormal_point_ratio_threshold=settings.decay_abnormal_point_ratio_threshold,
            abnormal_duration_seconds=settings.decay_abnormal_duration_seconds,
            near_zero_ratio=settings.decay_near_zero_ratio,
            absolute_low_threshold=settings.decay_absolute_low_threshold,
        )
        output = analyze_topoff_decay(
            repo=repo,
            start=start,
            end=end,
            fault_time=fault_time,
            beam_channel=beam_channel or settings.default_beam_channel,
            config=config,
        )
        return ToolResult(ok=True, output=output, summary=output["message"])
    except Exception as exc:
        return ToolResult(
            ok=False,
            output={},
            summary="恒流中断/decay 诊断失败。",
            error=f"{type(exc).__name__}: {exc}",
        )


def _diagnose_pss_emergency_unlock_with(
    *,
    settings: object,
    event: dict | None = None,
    context_events: list[dict] | None = None,
    start: str | None = None,
    end: str | None = None,
    prefix: str | None = None,
    seconds_before: int | None = None,
    seconds_after: int | None = None,
    use_demo_data: bool = False,
) -> ToolResult:
    try:
        output = analyze_pss_emergency_unlock(
            event=event,
            context_events=context_events,
            prefix=prefix or settings.pss_pv_prefix,
            seconds_before=seconds_before or settings.pss_event_lookback_seconds,
            seconds_after=seconds_after or settings.pss_event_lookahead_seconds,
            start=start,
            end=end,
            use_demo_data=use_demo_data,
        )
        return ToolResult(ok=True, output=output, summary=output["summary"])
    except Exception as exc:
        return ToolResult(
            ok=False,
            output={},
            summary="PSS 紧急解锁诊断失败。",
            error=f"{type(exc).__name__}: {exc}",
        )


def _runtime_repo_and_settings() -> tuple[object | None, object]:
    runtime = get_tool_runtime()
    return runtime.pv_repo, runtime.settings or get_settings()


@tool(
    name="diagnose_beam_fault",
    description="分析一个时间段内的束流 PV，判断是否发生束流掉束。对应旧脚本 beam-fault 命令。",
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
    category="diagnosis",
    read_only=True,
    expose_to_agent=False,
)
def diagnose_beam_fault(
    start: str,
    end: str,
    beam_channel: str | None = None,
    normal_low: float | None = None,
    normal_high: float | None = None,
    absolute_drop_threshold: float | None = None,
    relative_drop_threshold: float | None = None,
) -> ToolResult:
    repo, settings = _runtime_repo_and_settings()
    if repo is None:
        return ToolResult(
            ok=False,
            output={},
            summary="PV 数据源未初始化。",
            error="missing_pv_repo",
        )
    return _diagnose_beam_fault_with(
        repo,
        settings=settings,
        start=start,
        end=end,
        beam_channel=beam_channel,
        normal_low=normal_low,
        normal_high=normal_high,
        absolute_drop_threshold=absolute_drop_threshold,
        relative_drop_threshold=relative_drop_threshold,
    )


@tool(
    name="diagnose_topoff_decay",
    description="基于 sample_raw 的 MODE/TOPOFF/温度状态量和束流曲线诊断恒流中断、decay 和相关掉束表现。",
    parameters={
        "type": "object",
        "properties": {
            "start": {"type": "string"},
            "end": {"type": "string"},
            "fault_time": {"type": "string"},
            "beam_channel": {"type": "string"},
            "lookback_minutes": {"type": "integer"},
            "lookahead_minutes": {"type": "integer"},
        },
        "required": [],
    },
    category="diagnosis",
    read_only=True,
    expose_to_agent=False,
)
def diagnose_topoff_decay(
    start: str | None = None,
    end: str | None = None,
    fault_time: str | None = None,
    beam_channel: str | None = None,
    lookback_minutes: int | None = None,
    lookahead_minutes: int | None = None,
) -> ToolResult:
    repo, settings = _runtime_repo_and_settings()
    if repo is None:
        return ToolResult(
            ok=False,
            output={},
            summary="PV 数据源未初始化。",
            error="missing_pv_repo",
        )
    return _diagnose_topoff_decay_with(
        repo,
        settings=settings,
        start=start,
        end=end,
        fault_time=fault_time,
        beam_channel=beam_channel,
        lookback_minutes=lookback_minutes,
        lookahead_minutes=lookahead_minutes,
    )


@tool(
    name="diagnose_pss_emergency_unlock",
    description="根据传入的 PSS 紧急解锁事件和上下文事件，诊断 EmergencyUnlocked 的候选原因。",
    parameters={
        "type": "object",
        "properties": {
            "event": {"type": "object"},
            "context_events": {"type": "array"},
            "start": {"type": "string"},
            "end": {"type": "string"},
            "prefix": {"type": "string"},
            "seconds_before": {"type": "integer"},
            "seconds_after": {"type": "integer"},
            "use_demo_data": {"type": "boolean"},
        },
        "required": [],
    },
    category="diagnosis",
    read_only=True,
    expose_to_agent=False,
)
def diagnose_pss_emergency_unlock(
    event: dict | None = None,
    context_events: list[dict] | None = None,
    start: str | None = None,
    end: str | None = None,
    prefix: str | None = None,
    seconds_before: int | None = None,
    seconds_after: int | None = None,
    use_demo_data: bool = False,
) -> ToolResult:
    _repo, settings = _runtime_repo_and_settings()
    return _diagnose_pss_emergency_unlock_with(
        settings=settings,
        event=event,
        context_events=context_events,
        start=start,
        end=end,
        prefix=prefix,
        seconds_before=seconds_before,
        seconds_after=seconds_after,
        use_demo_data=use_demo_data,
    )


@tool(
    name="diagnose_power_faults",
    description="以某个束流故障时间为中心，查询前后窗口内的电源 PV，寻找候选电源跌落。对应旧脚本 power-faults 命令。",
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
    category="diagnosis",
    read_only=True,
    expose_to_agent=False,
)
def diagnose_power_faults(
    fault_time: str,
    window_seconds: int | None = None,
    power_pattern: str | None = None,
    relative_drop_threshold: float | None = None,
) -> ToolResult:
    repo, settings = _runtime_repo_and_settings()
    if repo is None:
        return ToolResult(
            ok=False,
            output={},
            summary="PV 数据源未初始化。",
            error="missing_pv_repo",
        )
    return _diagnose_power_faults_with(
        repo,
        settings=settings,
        fault_time=fault_time,
        window_seconds=window_seconds,
        power_pattern=power_pattern,
        relative_drop_threshold=relative_drop_threshold,
    )


@tool(
    name="diagnose_incident",
    description="先检测时间段内是否存在束流掉束，再围绕掉束时间查询电源异常，输出综合诊断结果。对应旧脚本 incident 命令。",
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
    category="diagnosis",
    read_only=True,
    expose_to_agent=False,
)
def diagnose_incident(
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
    repo, _settings = _runtime_repo_and_settings()
    if repo is None:
        return ToolResult(
            ok=False,
            output={},
            summary="PV 数据源未初始化。",
            error="missing_pv_repo",
        )
    return _diagnose_incident_with(
        repo,
        start=start,
        end=end,
        beam_channel=beam_channel,
        power_pattern=power_pattern,
        window_seconds=window_seconds,
        normal_low=normal_low,
        normal_high=normal_high,
        absolute_drop_threshold=absolute_drop_threshold,
        beam_relative_drop_threshold=beam_relative_drop_threshold,
        power_relative_drop_threshold=power_relative_drop_threshold,
    )

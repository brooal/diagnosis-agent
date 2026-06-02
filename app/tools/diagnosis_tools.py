from __future__ import annotations

from datetime import timedelta

from app.analysis.beam_decay import DecayAnalysisConfig, analyze_topoff_decay
from app.analysis.beam_fault import analyze_beam_faults
from app.analysis.incident import analyze_incident
from app.analysis.power_fault import analyze_power_faults
from app.analysis.pss_interlock_interrupt import analyze_pss_interlock_interrupt
from app.config import get_settings
from app.data_sources.fake_pss_archive import (
    build_current_fake_pss_raw_samples,
    build_fake_pss_raw_samples,
    fake_raw_samples_to_events,
)
from app.data_sources.time_utils import build_center_window, parse_iso_datetime, parse_time_arg
from app.diagnosis.pss_catalog import pss_all_diagnosis_pv_names
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


def _diagnose_pss_interlock_interrupt_with(
    repo: object | None = None,
    *,
    settings: object,
    event: dict | None = None,
    context_events: list[dict] | None = None,
    start: str | None = None,
    end: str | None = None,
    prefix: str | None = None,
    seconds_before: int | None = None,
    seconds_after: int | None = None,
    use_remote_db: bool | None = None,
    use_current_fake_data: bool | None = None,
    fake_seed: int | str | None = None,
    fake_scenario_id: str | None = None,
) -> ToolResult:
    try:
        prefix = prefix or settings.pss_pv_prefix
        context_events = list(context_events or [])
        fake_metadata: dict | None = None
        should_use_remote_db = settings.pss_use_remote_db if use_remote_db is None else use_remote_db
        if use_current_fake_data and not context_events and not event:
            samples, fake_metadata = build_current_fake_pss_raw_samples(
                prefix=prefix,
                fake_seed=fake_seed,
                scenario_id=fake_scenario_id,
            )
            context_events = fake_raw_samples_to_events(samples)
            if start is None:
                start = fake_metadata["query_window"]["start"]
            if end is None:
                end = fake_metadata["query_window"]["end"]
            should_use_remote_db = False
        elif not context_events and not event and not should_use_remote_db:
            samples = build_fake_pss_raw_samples(prefix=prefix, start=start, end=end)
            context_events = fake_raw_samples_to_events(samples)
        elif repo is not None and start and end and not context_events:
            start_dt = parse_time_arg(start)
            end_dt = parse_time_arg(end)
            start_iso = (
                parse_iso_datetime(start_dt) - timedelta(seconds=seconds_before or 5)
            ).isoformat()
            end_iso = (
                parse_iso_datetime(end_dt) + timedelta(seconds=seconds_after or 2)
            ).isoformat()
            samples = repo.fetch_raw_pv_samples(
                pv_names=pss_all_diagnosis_pv_names(prefix=prefix),
                start_time=start_iso,
                end_time=end_iso,
            )
            context_events = [
                {
                    "pv": item.channel_name,
                    "value": item.num_val,
                    "time": item.smpl_time,
                    "nanosecs": item.nanosecs,
                }
                for item in samples
                if item.channel_name is not None
            ]
        output = analyze_pss_interlock_interrupt(
            event=event,
            context_events=context_events,
            prefix=prefix,
            seconds_before=seconds_before or 5,
            seconds_after=seconds_after or 2,
            start=start,
            end=end,
            use_fake_data=not should_use_remote_db and not context_events,
        )
        if fake_metadata:
            output["fake_data"] = fake_metadata
        return ToolResult(ok=True, output=output, summary=output["summary"])
    except Exception as exc:
        return ToolResult(
            ok=False,
            output={},
            summary="PSS 联锁中断诊断失败。",
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
    name="diagnose_pss_interlock_interrupt",
    description=(
        "诊断 PSS 是否从 interlocked 进入 unlocked，并回溯门、急停、剂量、"
        "卡盒、PLC/IO 等联锁中断原因。sysStatus_Eunlocked 只作为辅助状态。"
    ),
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
            "use_remote_db": {"type": "boolean"},
            "use_current_fake_data": {"type": "boolean"},
            "fake_seed": {"type": "string"},
            "fake_scenario_id": {"type": "string"},
        },
        "required": [],
    },
    category="diagnosis",
    read_only=True,
    expose_to_agent=False,
)
def diagnose_pss_interlock_interrupt(
    event: dict | None = None,
    context_events: list[dict] | None = None,
    start: str | None = None,
    end: str | None = None,
    prefix: str | None = None,
    seconds_before: int | None = None,
    seconds_after: int | None = None,
    use_remote_db: bool | None = None,
    use_current_fake_data: bool | None = None,
    fake_seed: int | str | None = None,
    fake_scenario_id: str | None = None,
) -> ToolResult:
    repo, settings = _runtime_repo_and_settings()
    return _diagnose_pss_interlock_interrupt_with(
        repo,
        settings=settings,
        event=event,
        context_events=context_events,
        start=start,
        end=end,
        prefix=prefix,
        seconds_before=seconds_before,
        seconds_after=seconds_after,
        use_remote_db=use_remote_db,
        use_current_fake_data=use_current_fake_data,
        fake_seed=fake_seed,
        fake_scenario_id=fake_scenario_id,
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

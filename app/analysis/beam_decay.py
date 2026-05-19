from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.data_sources.schemas import PVRawSample, PVSample
from app.data_sources.time_utils import format_shanghai_datetime, parse_iso_datetime, parse_time_arg
from app.diagnosis.channel_catalog import (
    BEAM_CURRENT_CHANNEL,
    DECAY_ALARM_CHANNELS,
    DECAY_MODE_CHANNEL,
)


@dataclass(frozen=True)
class DecayAnalysisConfig:
    lookback_minutes: int = 30
    lookahead_minutes: int = 10
    recovery_lookahead_minutes: int = 30
    alarm_pre_window_minutes: int = 10
    alarm_post_window_seconds: int = 60
    exact_match_window_seconds: int = 1
    drop_ratio_threshold: float = 0.03
    abnormal_point_ratio_threshold: float = 0.6
    abnormal_duration_seconds: int = 10
    near_zero_ratio: float = 0.15
    absolute_low_threshold: float = 100.0


def analyze_topoff_decay(
    *,
    repo: Any,
    start: str | None = None,
    end: str | None = None,
    fault_time: str | None = None,
    beam_channel: str | None = None,
    config: DecayAnalysisConfig | None = None,
) -> dict[str, Any]:
    config = config or DecayAnalysisConfig()
    query_start, query_end = _build_query_window(start=start, end=end, fault_time=fault_time)
    lookup_start = query_start - timedelta(minutes=config.lookback_minutes)
    lookup_end = query_end + timedelta(
        minutes=max(config.lookahead_minutes, config.recovery_lookahead_minutes)
    )
    beam_channel = beam_channel or BEAM_CURRENT_CHANNEL["pv"]

    mode_channel_id = int(DECAY_MODE_CHANNEL["channel_id"])
    mode_samples = repo.fetch_raw_channel_samples(
        [mode_channel_id],
        format_shanghai_datetime(lookup_start),
        format_shanghai_datetime(lookup_end),
    )
    latest_mode_before_query = _fetch_latest_raw_sample_before(
        repo,
        mode_channel_id,
        format_shanghai_datetime(query_start),
    )

    events = _reconstruct_mode_events(
        mode_samples=mode_samples,
        latest_mode_before_query=latest_mode_before_query,
        query_start=query_start,
        query_end=query_end,
        lookup_end=lookup_end,
    )

    if not events:
        curve_summary = _analyze_curve_for_window(
            repo=repo,
            beam_channel=beam_channel,
            baseline_start=query_start - timedelta(minutes=5),
            baseline_end=query_start - timedelta(minutes=1),
            detect_start=query_start,
            detect_end=query_end,
            config=config,
        )
        classification = _classify_without_mode(curve_summary)
        return {
            "status": "ok",
            "query_window": _window_dict(query_start, query_end),
            "lookup_window": _window_dict(lookup_start, lookup_end),
            "event_count": 0,
            "events": [],
            "standalone_beam_curve_summary": curve_summary,
            "overall_status": classification,
            "dominant_classification": classification,
            "message": _overall_message(classification, 0),
        }

    alarm_channel_ids = [
        int(channel["channel_id"])
        for channel in DECAY_ALARM_CHANNELS.values()
        if channel.get("channel_id") is not None
    ]
    alarm_samples = repo.fetch_raw_channel_samples(
        alarm_channel_ids,
        format_shanghai_datetime(lookup_start),
        format_shanghai_datetime(lookup_end),
    )

    analyzed_events: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        reference_time = _event_reference_time(event, query_start)
        root_cause_candidates = _match_root_cause_candidates(
            repo=repo,
            event=event,
            alarm_samples=alarm_samples,
            reference_time=reference_time,
            config=config,
        )
        curve_summary = _analyze_curve_for_window(
            repo=repo,
            beam_channel=beam_channel,
            baseline_start=reference_time - timedelta(minutes=5),
            baseline_end=reference_time - timedelta(minutes=1),
            detect_start=reference_time - timedelta(seconds=30),
            detect_end=_curve_detect_end(event, reference_time, query_end, lookup_end),
            config=config,
        )
        classification = _classify_event(
            has_root_cause=bool(root_cause_candidates),
            curve_pattern=curve_summary["pattern"],
        )
        confidence = _event_confidence(
            classification=classification,
            root_cause_candidates=root_cause_candidates,
            event=event,
        )
        analyzed_events.append(
            {
                **event,
                "event_id": f"evt_{index:03d}",
                "classification": classification,
                "confidence": confidence,
                "enable_state": {"value": 1, "assumed": True},
                "root_cause_candidates": root_cause_candidates,
                "beam_curve_summary": curve_summary,
            }
        )

    classifications = Counter(event["classification"] for event in analyzed_events)
    dominant = classifications.most_common(1)[0][0]
    return {
        "status": "ok",
        "query_window": _window_dict(query_start, query_end),
        "lookup_window": _window_dict(lookup_start, lookup_end),
        "event_count": len(analyzed_events),
        "events": analyzed_events,
        "overall_status": "events_detected",
        "dominant_classification": dominant,
        "classifications": dict(classifications),
        "message": _overall_message(dominant, len(analyzed_events)),
    }


def _build_query_window(
    *,
    start: str | None,
    end: str | None,
    fault_time: str | None,
) -> tuple[datetime, datetime]:
    if fault_time and not (start and end):
        center = _to_datetime(fault_time)
        return center - timedelta(minutes=10), center + timedelta(minutes=10)
    if not start or not end:
        raise ValueError("diagnose_topoff_decay requires start/end or fault_time.")
    return _to_datetime(start), _to_datetime(end)


def _reconstruct_mode_events(
    *,
    mode_samples: list[PVRawSample],
    latest_mode_before_query: PVRawSample | None,
    query_start: datetime,
    query_end: datetime,
    lookup_end: datetime,
) -> list[dict[str, Any]]:
    timeline = sorted(mode_samples, key=_raw_sample_sort_key)
    active: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []

    if latest_mode_before_query and latest_mode_before_query.num_val == 0:
        interrupt_time = _sample_datetime(latest_mode_before_query)
        active = _new_event(
            interrupt_sample=latest_mode_before_query,
            source="active_before_query_window",
            query_start=query_start,
        )
        active["interrupt_time_in_query_window"] = query_start <= interrupt_time <= query_end

    for sample in timeline:
        value = sample.num_val
        sample_time = _sample_datetime(sample)
        if value == 0:
            if active is None:
                active = _new_event(
                    interrupt_sample=sample,
                    source=(
                        "mode_transition_in_query_window"
                        if query_start <= sample_time <= query_end
                        else "mode_transition_in_lookup_window"
                    ),
                    query_start=query_start,
                )
                active["interrupt_time_in_query_window"] = query_start <= sample_time <= query_end
            else:
                active.setdefault("duplicate_mode_zero", []).append(_sample_dict(sample))
            continue

        if value == 1 and active is not None:
            active["recover_time"] = sample.smpl_time
            active["recover_nanosecs"] = sample.nanosecs
            active["recover_time_in_query_window"] = query_start <= sample_time <= query_end
            active["duration_seconds"] = _seconds_between(
                _event_reference_time(active, query_start),
                sample_time,
            )
            events.append(active)
            active = None

    if active is not None:
        active["recover_time"] = None
        active["recover_nanosecs"] = None
        active["recover_time_in_query_window"] = False
        active["duration_seconds"] = None
        events.append(active)

    return [
        event
        for event in events
        if _event_overlaps_query(event, query_start=query_start, query_end=query_end, lookup_end=lookup_end)
    ]


def _new_event(
    *,
    interrupt_sample: PVRawSample,
    source: str,
    query_start: datetime,
) -> dict[str, Any]:
    interrupt_time = _sample_datetime(interrupt_sample)
    return {
        "interrupt_time": interrupt_sample.smpl_time,
        "interrupt_nanosecs": interrupt_sample.nanosecs,
        "interrupt_time_inferred": source == "active_before_query_window",
        "known_active_at": format_shanghai_datetime(query_start)
        if source == "active_before_query_window"
        else None,
        "recover_time": None,
        "recover_nanosecs": None,
        "duration_seconds": None,
        "mode_channel_id": interrupt_sample.channel_id,
        "event_source": source,
        "interrupt_time_in_query_window": False,
        "recover_time_in_query_window": False,
        "event_overlaps_query_window": True,
        "_interrupt_dt": interrupt_time,
    }


def _event_overlaps_query(
    event: dict[str, Any],
    *,
    query_start: datetime,
    query_end: datetime,
    lookup_end: datetime,
) -> bool:
    event_start = _event_reference_time(event, query_start)
    event_end = _to_datetime(event["recover_time"]) if event.get("recover_time") else lookup_end
    return event_start <= query_end and event_end >= query_start


def _match_root_cause_candidates(
    *,
    repo: Any,
    event: dict[str, Any],
    alarm_samples: list[PVRawSample],
    reference_time: datetime,
    config: DecayAnalysisConfig,
) -> list[dict[str, Any]]:
    event_end = _to_datetime(event["recover_time"]) if event.get("recover_time") else None
    window_start = reference_time - timedelta(minutes=config.alarm_pre_window_minutes)
    window_end = reference_time + timedelta(seconds=config.alarm_post_window_seconds)
    exact_delta = timedelta(seconds=config.exact_match_window_seconds)
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, str, int | None]] = set()

    for channel in DECAY_ALARM_CHANNELS.values():
        channel_id = int(channel["channel_id"])
        latest = _fetch_latest_raw_sample_before(
            repo,
            channel_id,
            format_shanghai_datetime(reference_time),
        )
        if latest and _is_abnormal(channel, latest.num_val):
            key = (channel_id, latest.smpl_time, latest.num_val)
            if key not in seen:
                candidates.append(
                    _cause_candidate(
                        channel=channel,
                        sample=latest,
                        reference_time=reference_time,
                        match_type="active_at_reference",
                        priority=1,
                    )
                )
                seen.add(key)

        for sample in alarm_samples:
            if sample.channel_id != channel_id or not _is_abnormal(channel, sample.num_val):
                continue
            sample_time = _sample_datetime(sample)
            in_exact = reference_time - exact_delta <= sample_time <= reference_time + exact_delta
            in_extended = window_start <= sample_time <= window_end
            overlaps_event = event_end is not None and reference_time <= sample_time <= event_end
            if not (in_exact or in_extended or overlaps_event):
                continue
            key = (channel_id, sample.smpl_time, sample.num_val)
            if key in seen:
                continue
            candidates.append(
                _cause_candidate(
                    channel=channel,
                    sample=sample,
                    reference_time=reference_time,
                    match_type="exact" if in_exact else "extended",
                    priority=0 if in_exact else 2,
                )
            )
            seen.add(key)

    candidates.sort(
        key=lambda item: (
            item["priority"],
            abs(item["offset_seconds_from_mode"])
            if item["offset_seconds_from_mode"] is not None
            else 999999,
            item["time"],
        )
    )
    return candidates


def _cause_candidate(
    *,
    channel: dict[str, Any],
    sample: PVRawSample,
    reference_time: datetime,
    match_type: str,
    priority: int,
) -> dict[str, Any]:
    sample_time = _sample_datetime(sample)
    value = sample.num_val
    return {
        "pv": channel["pv"],
        "channel_id": sample.channel_id,
        "subsystem": channel.get("subsystem"),
        "description": channel.get("description"),
        "value": value,
        "meaning": channel.get("value_map", {}).get(value, f"value_{value}"),
        "time": sample.smpl_time,
        "nanosecs": sample.nanosecs,
        "offset_seconds_from_mode": _seconds_between(reference_time, sample_time),
        "match_type": match_type,
        "priority": priority,
    }


def _analyze_curve_for_window(
    *,
    repo: Any,
    beam_channel: str,
    baseline_start: datetime,
    baseline_end: datetime,
    detect_start: datetime,
    detect_end: datetime,
    config: DecayAnalysisConfig,
) -> dict[str, Any]:
    samples = repo.fetch_channel_samples(
        channel_name=beam_channel,
        start_time=format_shanghai_datetime(min(baseline_start, detect_start)),
        end_time=format_shanghai_datetime(max(baseline_end, detect_end)),
    )
    baseline_values = [
        sample.float_val
        for sample in samples
        if baseline_start <= _sample_datetime(sample) <= baseline_end
    ]
    detect_samples = [
        sample for sample in samples if detect_start <= _sample_datetime(sample) <= detect_end
    ]
    detect_values = [sample.float_val for sample in detect_samples]
    if not baseline_values or not detect_values:
        return {
            "pattern": "uncertain",
            "beam_channel": beam_channel,
            "sample_count": len(samples),
            "baseline_sample_count": len(baseline_values),
            "detect_sample_count": len(detect_values),
            "baseline_window": _window_dict(baseline_start, baseline_end),
            "detect_window": _window_dict(detect_start, detect_end),
            "message": "束流样本不足，无法可靠判断曲线模式。",
        }

    baseline_median = statistics.median(baseline_values)
    current_median = statistics.median(detect_values)
    baseline_std = statistics.pstdev(baseline_values) if len(baseline_values) > 1 else 0.0
    baseline_mad = statistics.median(
        [abs(value - baseline_median) for value in baseline_values]
    )
    min_value = min(detect_values)
    max_value = max(detect_values)
    drop_abs = baseline_median - current_median
    drop_ratio = drop_abs / baseline_median if baseline_median else 0.0
    abnormal_threshold = baseline_median * (1 - config.drop_ratio_threshold)
    abnormal_samples = [sample for sample in detect_samples if sample.float_val < abnormal_threshold]
    abnormal_point_ratio = len(abnormal_samples) / len(detect_samples) if detect_samples else 0.0
    abnormal_duration_seconds = _abnormal_duration_seconds(abnormal_samples)
    near_zero_threshold = max(
        config.absolute_low_threshold,
        baseline_median * config.near_zero_ratio,
    )
    is_near_zero = min_value <= near_zero_threshold
    recovery = _detect_recovery(detect_samples, baseline_median, config.drop_ratio_threshold)

    if is_near_zero:
        pattern = "beam_drop"
    elif (
        drop_ratio >= config.drop_ratio_threshold
        and abnormal_point_ratio >= config.abnormal_point_ratio_threshold
        and abnormal_duration_seconds >= config.abnormal_duration_seconds
        and (
            drop_abs > 3 * baseline_std
            or drop_abs > 5 * baseline_mad
            or baseline_std == 0
            or baseline_mad == 0
        )
    ):
        pattern = "beam_decay_like"
    else:
        pattern = "normal"

    return {
        "pattern": pattern,
        "beam_channel": beam_channel,
        "sample_count": len(samples),
        "baseline_sample_count": len(baseline_values),
        "detect_sample_count": len(detect_values),
        "baseline_window": _window_dict(baseline_start, baseline_end),
        "detect_window": _window_dict(detect_start, detect_end),
        "baseline_median": baseline_median,
        "baseline_std": baseline_std,
        "baseline_mad": baseline_mad,
        "min_value": min_value,
        "max_value": max_value,
        "current_median": current_median,
        "drop_abs": drop_abs,
        "drop_ratio": drop_ratio,
        "abnormal_duration_seconds": abnormal_duration_seconds,
        "abnormal_point_ratio": abnormal_point_ratio,
        "is_near_zero": is_near_zero,
        "recovery_detected": recovery["detected"],
        "recovery_time": recovery["time"],
    }


def _classify_event(*, has_root_cause: bool, curve_pattern: str) -> str:
    if has_root_cause and curve_pattern == "beam_drop":
        return "topoff_interrupt_with_beam_drop"
    if has_root_cause:
        return "topoff_decay"
    if curve_pattern == "beam_drop":
        return "beam_drop_related_mode_interrupt"
    return "mode_interrupt_unknown"


def _classify_without_mode(curve_summary: dict[str, Any]) -> str:
    pattern = curve_summary.get("pattern")
    if pattern == "beam_drop":
        return "beam_drop"
    if pattern == "beam_decay_like":
        return "beam_decay_like_unknown"
    return "normal"


def _event_confidence(
    *,
    classification: str,
    root_cause_candidates: list[dict[str, Any]],
    event: dict[str, Any],
) -> str:
    if classification in {"topoff_decay", "topoff_interrupt_with_beam_drop"}:
        if root_cause_candidates and root_cause_candidates[0]["match_type"] == "exact":
            return "high"
        return "medium"
    if event.get("interrupt_time_inferred"):
        return "low"
    return "medium"


def _curve_detect_end(
    event: dict[str, Any],
    reference_time: datetime,
    query_end: datetime,
    lookup_end: datetime,
) -> datetime:
    if event.get("recover_time"):
        return min(_to_datetime(event["recover_time"]), lookup_end)
    return min(max(query_end, reference_time + timedelta(minutes=5)), lookup_end)


def _event_reference_time(event: dict[str, Any], fallback: datetime) -> datetime:
    raw = event.get("_interrupt_dt")
    if isinstance(raw, datetime):
        return raw
    if event.get("interrupt_time"):
        return _to_datetime(event["interrupt_time"])
    return fallback


def _is_abnormal(channel: dict[str, Any], value: int | None) -> bool:
    if value is None:
        return False
    rule = channel.get("abnormal_rule")
    if rule == "equals_1":
        return value == 1
    if rule == "equals_0":
        return value == 0
    return value != channel.get("normal_value", 0)


def _fetch_latest_raw_sample_before(
    repo: Any,
    channel_id: int,
    before_time: str,
) -> PVRawSample | None:
    method = getattr(repo, "fetch_latest_raw_sample_before", None)
    if method is None:
        return None
    return method(channel_id, before_time)


def _sample_dict(sample: PVRawSample) -> dict[str, Any]:
    return {
        "channel_id": sample.channel_id,
        "channel_name": sample.channel_name,
        "smpl_time": sample.smpl_time,
        "nanosecs": sample.nanosecs,
        "num_val": sample.num_val,
    }


def _raw_sample_sort_key(sample: PVRawSample) -> tuple[int, datetime, int]:
    return sample.channel_id, _sample_datetime(sample), sample.nanosecs


def _sample_datetime(sample: PVRawSample | PVSample) -> datetime:
    return _to_datetime(sample.smpl_time)


def _to_datetime(value: str) -> datetime:
    return parse_iso_datetime(parse_time_arg(value))


def _seconds_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds()


def _window_dict(start: datetime, end: datetime) -> dict[str, str]:
    return {"start": format_shanghai_datetime(start), "end": format_shanghai_datetime(end)}


def _abnormal_duration_seconds(samples: list[PVSample]) -> float:
    if len(samples) < 2:
        return 0.0
    return max(0.0, _seconds_between(_sample_datetime(samples[0]), _sample_datetime(samples[-1])))


def _detect_recovery(
    samples: list[PVSample],
    baseline_median: float,
    drop_ratio_threshold: float,
) -> dict[str, Any]:
    recovery_threshold = baseline_median * (1 - drop_ratio_threshold)
    for sample in samples:
        if sample.float_val >= recovery_threshold:
            return {"detected": True, "time": sample.smpl_time}
    return {"detected": False, "time": None}


def _overall_message(classification: str, event_count: int) -> str:
    if event_count:
        return f"检测到 {event_count} 个恒流中断/decay 相关事件，主分类为 {classification}。"
    if classification == "beam_decay_like_unknown":
        return "未找到 MODE=0 恒流中断事件，但束流曲线存在 decay-like 异常。"
    if classification == "beam_drop":
        return "未找到 MODE=0 恒流中断事件，但束流曲线存在掉束特征。"
    return "未找到 MODE=0 恒流中断事件，束流曲线未见明确 decay 或掉束特征。"

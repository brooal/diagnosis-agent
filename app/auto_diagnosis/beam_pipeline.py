from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import Any

from app.analysis.power_fault import analyze_power_faults
from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.schemas import BeamFaultEvent, BeamPipelineResult
from app.config import get_settings
from app.data_sources.schemas import PVRawSample, PVSample
from app.data_sources.time_utils import build_center_window, format_shanghai_datetime
from app.diagnosis.channel_catalog import DECAY_ALARM_CHANNELS, DECAY_MODE_CHANNEL


class BeamAutoDiagnosisPipeline:
    def __init__(self, repo: Any, config: AutoDiagnosisConfig):
        self.repo = repo
        self.config = config

    def run_window(self, *, start: str, end: str) -> BeamPipelineResult:
        detect_window = {"start": start, "end": end}
        try:
            beam_samples = self.repo.fetch_sample_channel_samples(
                channel_id=self.config.beam_channel_id,
                start_time=start,
                end_time=end,
            )
            beam_context_samples = _fetch_beam_context_samples(
                self.repo,
                channel_id=self.config.beam_channel_id,
                start=start,
                lookback_seconds=self.config.cause_lookback_seconds,
            )
            mode_samples = self.repo.fetch_raw_channel_samples(
                [int(DECAY_MODE_CHANNEL["channel_id"])],
                start,
                end,
            )
            previous_mode_sample = _fetch_previous_mode_sample(self.repo, start)
            alarm_samples = self.repo.fetch_raw_channel_samples(
                _alarm_channel_ids(),
                start,
                end,
            )
        except Exception as exc:
            return BeamPipelineResult(
                status="error",
                detect_window=detect_window,
                summary="束流自动诊断证据采集失败。",
                error=f"{type(exc).__name__}: {exc}",
            )

        beam_evidence = _analyze_beam_samples(
            beam_samples,
            self.config,
            context_samples=beam_context_samples,
        )
        mode_evidence = _analyze_mode_samples(
            mode_samples,
            previous_sample=previous_mode_sample,
            window_start=start,
        )
        alarm_evidence = _analyze_alarm_samples(alarm_samples)
        recovery_evidence = _analyze_recovery_window(
            beam=beam_evidence,
            mode=mode_evidence,
            alarms=alarm_evidence,
            config=self.config,
        )
        classification = _classify_window(
            beam=beam_evidence,
            mode=mode_evidence,
            alarms=alarm_evidence,
        )

        evidence = {
            "detect_window": detect_window,
            "beam": beam_evidence,
            "mode": mode_evidence,
            "alarms": alarm_evidence,
            "recovery": recovery_evidence,
        }
        report_window = _report_window_for_event(
            classification,
            detect_window,
            beam_evidence,
        )
        if report_window:
            evidence["report_window"] = report_window
        if classification == "normal":
            return BeamPipelineResult(
                status="normal",
                detect_window=detect_window,
                raw_output=evidence,
                summary="当前诊断窗口内束流、MODE 和关键报警 PV 未见明确异常。",
            )

        event_time = _event_time(classification, end, mode_evidence, alarm_evidence, beam_evidence)
        quadrupole_evidence = None
        quadrupole_causes: list[dict[str, Any]] = []
        if classification == "drop":
            quadrupole_evidence = _analyze_quadrupole_power(
                repo=self.repo,
                fault_time=event_time,
            )
            quadrupole_causes = _quadrupole_causes(quadrupole_evidence)
            evidence["quadrupole_power"] = quadrupole_evidence

        primary = _primary_cause(classification, alarm_evidence, quadrupole_causes)
        event = BeamFaultEvent(
            incident_key=_incident_key(classification, start, end, evidence),
            classification=classification,
            severity=_severity(classification, beam_evidence),
            event_time=event_time,
            summary=_summary(classification, beam_evidence, mode_evidence, primary),
            primary_cause=primary,
            candidate_causes=[*list(alarm_evidence["active_alarms"]), *quadrupole_causes],
            evidence=evidence,
        )
        return BeamPipelineResult(
            status="fault",
            detect_window=detect_window,
            events=[event],
            raw_output=evidence,
            summary=event.summary,
        )


def _fetch_beam_context_samples(
    repo: Any,
    *,
    channel_id: int,
    start: str,
    lookback_seconds: int,
) -> list[PVSample]:
    if lookback_seconds <= 0:
        return []
    try:
        start_dt = datetime.fromisoformat(str(start))
        context_start = format_shanghai_datetime(start_dt - timedelta(seconds=lookback_seconds))
        return repo.fetch_sample_channel_samples(
            channel_id=channel_id,
            start_time=context_start,
            end_time=start,
        )
    except Exception:
        return []


def build_detect_window(now: datetime, *, detect_window_seconds: int) -> tuple[str, str]:
    start = now - timedelta(seconds=detect_window_seconds)
    return format_shanghai_datetime(start), format_shanghai_datetime(now)


def _alarm_channel_ids() -> list[int]:
    return [
        int(channel["channel_id"])
        for channel in DECAY_ALARM_CHANNELS.values()
        if channel.get("channel_id") is not None
    ]


def _analyze_beam_samples(
    samples: list[PVSample],
    config: AutoDiagnosisConfig,
    *,
    context_samples: list[PVSample] | None = None,
) -> dict[str, Any]:
    values = [sample.float_val for sample in samples]
    if not values:
        return {
            "channel_id": config.beam_channel_id,
            "channel": config.beam_channel,
            "sample_count": 0,
            "context_sample_count": len(context_samples or []),
            "has_samples": False,
            "normal_range": [config.beam_normal_min, config.beam_normal_max],
            "decay_range": [config.beam_decay_min, config.beam_decay_max],
            "absolute_low_threshold": config.absolute_low_threshold,
        }

    first = values[0]
    last = values[-1]
    min_value = min(values)
    max_value = max(values)
    median = statistics.median(values)
    delta = last - first
    drop_abs = max(0.0, first - min_value)
    drop_ratio = drop_abs / first if first > 0 else 0.0
    normal_points = [
        value
        for value in values
        if config.beam_normal_min <= value <= config.beam_normal_max
    ]
    decay_band_points = [
        value
        for value in values
        if config.beam_decay_min <= value <= config.beam_decay_max
    ]
    low_points = [value for value in values if value <= config.absolute_low_threshold]
    below_normal_points = [value for value in values if value < config.beam_normal_min]
    below_normal_ratio = len(below_normal_points) / len(values)
    relative_decay = max(0.0, first - last) / first if first > 0 else 0.0
    median_below_normal_abs = max(0.0, config.beam_normal_min - median)
    drop_context = _analyze_drop_context(
        _dedupe_sort_samples([*(context_samples or []), *samples]),
        config,
    )

    return {
        "channel_id": config.beam_channel_id,
        "channel": samples[0].channel_name or config.beam_channel,
        "sample_count": len(values),
        "context_sample_count": len(context_samples or []),
        "has_samples": True,
        "first_time": samples[0].smpl_time,
        "last_time": samples[-1].smpl_time,
        "first": first,
        "last": last,
        "min": min_value,
        "max": max_value,
        "median": median,
        "delta": delta,
        "drop_abs": drop_abs,
        "drop_ratio": drop_ratio,
        "normal_range": [config.beam_normal_min, config.beam_normal_max],
        "decay_range": [config.beam_decay_min, config.beam_decay_max],
        "absolute_low_threshold": config.absolute_low_threshold,
        "normal_point_ratio": len(normal_points) / len(values),
        "below_normal_point_ratio": below_normal_ratio,
        "decay_band_point_ratio": len(decay_band_points) / len(values),
        "low_point_ratio": len(low_points) / len(values),
        "relative_decay": relative_decay,
        "median_below_normal_abs": median_below_normal_abs,
        "first_low_time": _first_low_time(samples, config.absolute_low_threshold),
        "is_all_normal": len(normal_points) == len(values),
        "is_mostly_normal": len(normal_points) / len(values) >= 0.8,
        "is_within_decay_band": len(decay_band_points) == len(values),
        "is_slight_boundary_deviation": (
            median_below_normal_abs <= 0.5
            and min_value >= config.beam_decay_min
            and relative_decay < config.decay_ratio_threshold
        ),
        "has_low_points": bool(low_points),
        "has_drop_shape": drop_context["has_drop_step"],
        "has_decay_shape": (
            first >= config.beam_normal_min
            and median < config.beam_normal_min
            and min_value >= config.beam_decay_min
            and below_normal_ratio >= 0.6
            and relative_decay >= config.decay_ratio_threshold
        ),
        "is_rising": delta > 0,
        **drop_context,
    }


def _dedupe_sort_samples(samples: list[PVSample]) -> list[PVSample]:
    dedup = {(sample.smpl_time, sample.nanosecs, sample.float_val): sample for sample in samples}
    return sorted(dedup.values(), key=lambda item: (item.smpl_time, item.nanosecs))


def _analyze_drop_context(samples: list[PVSample], config: AutoDiagnosisConfig) -> dict[str, Any]:
    if len(samples) < 2:
        return {
            "has_drop_step": False,
            "has_drop_from_baseline": False,
            "drop_baseline_value": None,
            "drop_baseline_time": None,
            "estimated_drop_start_time": None,
            "drop_start_value": None,
            "drop_min_after_start": None,
            "drop_step_ratio": None,
            "drop_ratio_from_baseline": 0.0,
        }

    best: dict[str, Any] | None = None
    for index in range(1, len(samples)):
        prev = samples[index - 1]
        curr = samples[index]
        if prev.float_val <= config.absolute_low_threshold:
            continue
        step_ratio = curr.float_val / prev.float_val if prev.float_val > 0 else 1.0
        if step_ratio > config.drop_step_ratio_threshold:
            continue

        baseline_sample = next(
            (
                sample
                for sample in reversed(samples[:index])
                if config.beam_normal_min <= sample.float_val <= config.beam_normal_max
            ),
            prev,
        )
        tail_values = [sample.float_val for sample in samples[index:]]
        min_after = min(tail_values)
        baseline_drop_ratio = (
            (baseline_sample.float_val - min_after) / baseline_sample.float_val
            if baseline_sample.float_val > 0
            else 0.0
        )
        best = {
            "has_drop_step": True,
            "has_drop_from_baseline": True,
            "drop_baseline_value": baseline_sample.float_val,
            "drop_baseline_time": baseline_sample.smpl_time,
            "estimated_drop_start_time": curr.smpl_time,
            "drop_start_value": curr.float_val,
            "drop_min_after_start": min_after,
            "drop_step_ratio": step_ratio,
            "drop_ratio_from_baseline": baseline_drop_ratio,
        }
        break

    return best or {
        "has_drop_step": False,
        "has_drop_from_baseline": False,
        "drop_baseline_value": None,
        "drop_baseline_time": None,
        "estimated_drop_start_time": None,
        "drop_start_value": None,
        "drop_min_after_start": None,
        "drop_step_ratio": None,
        "drop_ratio_from_baseline": 0.0,
    }


def _fetch_previous_mode_sample(repo: Any, start: str) -> PVRawSample | None:
    method = getattr(repo, "fetch_latest_raw_sample_before", None)
    if not callable(method):
        return None
    try:
        return method(int(DECAY_MODE_CHANNEL["channel_id"]), start)
    except Exception:
        return None


def _analyze_mode_samples(
    samples: list[PVRawSample],
    *,
    previous_sample: PVRawSample | None = None,
    window_start: str | None = None,
) -> dict[str, Any]:
    sorted_samples = sorted(samples, key=lambda item: (item.smpl_time, item.nanosecs))
    values = [sample.num_val for sample in sorted_samples if sample.num_val is not None]
    transitions = []
    for prev, curr in zip(sorted_samples, sorted_samples[1:]):
        if prev.num_val != curr.num_val:
            transitions.append(
                {
                    "from": prev.num_val,
                    "to": curr.num_val,
                    "time": curr.smpl_time,
                    "nanosecs": curr.nanosecs,
                }
            )
    zero_samples = [sample for sample in sorted_samples if sample.num_val == 0]
    one_samples = [sample for sample in sorted_samples if sample.num_val == 1]
    inherited_zero = bool(previous_sample and previous_sample.num_val == 0)
    zero_times = [_sample_event(sample) for sample in zero_samples]
    if inherited_zero:
        zero_times.insert(
            0,
            {
                "time": window_start or previous_sample.smpl_time,
                "nanosecs": previous_sample.nanosecs,
                "value": 0,
                "inherited": True,
                "source_time": previous_sample.smpl_time,
            },
        )
    return {
        "channel_id": int(DECAY_MODE_CHANNEL["channel_id"]),
        "pv": DECAY_MODE_CHANNEL["pv"],
        "sample_count": len(sorted_samples),
        "values": values,
        "previous_sample": _sample_event(previous_sample) if previous_sample else None,
        "inherited_start_value": previous_sample.num_val if previous_sample else None,
        "inherited_zero_at_window_start": inherited_zero,
        "has_zero": bool(zero_times),
        "has_one": bool(one_samples),
        "zero_times": zero_times,
        "one_times": [_sample_event(sample) for sample in one_samples],
        "transitions": transitions,
        "last_value": values[-1] if values else None,
        "effective_value": values[-1] if values else (previous_sample.num_val if previous_sample else None),
    }


def _analyze_alarm_samples(samples: list[PVRawSample]) -> dict[str, Any]:
    catalog = {
        int(channel["channel_id"]): channel
        for channel in DECAY_ALARM_CHANNELS.values()
        if channel.get("channel_id") is not None
    }
    sorted_samples = sorted(samples, key=lambda item: (item.smpl_time, item.nanosecs))
    active = []
    all_samples = []
    for sample in sorted_samples:
        channel = catalog.get(sample.channel_id, {})
        value = sample.num_val
        event = {
            "pv": sample.channel_name or channel.get("pv"),
            "channel_id": sample.channel_id,
            "value": value,
            "meaning": (channel.get("value_map") or {}).get(value),
            "subsystem": channel.get("subsystem"),
            "description": channel.get("description"),
            "time": sample.smpl_time,
            "nanosecs": sample.nanosecs,
        }
        all_samples.append(event)
        if _is_alarm_active(value, channel):
            active.append(event)

    return {
        "sample_count": len(sorted_samples),
        "active_count": len(active),
        "active_alarms": active,
        "samples": all_samples,
        "has_beam_error": any(_is_beam_error(item) for item in active),
        "has_injection_efficiency_error": any(
            item.get("pv") == "RNG:TOPOFF:IE:Err:mbbo" for item in active
        ),
    }


def _classify_window(
    *,
    beam: dict[str, Any],
    mode: dict[str, Any],
    alarms: dict[str, Any],
) -> str:
    if (
        beam.get("has_low_points")
        or beam.get("has_drop_shape")
        or beam.get("has_drop_from_baseline")
        or alarms.get("has_beam_error")
    ):
        return "drop"
    if mode["has_zero"]:
        return "decay"
    if beam.get("has_samples") and beam.get("has_decay_shape"):
        return "decay"
    return "normal"


def _analyze_recovery_window(
    *,
    beam: dict[str, Any],
    mode: dict[str, Any],
    alarms: dict[str, Any],
    config: AutoDiagnosisConfig,
) -> dict[str, Any]:
    beam_median = beam.get("median")
    beam_median_normal = bool(
        beam.get("has_samples")
        and beam_median is not None
        and config.beam_normal_min <= beam_median <= config.beam_normal_max
    )
    beam_points_normal = bool(
        beam.get("has_samples")
        and float(beam.get("normal_point_ratio") or 0.0) >= 0.8
    )
    mode_is_one = mode.get("effective_value") == 1 and not mode.get("has_zero")
    no_beam_error = not alarms.get("has_beam_error")
    return {
        "is_recovered_window": bool(
            beam.get("has_samples")
            and beam_median_normal
            and beam_points_normal
            and mode_is_one
            and no_beam_error
        ),
        "beam_samples_present": bool(beam.get("has_samples")),
        "beam_median_normal": beam_median_normal,
        "beam_normal_point_ratio": beam.get("normal_point_ratio"),
        "beam_normal_point_ratio_required": 0.8,
        "mode_effective_value": mode.get("effective_value"),
        "mode_is_one_without_zero": mode_is_one,
        "no_beam_error": no_beam_error,
    }


def _first_low_time(samples: list[PVSample], threshold: float) -> str | None:
    for sample in samples:
        if sample.float_val <= threshold:
            return sample.smpl_time
    return None


def _primary_cause(
    classification: str,
    alarms: dict[str, Any],
    quadrupole_causes: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    quadrupole_causes = quadrupole_causes or []
    active = list(alarms["active_alarms"])
    if classification == "drop":
        for alarm in active:
            if _is_beam_error(alarm):
                return alarm
        if quadrupole_causes:
            return quadrupole_causes[0]
    if active:
        return active[0]
    return quadrupole_causes[0] if quadrupole_causes else None


def _severity(classification: str, beam: dict[str, Any]) -> str:
    if classification == "drop":
        return "critical"
    if not beam.get("has_samples"):
        return "notice"
    return "warning"


def _event_time(
    classification: str,
    end: str,
    mode: dict[str, Any],
    alarms: dict[str, Any],
    beam: dict[str, Any],
) -> str:
    if classification == "drop" and beam.get("estimated_drop_start_time"):
        return str(beam["estimated_drop_start_time"])
    if classification == "drop" and beam.get("has_low_points"):
        return str(beam.get("first_low_time") or beam.get("first_time") or end)
    if mode["zero_times"]:
        return str(mode["zero_times"][0]["time"])
    if alarms["active_alarms"]:
        return str(alarms["active_alarms"][0]["time"])
    return end


def _report_window_for_event(
    classification: str,
    detect_window: dict[str, str],
    beam: dict[str, Any],
) -> dict[str, str] | None:
    if classification == "drop" and beam.get("estimated_drop_start_time"):
        return {
            "start": str(beam["estimated_drop_start_time"]),
            "end": detect_window["end"],
        }
    return detect_window


def _incident_key(
    classification: str,
    start: str,
    end: str,
    evidence: dict[str, Any],
) -> str:
    mode = evidence["mode"]
    if mode["zero_times"]:
        return f"{classification}:mode:{mode['zero_times'][0]['time']}"
    return f"{classification}:beam:{start}:{end}"


def _summary(
    classification: str,
    beam: dict[str, Any],
    mode: dict[str, Any],
    primary: dict[str, Any] | None,
) -> str:
    beam_line = (
        f"束流中位数 {beam.get('median'):.3f}，最小值 {beam.get('min'):.3f}。"
        if beam.get("has_samples")
        else "当前窗口未查询到束流 sample 数据。"
    )
    if mode.get("inherited_zero_at_window_start"):
        mode_line = "窗口开始时 MODE 已处于 0 状态。"
    else:
        mode_line = "窗口内出现 MODE=0。" if mode["has_zero"] else "窗口内未发现 MODE=0。"
    if primary:
        cause_line = (
            f"主要候选原因：{primary.get('pv')}={primary.get('value')}"
            f" ({primary.get('meaning')})。"
        )
    else:
        cause_line = "当前窗口未匹配到明确报警 PV。"
    if classification == "drop":
        baseline = beam.get("drop_baseline_value")
        min_after = beam.get("drop_min_after_start") or beam.get("min")
        if baseline is not None and min_after is not None:
            beam_line = f"束流从故障前基准约 {baseline:.3f} 下降至最低约 {min_after:.3f}。"
        return f"检测到束流掉束现象。{beam_line}{mode_line}{cause_line}"
    return f"检测到束流 decay/恒流异常现象。{beam_line}{mode_line}{cause_line}"


def _is_alarm_active(value: int | None, channel: dict[str, Any]) -> bool:
    if value is None:
        return False
    rule = channel.get("abnormal_rule")
    normal_value = channel.get("normal_value")
    if rule == "equals_1":
        return value == 1
    if rule == "equals_0":
        return value == 0
    if rule == "nonzero":
        return value != normal_value
    return value != normal_value


def _is_beam_error(alarm: dict[str, Any]) -> bool:
    return alarm.get("pv") == "RNG:TOPOFF:BEAM:Err:mbbo" and alarm.get("value") in {1, 2}


def _sample_event(sample: PVRawSample) -> dict[str, Any]:
    return {"time": sample.smpl_time, "nanosecs": sample.nanosecs, "value": sample.num_val}


def _analyze_quadrupole_power(*, repo: Any, fault_time: str) -> dict[str, Any]:
    settings = get_settings()
    window_seconds = settings.power_window_seconds
    power_pattern = settings.default_power_pattern
    window_start, window_end = build_center_window(fault_time, window_seconds)
    try:
        samples = repo.fetch_pattern_samples(
            pattern=power_pattern,
            start_time=window_start,
            end_time=window_end,
        )
        return analyze_power_faults(
            samples=samples,
            fault_time=fault_time,
            window_seconds=window_seconds,
            power_pattern=power_pattern,
            relative_drop_threshold=settings.power_relative_drop_threshold,
        )
    except Exception as exc:
        return {
            "status": "error",
            "fault_time": fault_time,
            "window_seconds": window_seconds,
            "power_pattern": power_pattern,
            "power_fault_count": 0,
            "power_faults": [],
            "message": "Quadrupole power diagnosis failed.",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _quadrupole_causes(output: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not output or output.get("status") != "ok":
        return []
    causes = []
    for fault in output.get("power_faults") or []:
        causes.append(
            {
                "cause_type": "quadrupole_power_fault",
                "pv": fault.get("channel_name"),
                "value": fault.get("curr_val"),
                "meaning": fault.get("fault_type"),
                "subsystem": "quadrupole_power",
                "description": "四极铁电源电流在掉束时间附近出现异常下降。",
                "time": fault.get("fault_time"),
                "offset_seconds": fault.get("time_offset_from_beam_fault_seconds"),
                "evidence": fault.get("evidence"),
            }
        )
    return causes

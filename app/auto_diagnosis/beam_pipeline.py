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
            mode_samples = self.repo.fetch_raw_channel_samples(
                [int(DECAY_MODE_CHANNEL["channel_id"])],
                start,
                end,
            )
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

        beam_evidence = _analyze_beam_samples(beam_samples, self.config)
        mode_evidence = _analyze_mode_samples(mode_samples)
        alarm_evidence = _analyze_alarm_samples(alarm_samples)
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
        }
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


def build_detect_window(now: datetime, *, detect_window_seconds: int) -> tuple[str, str]:
    start = now - timedelta(seconds=detect_window_seconds)
    return format_shanghai_datetime(start), format_shanghai_datetime(now)


def _alarm_channel_ids() -> list[int]:
    return [
        int(channel["channel_id"])
        for channel in DECAY_ALARM_CHANNELS.values()
        if channel.get("channel_id") is not None
    ]


def _analyze_beam_samples(samples: list[PVSample], config: AutoDiagnosisConfig) -> dict[str, Any]:
    values = [sample.float_val for sample in samples]
    if not values:
        return {
            "channel_id": config.beam_channel_id,
            "channel": config.beam_channel,
            "sample_count": 0,
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

    return {
        "channel_id": config.beam_channel_id,
        "channel": samples[0].channel_name or config.beam_channel,
        "sample_count": len(values),
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
        "has_drop_shape": (
            first >= config.beam_decay_min
            and min_value <= config.absolute_low_threshold
            and drop_ratio >= config.drop_ratio_threshold
        ),
        "has_decay_shape": (
            first >= config.beam_normal_min
            and median < config.beam_normal_min
            and min_value >= config.beam_decay_min
            and below_normal_ratio >= 0.6
            and relative_decay >= config.decay_ratio_threshold
        ),
        "is_rising": delta > 0,
    }


def _analyze_mode_samples(samples: list[PVRawSample]) -> dict[str, Any]:
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
    return {
        "channel_id": int(DECAY_MODE_CHANNEL["channel_id"]),
        "pv": DECAY_MODE_CHANNEL["pv"],
        "sample_count": len(sorted_samples),
        "values": values,
        "has_zero": bool(zero_samples),
        "has_one": bool(one_samples),
        "zero_times": [_sample_event(sample) for sample in zero_samples],
        "one_times": [_sample_event(sample) for sample in one_samples],
        "transitions": transitions,
        "last_value": values[-1] if values else None,
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
    if alarms["has_beam_error"]:
        return "drop"
    if beam.get("has_low_points") or beam.get("has_drop_shape"):
        return "drop"
    if mode["has_zero"]:
        return "decay"
    if alarms["active_count"] > 0:
        return "decay"
    if beam.get("has_samples") and beam.get("has_decay_shape"):
        return "decay"
    return "normal"


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
    if classification == "drop" and beam.get("has_low_points"):
        return str(beam.get("first_low_time") or beam.get("first_time") or end)
    if mode["zero_times"]:
        return str(mode["zero_times"][0]["time"])
    if alarms["active_alarms"]:
        return str(alarms["active_alarms"][0]["time"])
    return end


def _incident_key(
    classification: str,
    start: str,
    end: str,
    evidence: dict[str, Any],
) -> str:
    mode = evidence["mode"]
    if mode["zero_times"]:
        return f"{classification}:mode:{mode['zero_times'][0]['time']}"
    alarms = evidence["alarms"]
    if alarms["active_alarms"]:
        alarm = alarms["active_alarms"][0]
        return f"{classification}:alarm:{alarm.get('pv')}:{alarm.get('time')}"
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
    mode_line = "窗口内出现 MODE=0。" if mode["has_zero"] else "窗口内未发现 MODE=0。"
    if primary:
        cause_line = (
            f"主要候选原因：{primary.get('pv')}={primary.get('value')}"
            f" ({primary.get('meaning')})。"
        )
    else:
        cause_line = "当前窗口未匹配到明确报警 PV。"
    if classification == "drop":
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

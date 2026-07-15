from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    normal_low: float = 480.0
    normal_high: float = 520.0
    absolute_drop_threshold: float = 100.0
    relative_drop_threshold: float = 0.4
    decay_drop_ratio_threshold: float = 0.03
    near_zero_ratio: float = 0.15
    alarm_window_seconds: int = 60


def diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _diagnose(payload)
    except Exception as exc:
        return {
            "ok": False,
            "summary": "束流状态诊断失败。",
            "error": f"{type(exc).__name__}: {exc}",
            "evidence": [],
            "candidate_causes": [],
            "output": {"phenomena": [], "recommended_next_skills": {}, "features": {}},
        }


def _diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    start = str(payload["start"])
    end = str(payload["end"])
    beam_channel = payload.get("beam_channel")
    config = _config_from(payload.get("config") or {})
    beam_samples = _sorted_samples(payload.get("beam_samples") or [])
    mode_samples = _sorted_samples(payload.get("mode_samples") or [])
    alarm_samples = _sorted_samples(payload.get("alarm_samples") or [])

    if not beam_samples:
        return _result(
            summary="诊断窗口内没有找到束流样本。",
            start=start,
            end=end,
            beam_channel=beam_channel,
            phenomena=[
                {
                    "type": "unknown",
                    "classification": "insufficient_samples",
                    "start": start,
                    "end": end,
                    "fault_time": None,
                    "confidence": 0.0,
                }
            ],
            features={"sample_count": 0},
        )

    mode_events = _mode_events(mode_samples)
    curve = _beam_curve_summary(beam_samples, config)
    if mode_events:
        return _build_mode_result(
            start=start,
            end=end,
            beam_channel=beam_channel,
            curve=curve,
            mode_events=mode_events,
            alarm_samples=alarm_samples,
            config=config,
        )

    fault = _detect_beam_fault(beam_samples, config)
    if fault["detected"]:
        return _build_trip_result(
            start=start,
            end=end,
            beam_channel=beam_channel,
            summary="诊断窗口内检测到束流掉束/突降特征。",
            classification=fault["classification"],
            fault_time=fault["fault_time"],
            confidence=fault["confidence"],
            features={"beam_fault": fault, "beam_curve": curve},
        )

    if curve["pattern"] == "beam_decay_like":
        return _result(
            summary="未发现模式中断样本，但束流曲线表现出 decay-like 异常。",
            start=start,
            end=end,
            beam_channel=beam_channel,
            phenomena=[
                {
                    "type": "topoff_decay",
                    "classification": "beam_decay_like_unknown",
                    "start": start,
                    "end": end,
                    "fault_time": None,
                    "confidence": 0.55,
                }
            ],
            candidate_causes=[],
            recommendations=[
                {
                    "name": "decay_cause_analysis",
                    "reason": "束流曲线表现为 decay-like，需要检查恒流/模式状态及相关报警 PV。",
                }
            ],
            features={"beam_curve": curve},
        )

    return _result(
        summary="诊断窗口内未检测到明确的束流掉束/突降或恒流中断/decay 特征。",
        start=start,
        end=end,
        beam_channel=beam_channel,
        phenomena=[
            {
                "type": "normal",
                "classification": "normal",
                "start": start,
                "end": end,
                "fault_time": None,
                "confidence": 0.7,
            }
        ],
        features={"beam_curve": curve},
    )


def _build_mode_result(
    *,
    start: str,
    end: str,
    beam_channel: str | None,
    curve: dict[str, Any],
    mode_events: list[dict[str, Any]],
    alarm_samples: list[dict[str, Any]],
    config: Config,
) -> dict[str, Any]:
    phenomena: list[dict[str, Any]] = []
    candidate_causes: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []

    for index, event in enumerate(mode_events, start=1):
        event_id = f"evt_{index:03d}"
        classification = _classification_for_mode_event(curve)
        phenomenon_type = "beam_trip" if "beam_drop" in classification else "topoff_decay"
        confidence = 0.75
        if curve["pattern"] in {"beam_drop", "beam_decay_like"}:
            confidence = 0.85

        phenomena.append(
            {
                "type": phenomenon_type,
                "classification": classification,
                "event_id": event_id,
                "start": start,
                "end": end,
                "fault_time": event["interrupt_time"],
                "confidence": confidence,
            }
        )

        causes = _alarm_candidates(
            alarm_samples=alarm_samples,
            reference_time=event["interrupt_time"],
            config=config,
        )
        if causes:
            primary = causes[0]
            candidate_causes.append(
                {
                    "cause_type": _cause_type(primary),
                    "description": primary.get("description"),
                    "confidence": confidence,
                    "event_id": event_id,
                    "fault_time": event["interrupt_time"],
                    "pv": primary.get("pv"),
                    "channel_id": primary.get("channel_id"),
                    "value": primary.get("value"),
                    "meaning": primary.get("meaning"),
                    "subsystem": primary.get("subsystem"),
                    "time": primary.get("time"),
                }
            )

        if phenomenon_type == "topoff_decay":
            recommendations.append(
                {
                    "name": "decay_cause_analysis",
                    "event_id": event_id,
                    "reason": f"{event_id} 检测到恒流中断/decay 或模式中断。",
                }
            )
        else:
            recommendations.append(
                {
                    "name": "quadrupole_power_diagnosis",
                    "event_id": event_id,
                    "reason": f"{event_id} 检测到束流掉束/突降特征，需要检查磁铁电源 PV。",
                }
            )

    summary = (
        f"检测到 {len(mode_events)} 个恒流/模式中断事件；"
        f"主导束流曲线模式为 {curve['pattern']}。"
    )
    return _result(
        summary=summary,
        start=start,
        end=end,
        beam_channel=beam_channel,
        phenomena=phenomena,
        candidate_causes=candidate_causes,
        recommendations=recommendations,
        features={"beam_curve": curve, "mode_events": mode_events},
    )


def _build_trip_result(
    *,
    start: str,
    end: str,
    beam_channel: str | None,
    summary: str,
    classification: str,
    fault_time: str | None,
    confidence: float,
    features: dict[str, Any],
) -> dict[str, Any]:
    return _result(
        summary=summary,
        start=start,
        end=end,
        beam_channel=beam_channel,
        phenomena=[
            {
                "type": "beam_trip",
                "classification": classification,
                "start": start,
                "end": end,
                "fault_time": fault_time,
                "confidence": confidence,
            }
        ],
        candidate_causes=[
            {
                "cause_type": "beam_trip",
                "description": "束流电流样本中存在掉束/突降特征。",
                "confidence": min(confidence, 0.8),
                "drop_time": fault_time,
            }
        ],
        recommendations=[
            {
                "name": "quadrupole_power_diagnosis",
                "reason": "检测到束流掉束/突降，需要检查四极铁电源 PV。",
            }
        ],
        features=features,
    )


def _result(
    *,
    summary: str,
    start: str,
    end: str,
    beam_channel: str | None,
    phenomena: list[dict[str, Any]],
    candidate_causes: list[dict[str, Any]] | None = None,
    recommendations: list[dict[str, Any]] | None = None,
    features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    features = features or {}
    evidence = [
        {
            "type": "beam_state_diagnosis",
            "start": start,
            "end": end,
            "beam_channel": beam_channel,
            "summary": summary,
            "features": features,
        }
    ]
    return {
        "ok": True,
        "summary": summary,
        "error": None,
        "evidence": evidence,
        "candidate_causes": candidate_causes or [],
        "output": {
            "phenomena": phenomena,
            "recommended_next_skills": recommendations or [],
            "features": features,
        },
    }


def _config_from(data: dict[str, Any]) -> Config:
    defaults = Config()
    values = {
        field: data.get(field, getattr(defaults, field))
        for field in defaults.__dataclass_fields__
    }
    return Config(**values)


def _sorted_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(samples, key=lambda item: (_parse_time(str(item["time"])), item.get("nanosecs") or 0))


def _mode_events(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    for sample in samples:
        value = sample.get("value")
        if value == 0 and active is None:
            active = {
                "interrupt_time": sample["time"],
                "interrupt_nanosecs": sample.get("nanosecs"),
                "recover_time": None,
                "recover_nanosecs": None,
            }
            continue
        if value == 1 and active is not None:
            active["recover_time"] = sample["time"]
            active["recover_nanosecs"] = sample.get("nanosecs")
            events.append(active)
            active = None
    if active is not None:
        events.append(active)
    return events


def _beam_curve_summary(samples: list[dict[str, Any]], config: Config) -> dict[str, Any]:
    values = [float(sample["value"]) for sample in samples]
    baseline = values[0]
    current = values[-1]
    min_value = min(values)
    max_value = max(values)
    drop_abs = baseline - current
    drop_ratio = drop_abs / baseline if baseline else 0.0
    near_zero_threshold = max(config.absolute_drop_threshold, baseline * config.near_zero_ratio)

    if min_value <= near_zero_threshold:
        pattern = "beam_drop"
    elif drop_ratio >= config.decay_drop_ratio_threshold:
        pattern = "beam_decay_like"
    else:
        pattern = "normal"

    return {
        "pattern": pattern,
        "sample_count": len(samples),
        "baseline_value": baseline,
        "current_value": current,
        "min_value": min_value,
        "max_value": max_value,
        "drop_abs": drop_abs,
        "drop_ratio": round(drop_ratio, 6),
        "near_zero_threshold": near_zero_threshold,
    }


def _detect_beam_fault(samples: list[dict[str, Any]], config: Config) -> dict[str, Any]:
    first_value = float(samples[0]["value"])
    if first_value < config.normal_low:
        return {
            "detected": True,
            "classification": "beam_already_low",
            "fault_time": samples[0]["time"],
            "confidence": 0.6,
            "reason": "first_sample_below_normal_low",
        }

    for prev, curr in zip(samples[:-1], samples[1:]):
        prev_value = float(prev["value"])
        curr_value = float(curr["value"])
        prev_normal = config.normal_low <= prev_value <= config.normal_high
        curr_below_normal = curr_value < config.normal_low
        if not prev_normal or not curr_below_normal:
            continue
        drop_ratio = (prev_value - curr_value) / prev_value if prev_value else 0.0
        if curr_value < config.absolute_drop_threshold or drop_ratio >= config.relative_drop_threshold:
            return {
                "detected": True,
                "classification": "beam_trip",
                "fault_time": curr["time"],
                "confidence": 0.85,
                "prev_time": prev["time"],
                "prev_value": prev_value,
                "curr_value": curr_value,
                "drop_ratio": round(drop_ratio, 6),
            }

    return {"detected": False, "classification": "normal", "fault_time": None, "confidence": 0.7}


def _classification_for_mode_event(curve: dict[str, Any]) -> str:
    if curve["pattern"] == "beam_drop":
        return "topoff_interrupt_with_beam_drop"
    if curve["pattern"] == "beam_decay_like":
        return "topoff_decay"
    return "mode_interrupt_unknown"


def _alarm_candidates(
    *,
    alarm_samples: list[dict[str, Any]],
    reference_time: str,
    config: Config,
) -> list[dict[str, Any]]:
    reference = _parse_time(reference_time)
    candidates: list[dict[str, Any]] = []
    for sample in alarm_samples:
        normal_value = sample.get("normal_value", 0)
        if sample.get("value") == normal_value:
            continue
        offset = (_parse_time(str(sample["time"])) - reference).total_seconds()
        if abs(offset) > config.alarm_window_seconds:
            continue
        candidates.append({**sample, "offset_seconds_from_mode": offset})
    candidates.sort(key=lambda item: abs(float(item["offset_seconds_from_mode"])))
    return candidates


def _cause_type(candidate: dict[str, Any]) -> str:
    subsystem = str(candidate.get("subsystem") or "topoff").lower()
    return f"topoff_{subsystem}_error"


def _parse_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _main() -> None:
    parser = argparse.ArgumentParser(description="运行可迁移束流状态诊断。")
    parser.add_argument("--input", required=True, help="输入 JSON 路径。")
    parser.add_argument("--output", required=True, help="输出 JSON 路径。")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = diagnose(payload)
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    _main()

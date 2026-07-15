from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


BEAM_CHANNEL = "RNG:BEAM:CURR"
MODE_CHANNEL = "RNG:OPERATION:MODE:bo"

ALARM_CATALOG: dict[str, dict[str, Any]] = {
    "RNG:TOPOFF:IE:Err:mbbo": {
        "cause_type": "topoff_injection_error",
        "subsystem": "injection",
        "description": "注入效率低触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "InjectingEfficiencyNormal", 1: "Injecting Efficiency Low"},
    },
    "RNG:TOPOFF:BEAM:Err:mbbo": {
        "cause_type": "topoff_beam_error",
        "subsystem": "beam",
        "description": "束流低流强或束团异常触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "Current Normal", 1: "Low Current", 2: "Bunch_Err"},
    },
    "RNG:TOPOFF:KLY:Err:mbbo": {
        "cause_type": "topoff_kly_error",
        "subsystem": "KLY",
        "description": "速调管调制器故障触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "KLY_Normal", 1: "KLY1_Err", 2: "KLY2_Err", 3: "KLY3_Err"},
    },
    "RNG:TOPOFF:RI:Err:mbbo": {
        "cause_type": "topoff_injection_system_error",
        "subsystem": "injection",
        "description": "注入系统故障触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "Injection System Normal", 1: "Kick1_Err", 5: "Septum_Err"},
    },
    "RNG:TOPOFF:MPS:Err:mbbo": {
        "cause_type": "topoff_mps_error",
        "subsystem": "MPS",
        "description": "主电源系统报警触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "MPS Normal", 2: "QPU_MPS_Err", 9: "BM_Err"},
    },
    "RNG:TOPOFF:TPS:Err:mbbo": {
        "cause_type": "topoff_tps_error",
        "subsystem": "TPS",
        "description": "TPS 或 BMPS 报警触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "TPS Normal", 1: "TPS1_Err", 13: "BMPS1_Err"},
    },
    "RNG:TOPOFF:DM:Gamma:Err:mbbo": {
        "cause_type": "topoff_dose_error",
        "subsystem": "DM",
        "description": "Gamma 剂量超标报警触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "DMGamma_NoOverdose", 1: "DMGamma6_Overdose"},
    },
    "RNG:TOPOFF:DM:Neutron:Err:mbbo": {
        "cause_type": "topoff_dose_error",
        "subsystem": "DM",
        "description": "中子剂量超标报警触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "DMNeutron_NoOverdose", 1: "DMNeutron6_Overdose"},
    },
    "RNG:BTemp:alarm:bi": {
        "cause_type": "bending_magnet_temperature_alarm",
        "subsystem": "temperature",
        "description": "二极铁温度报警触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "normal", 1: "bending_magnet_temperature_alarm"},
    },
    "RNG:STemp:alarm:bi": {
        "cause_type": "sextupole_temperature_alarm",
        "subsystem": "temperature",
        "description": "六极铁温度报警触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "normal", 1: "sextupole_temperature_alarm"},
    },
    "RNG:QTemp:alarm:bi": {
        "cause_type": "quadrupole_temperature_alarm",
        "subsystem": "temperature",
        "description": "四极铁温度报警触发恒流中断。",
        "normal_value": 0,
        "value_map": {0: "normal", 1: "quadrupole_temperature_alarm"},
    },
}


@dataclass(frozen=True)
class Config:
    beam_normal_low: float = 495.0
    beam_normal_high: float = 501.0
    beam_decay_low: float = 490.0
    beam_drop_low: float = 100.0
    beam_relative_drop_threshold: float = 0.35
    beam_decay_ratio_threshold: float = 0.01
    alarm_window_seconds: int = 60


def diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _diagnose(payload)
    except Exception as exc:
        return {
            "ok": False,
            "summary": "束流 decay/drop 诊断失败。",
            "diagnosis": _empty_diagnosis(),
            "evidence": [],
            "candidate_causes": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    config = _config_from(payload.get("config") or {})
    start = payload.get("start")
    end = payload.get("end")
    beam_channel = payload.get("beam_channel") or BEAM_CHANNEL
    beam_samples = _sorted_samples(payload.get("beam_samples") or [])
    mode_samples = _sorted_samples(payload.get("mode_samples") or [])
    alarm_samples = _sorted_samples(payload.get("alarm_samples") or [])

    curve = _beam_curve_summary(beam_samples, config, beam_channel)
    mode = _mode_summary(mode_samples)
    reference_time = mode.get("first_zero_time") or curve.get("fault_time") or start
    candidates = _alarm_candidates(alarm_samples, reference_time, config)
    beam_alarm = next((item for item in candidates if item["pv"] == "RNG:TOPOFF:BEAM:Err:mbbo"), None)

    classification = "normal"
    phenomenon_type = "normal"
    confidence = 0.7
    if curve["pattern"] == "drop" or (mode["has_zero"] and beam_alarm):
        classification = "drop"
        phenomenon_type = "beam_trip"
        confidence = 0.9 if curve["pattern"] == "drop" else 0.82
    elif mode["has_zero"] or curve["pattern"] == "decay":
        classification = "decay"
        phenomenon_type = "topoff_decay"
        confidence = 0.85 if mode["has_zero"] else 0.65

    primary = candidates[0] if classification != "normal" and candidates else None
    summary = _summary(classification, primary)
    phenomena = [
        {
            "type": phenomenon_type,
            "classification": classification,
            "start": start,
            "end": end,
            "fault_time": reference_time if classification != "normal" else None,
            "confidence": confidence,
        }
    ]
    evidence = [
        {"type": "beam_curve", **curve},
        {
            "type": "operation_mode",
            "pv": MODE_CHANNEL,
            "has_zero": mode["has_zero"],
            "first_zero_time": mode.get("first_zero_time"),
            "transition_count": len(mode["transitions"]),
        },
    ]
    if candidates:
        evidence.append({"type": "alarm_match", "reference_time": reference_time, "alarms": candidates})

    actions = []
    if classification == "drop":
        actions.append(
            {
                "name": "quadrupole_power_diagnosis",
                "reason": "束流诊断为掉束，建议继续检查四极铁电源和其他硬件原因。",
            }
        )

    return {
        "ok": True,
        "summary": summary,
        "diagnosis": {
            "phenomena": phenomena,
            "primary_cause": primary,
            "candidate_causes": candidates,
            "evidence": evidence,
            "recommended_actions": actions,
            "details": {"curve": curve, "mode": mode},
        },
        "evidence": evidence,
        "candidate_causes": candidates,
        "error": None,
    }


def _summary(classification: str, primary: dict[str, Any] | None) -> str:
    if classification == "normal":
        return "诊断结果：束流状态正常，未发现明确 decay 或掉束证据。"
    if primary:
        return f"诊断结果：束流发生 {classification}，主要原因是 {primary['description']}"
    return f"诊断结果：束流发生 {classification}，但未定位到明确报警原因。"


def _beam_curve_summary(samples: list[dict[str, Any]], config: Config, beam_channel: str) -> dict[str, Any]:
    values = [_value(item) for item in samples]
    values = [float(item) for item in values if item is not None and math.isfinite(float(item))]
    if not values:
        return {"pattern": "insufficient_samples", "beam_channel": beam_channel, "sample_count": 0, "fault_time": None}

    first_value = values[0]
    last_value = values[-1]
    min_value = min(values)
    max_value = max(values)
    min_index = values.index(min_value)
    relative_drop = (first_value - min_value) / first_value if abs(first_value) > 1e-12 else 0.0
    below_normal = sum(1 for item in values if item < config.beam_normal_low)
    low_points = sum(1 for item in values if item < config.beam_drop_low)

    pattern = "normal"
    fault_time = None
    if low_points > 0 or relative_drop >= config.beam_relative_drop_threshold:
        pattern = "drop"
        fault_time = _time_text(samples[min_index])
    elif below_normal > 0 or first_value - last_value >= abs(first_value) * config.beam_decay_ratio_threshold:
        if min_value >= config.beam_decay_low or below_normal > 0:
            pattern = "decay"
            fault_time = _time_text(samples[min_index])

    return {
        "pattern": pattern,
        "beam_channel": beam_channel,
        "sample_count": len(values),
        "first_value": first_value,
        "last_value": last_value,
        "min_value": min_value,
        "max_value": max_value,
        "median_value": median(values),
        "relative_drop": relative_drop,
        "fault_time": fault_time,
    }


def _mode_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    transitions = []
    previous = None
    previous_time = None
    first_zero_time = None
    has_zero = False
    for sample in samples:
        value = _value(sample)
        if value is None:
            continue
        current = int(value)
        time = _time_text(sample)
        if current == 0:
            has_zero = True
            first_zero_time = first_zero_time or time
        if previous is not None and current != previous:
            transitions.append({"from": previous, "to": current, "time": time, "previous_time": previous_time})
        previous = current
        previous_time = time
    return {"has_zero": has_zero, "first_zero_time": first_zero_time, "transitions": transitions}


def _alarm_candidates(samples: list[dict[str, Any]], reference_time: Any, config: Config) -> list[dict[str, Any]]:
    reference_dt = _parse_time(reference_time)
    candidates = []
    for sample in samples:
        pv = _pv(sample)
        value = _value(sample)
        if not pv or value is None:
            continue
        meta = ALARM_CATALOG.get(pv, {})
        normal = meta.get("normal_value", 0)
        if int(value) == int(normal):
            continue
        time = _time_text(sample)
        sample_dt = _parse_time(time)
        offset = None
        if reference_dt and sample_dt:
            offset = (sample_dt - reference_dt).total_seconds()
            if abs(offset) > config.alarm_window_seconds:
                continue
        value_map = meta.get("value_map") or {}
        candidates.append(
            {
                "cause_type": meta.get("cause_type", "alarm_active"),
                "pv": pv,
                "value": int(value) if float(value).is_integer() else value,
                "meaning": value_map.get(int(value), str(value)),
                "subsystem": meta.get("subsystem", "unknown"),
                "description": meta.get("description", f"{pv} 出现非正常状态。"),
                "time": time,
                "offset_seconds": offset,
                "confidence": 0.9 if offset is not None and abs(offset) <= 1 else 0.75,
            }
        )
    candidates.sort(key=lambda item: (abs(item["offset_seconds"] or 0), -item["confidence"], item["pv"]))
    return candidates


def _empty_diagnosis() -> dict[str, Any]:
    return {"phenomena": [], "primary_cause": None, "candidate_causes": [], "evidence": [], "recommended_actions": []}


def _config_from(raw: dict[str, Any]) -> Config:
    return Config(**{key: raw[key] for key in Config.__dataclass_fields__ if key in raw})


def _sorted_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(samples, key=lambda item: (_parse_time(_time_text(item)) or datetime.min.replace(tzinfo=timezone.utc), int(item.get("nanosecs") or 0)))


def _time_text(sample: dict[str, Any]) -> str | None:
    value = sample.get("time") or sample.get("smpl_time") or sample.get("datetime") or sample.get("timestamp")
    if value is None:
        return None
    text = str(value)
    if text.isdigit():
        return _timestamp_to_iso(int(text))
    return text


def _pv(sample: dict[str, Any]) -> str | None:
    value = sample.get("pv") or sample.get("channel_name") or sample.get("channel") or sample.get("name")
    return None if value is None else str(value)


def _value(sample: dict[str, Any]) -> float | None:
    value = sample.get("value")
    if value is None:
        value = sample.get("float_val")
    if value is None:
        value = sample.get("num_val")
    if value is None:
        value = sample.get("str_val")
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return _parse_time(_timestamp_to_iso(int(text)))
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _timestamp_to_iso(value: int) -> str:
    digits = len(str(abs(value)))
    seconds = value / 1_000_000_000 if digits >= 18 else value / 1_000 if digits >= 13 else value
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run portable beam decay/drop diagnosis.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = diagnose(payload)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    _main()

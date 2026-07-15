from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    relative_drop_threshold: float = 0.2


def diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _diagnose(payload)
    except Exception as exc:
        return {
            "ok": False,
            "summary": "四极铁电源诊断失败。",
            "diagnosis": _empty_diagnosis(),
            "evidence": [],
            "candidate_causes": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    config = Config(**{key: (payload.get("config") or {})[key] for key in Config.__dataclass_fields__ if key in (payload.get("config") or {})})
    samples = _sorted_samples(payload.get("power_samples") or [])
    fault_time = payload.get("fault_time") or payload.get("start")
    fault_dt = _parse_time(fault_time)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        grouped.setdefault(_pv(sample) or "unknown", []).append(sample)

    faults = []
    for pv, items in grouped.items():
        items = _sorted_samples(items)
        for prev, curr in zip(items[:-1], items[1:]):
            prev_val = _value(prev)
            curr_val = _value(curr)
            if prev_val is None or curr_val is None:
                continue
            ratio = curr_val / prev_val if abs(prev_val) > 1e-12 else None
            fault_type = None
            if abs(curr_val) <= 1e-12 and abs(prev_val) > 1e-12:
                fault_type = "zero"
            elif ratio is not None and curr_val < prev_val * config.relative_drop_threshold:
                fault_type = "sharp_drop"
            if not fault_type:
                continue
            curr_time = _time_text(curr)
            curr_dt = _parse_time(curr_time)
            offset = (curr_dt - fault_dt).total_seconds() if curr_dt and fault_dt else None
            faults.append(
                {
                    "cause_type": "quadrupole_power_fault",
                    "pv": pv,
                    "fault_type": fault_type,
                    "fault_time": curr_time,
                    "prev_time": _time_text(prev),
                    "prev_value": prev_val,
                    "curr_value": curr_val,
                    "ratio_to_prev": None if ratio is None else round(ratio, 6),
                    "time_offset_from_beam_fault_seconds": offset,
                    "confidence": 0.88 if fault_type == "zero" else 0.80,
                    "description": f"四极铁电源 {pv} 电流从 {prev_val:.6g} 下降到 {curr_val:.6g}。",
                }
            )

    faults.sort(key=lambda item: (abs(item["time_offset_from_beam_fault_seconds"] or 0), item["pv"]))
    primary = faults[0] if faults else None
    summary = f"诊断结果：检测到 {len(faults)} 个四极铁电源异常。" if faults else "诊断结果：未检测到四极铁电源电流突降或掉零。"
    evidence = [
        {
            "type": "quadrupole_power_samples",
            "sample_count": len(samples),
            "channel_count": len(grouped),
            "fault_count": len(faults),
            "relative_drop_threshold": config.relative_drop_threshold,
        }
    ]
    return {
        "ok": True,
        "summary": summary,
        "diagnosis": {
            "phenomena": [
                {
                    "type": "quadrupole_power",
                    "classification": "fault" if faults else "normal",
                    "fault_time": primary.get("fault_time") if primary else None,
                    "confidence": primary.get("confidence") if primary else 0.7,
                }
            ],
            "primary_cause": primary,
            "candidate_causes": faults,
            "evidence": evidence,
            "recommended_actions": [],
        },
        "evidence": evidence,
        "candidate_causes": faults,
        "error": None,
    }


def _empty_diagnosis() -> dict[str, Any]:
    return {"phenomena": [], "primary_cause": None, "candidate_causes": [], "evidence": [], "recommended_actions": []}


def _sorted_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(samples, key=lambda item: (_parse_time(_time_text(item)) or datetime.min.replace(tzinfo=timezone.utc), int(item.get("nanosecs") or 0)))


def _time_text(sample: dict[str, Any]) -> str | None:
    value = sample.get("time") or sample.get("smpl_time") or sample.get("datetime") or sample.get("timestamp")
    return None if value is None else str(value)


def _pv(sample: dict[str, Any]) -> str | None:
    value = sample.get("pv") or sample.get("channel_name") or sample.get("channel") or sample.get("name")
    return None if value is None else str(value)


def _value(sample: dict[str, Any]) -> float | None:
    value = sample.get("value")
    if value is None:
        value = sample.get("float_val")
    if value is None:
        value = sample.get("num_val")
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run portable quadrupole power diagnosis.")
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

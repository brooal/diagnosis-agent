from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any


STATE_PVS = {
    "interlocked": "sysStatus_interlocked:bi",
    "unlocked": "sysStatus_unlocked:bi",
    "emergency_unlocked": "sysStatus_Eunlocked:bi",
}

REASON_RULES = [
    ("manual_unlock", "Order_Unlock_Button", 0, 1, 1, 0.95, "operator_command", "人工普通解锁命令触发。"),
    ("manual_emergency_unlock", "Order_EmergencyUnlock_Button", 0, 1, 1, 0.95, "operator_command", "人工紧急解锁命令触发。"),
    ("emergency_stop", "emergencyStopButton_*:bi", 1, 0, 2, 0.90, "emergency_stop", "急停按钮触发导致 PSS 联锁中断。"),
    ("radiation_overlimit", "gammaOverlimit_*:bi", 0, 1, 3, 0.88, "radiation", "Gamma 剂量超标导致 PSS 联锁中断。"),
    ("radiation_overlimit", "neutrOverlimit_*:bi", 0, 1, 3, 0.88, "radiation", "Neutron 剂量超标导致 PSS 联锁中断。"),
    ("door_open", "doorStatus_*:bi", 1, 0, 4, 0.85, "door", "运行中门打开导致 PSS 联锁中断。"),
    ("door_fault", "doorFault_*:bi", 1, 0, 4, 0.85, "door", "门状态故障导致 PSS 联锁中断。"),
    ("cardbox_not_ready", "CardboxOutput:bi", 1, 0, 5, 0.82, "access_control", "卡盒状态异常或门禁卡未全部归位导致 PSS 联锁中断。"),
    ("plc_io_fault", "PLCstatus:bi", 1, 0, 6, 0.86, "communication", "PLC 状态异常导致 PSS 联锁中断。"),
    ("plc_io_fault", "IOstationStatus_*:bi", 1, 0, 6, 0.86, "communication", "IO 子站状态异常导致 PSS 联锁中断。"),
]

AUXILIARY_RULES = [
    ("emergency_unlocked_status", "sysStatus_Eunlocked:bi", 0, 1, 20, 0.50, "state_result", "本次事件伴随紧急解锁状态置位，但该 PV 不是原因证据。"),
    ("acc_interlock_output_lost", "interlockOutputAcc:bi", 1, 0, 21, 0.50, "state_result", "加速器联锁输出掉线，作为结果状态记录。"),
    ("door_button_cardbox_interlock_output_lost", "interlockOutputDorBtnCrdbox:bi", 1, 0, 21, 0.50, "state_result", "门/按钮/卡盒联锁输出掉线，作为结果状态记录。"),
]


@dataclass(frozen=True)
class Config:
    reason_before_seconds: int = 5
    reason_after_seconds: int = 2


def diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _diagnose(payload)
    except Exception as exc:
        return {
            "ok": False,
            "summary": "PSS 安全联锁诊断失败。",
            "diagnosis": _empty_diagnosis(),
            "evidence": [],
            "candidate_causes": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    raw_config = payload.get("config") or {}
    config = Config(**{key: raw_config[key] for key in Config.__dataclass_fields__ if key in raw_config})
    samples = _sorted_samples(payload.get("pss_samples") or [])
    events = _state_events(samples)

    if not events:
        state = _latest_state(samples)
        summary = "诊断结果：诊断窗口内未检测到 PSS 联锁中断事件。"
        if state == "unlocked":
            summary = "诊断结果：PSS 当前处于解锁状态，但窗口内未找到完整的联锁到解锁跳变。"
        evidence = [{"type": "pss_state_samples", "sample_count": len(samples), "latest_state": state, "event_count": 0}]
        return {
            "ok": True,
            "summary": summary,
            "diagnosis": {
                "phenomena": [{"type": "pss_interlock", "classification": state or "normal", "fault_time": None, "confidence": 0.7}],
                "primary_cause": None,
                "candidate_causes": [],
                "evidence": evidence,
                "recommended_actions": [],
                "events": [],
            },
            "evidence": evidence,
            "candidate_causes": [],
            "error": None,
        }

    diagnosed_events = []
    all_causes = []
    all_auxiliary = []
    for event in events:
        causes = _rule_matches(samples, event["event_time"], REASON_RULES, config)
        auxiliary = _rule_matches(samples, event["event_time"], AUXILIARY_RULES, config)
        primary = causes[0] if causes else None
        all_causes.extend(causes)
        all_auxiliary.extend(auxiliary)
        diagnosed_events.append(
            {
                "event_type": "pss_interlock_to_unlock",
                "event_time": event["event_time"],
                "state_transition": event,
                "primary_cause": primary,
                "candidate_reasons": causes,
                "auxiliary_events": auxiliary,
                "summary": _event_summary(primary, auxiliary),
            }
        )

    primary_event = diagnosed_events[0]
    primary = primary_event["primary_cause"]
    evidence = [
        {"type": "pss_state_transition", "event_time": primary_event["event_time"], "trigger_pvs": primary_event["state_transition"]["trigger_pvs"]},
        {"type": "pss_auxiliary_events", "items": all_auxiliary},
    ]
    return {
        "ok": True,
        "summary": primary_event["summary"],
        "diagnosis": {
            "phenomena": [
                {
                    "type": "pss_interlock",
                    "classification": "pss_interlock_to_unlock",
                    "fault_time": primary_event["event_time"],
                    "confidence": 0.9 if primary else 0.7,
                }
            ],
            "primary_cause": primary,
            "candidate_causes": all_causes,
            "evidence": evidence,
            "recommended_actions": [{"name": "pss_operator_review", "reason": "请结合现场记录复核触发 PV 和 PSS PLC/IO 状态。"}],
            "events": diagnosed_events,
        },
        "evidence": evidence,
        "candidate_causes": all_causes,
        "error": None,
    }


def _state_events(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    interlocked = _edges(samples, STATE_PVS["interlocked"], 1, 0)
    unlocked = _edges(samples, STATE_PVS["unlocked"], 0, 1)
    events = []
    used_unlocked = set()
    for edge in interlocked:
        matched_index = None
        matched = None
        edge_dt = _parse_time(edge["time"])
        for index, item in enumerate(unlocked):
            if index in used_unlocked:
                continue
            item_dt = _parse_time(item["time"])
            if edge_dt and item_dt and abs((item_dt - edge_dt).total_seconds()) <= 2:
                matched_index = index
                matched = item
                break
        if matched_index is not None:
            used_unlocked.add(matched_index)
        event_time = matched["time"] if matched else edge["time"]
        trigger_pvs = [{"pv": edge["pv"], "change": "1 -> 0", "time": edge["time"]}]
        if matched:
            trigger_pvs.append({"pv": matched["pv"], "change": "0 -> 1", "time": matched["time"]})
        events.append({"from": "interlocked", "to": "unlocked", "event_time": event_time, "trigger_pvs": trigger_pvs})
    for index, edge in enumerate(unlocked):
        if index not in used_unlocked:
            events.append({"from": "unknown", "to": "unlocked", "event_time": edge["time"], "trigger_pvs": [{"pv": edge["pv"], "change": "0 -> 1", "time": edge["time"]}]})
    return sorted(events, key=lambda item: _parse_time(item["event_time"]) or datetime.min.replace(tzinfo=timezone.utc))


def _edges(samples: list[dict[str, Any]], suffix: str, old: int, new: int) -> list[dict[str, Any]]:
    by_pv: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        by_pv.setdefault(_pv(sample) or "", []).append(sample)
    edges = []
    for pv, items in by_pv.items():
        if _suffix(pv) != suffix:
            continue
        items = _sorted_samples(items)
        for prev, curr in zip(items[:-1], items[1:]):
            if _value(prev) == old and _value(curr) == new:
                edges.append({"pv": pv, "time": _time_text(curr)})
    return edges


def _rule_matches(samples: list[dict[str, Any]], event_time: str, rules: list[tuple[Any, ...]], config: Config) -> list[dict[str, Any]]:
    event_dt = _parse_time(event_time)
    matches = []
    for sample in samples:
        pv = _pv(sample)
        value = _value(sample)
        if pv is None or value is None:
            continue
        for cause_type, pattern, normal, abnormal, priority, confidence, subsystem, description in rules:
            if not fnmatchcase(_suffix(pv), pattern) or int(value) != int(abnormal):
                continue
            sample_time = _time_text(sample)
            sample_dt = _parse_time(sample_time)
            offset = (sample_dt - event_dt).total_seconds() if sample_dt and event_dt else None
            if offset is not None and (offset < -config.reason_before_seconds or offset > config.reason_after_seconds):
                continue
            matches.append(
                {
                    "cause_type": cause_type,
                    "pv": pv,
                    "change": f"{normal} -> {abnormal}",
                    "time": sample_time,
                    "offset_seconds": offset,
                    "priority": priority,
                    "confidence": confidence,
                    "subsystem": subsystem,
                    "description": _specific_description(cause_type, pv, description),
                }
            )
    return sorted(matches, key=lambda item: (item["priority"], abs(item["offset_seconds"] or 0), item["pv"]))


def _event_summary(primary: dict[str, Any] | None, auxiliary: list[dict[str, Any]]) -> str:
    if primary:
        text = f"诊断结果：{primary['description']}"
    else:
        text = "诊断结果：检测到 PSS 联锁中断，但未定位到明确原因 PV。"
    if any(item["cause_type"] == "emergency_unlocked_status" for item in auxiliary):
        text += " 本次事件伴随紧急解锁状态置位，但该 PV 仅作为结果状态。"
    return text


def _specific_description(cause_type: str, pv: str, fallback: str) -> str:
    suffix = _suffix(pv)
    if cause_type == "emergency_stop" and "emergencyStopButton_" in suffix:
        number = suffix.split("emergencyStopButton_", 1)[1].split(":", 1)[0]
        return f"第 {number} 个急停按钮触发导致 PSS 联锁中断。"
    if cause_type == "door_open" and "doorStatus_" in suffix:
        number = suffix.split("doorStatus_", 1)[1].split(":", 1)[0]
        return f"第 {number} 个门状态异常导致 PSS 联锁中断。"
    return fallback


def _latest_state(samples: list[dict[str, Any]]) -> str | None:
    unlocked = _latest_value(samples, STATE_PVS["unlocked"])
    interlocked = _latest_value(samples, STATE_PVS["interlocked"])
    if unlocked == 1:
        return "unlocked"
    if interlocked == 1:
        return "interlocked"
    return None


def _latest_value(samples: list[dict[str, Any]], suffix: str) -> int | None:
    selected = [item for item in samples if _suffix(_pv(item) or "") == suffix]
    if not selected:
        return None
    value = _value(_sorted_samples(selected)[-1])
    return None if value is None else int(value)


def _empty_diagnosis() -> dict[str, Any]:
    return {"phenomena": [], "primary_cause": None, "candidate_causes": [], "evidence": [], "recommended_actions": [], "events": []}


def _sorted_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(samples, key=lambda item: (_parse_time(_time_text(item)) or datetime.min.replace(tzinfo=timezone.utc), int(item.get("nanosecs") or 0)))


def _time_text(sample: dict[str, Any]) -> str | None:
    value = sample.get("time") or sample.get("smpl_time") or sample.get("datetime") or sample.get("timestamp")
    return None if value is None else str(value)


def _pv(sample: dict[str, Any]) -> str | None:
    value = sample.get("pv") or sample.get("channel_name") or sample.get("channel") or sample.get("name")
    return None if value is None else str(value)


def _value(sample: dict[str, Any]) -> int | None:
    value = sample.get("value")
    if value is None:
        value = sample.get("num_val")
    if value is None:
        value = sample.get("float_val")
    try:
        return None if value is None else int(float(value))
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


def _suffix(pv: str) -> str:
    for marker in ("PSS:", "PSS-"):
        if marker in pv:
            return pv.split(marker, 1)[1]
    return pv


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run portable PSS interlock diagnosis.")
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

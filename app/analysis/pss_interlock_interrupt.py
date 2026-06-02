from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.data_sources.time_utils import parse_iso_datetime, parse_time_arg
from app.diagnosis.pss_catalog import (
    PSS_AUXILIARY_RULES,
    PSS_COMMAND_RULES,
    PSS_REASON_RULES,
    PSS_STATE_PVS,
    full_pss_pv,
    match_pss_pattern,
    pss_prefix,
)


def analyze_pss_interlock_interrupt(
    *,
    event: dict[str, Any] | None = None,
    context_events: list[dict[str, Any]] | None = None,
    prefix: str | None = None,
    seconds_before: int = 5,
    seconds_after: int = 2,
    start: str | None = None,
    end: str | None = None,
    use_fake_data: bool = False,
    transition_window_seconds: int = 2,
) -> dict[str, Any]:
    """Diagnose PSS interlocked -> unlocked events.

    The function name is kept for compatibility with the existing tool/skill
    registration, but the diagnostic target is no longer "EmergencyUnlocked as
    trigger". The trigger is now the PSS state transition from interlocked to
    unlocked. EmergencyUnlocked is only auxiliary state evidence.
    """
    prefix = prefix or pss_prefix()
    context_events = list(context_events or [])
    if event is not None:
        context_events.append(event)
    if use_fake_data and not context_events:
        context_events = build_fake_pss_interlock_interrupt_events(prefix=prefix)

    normalized_events = [_normalize_event(item, prefix=prefix) for item in context_events]
    if start and end:
        start_dt = _to_datetime(start)
        end_dt = _to_datetime(end)
        normalized_events = [
            item
            for item in normalized_events
            if start_dt - timedelta(seconds=seconds_before)
            <= _event_time(item)
            <= end_dt + timedelta(seconds=seconds_after)
        ]

    transitions = _detect_interlock_to_unlock_events(
        normalized_events,
        prefix=prefix,
        start=start,
        end=end,
        transition_window_seconds=transition_window_seconds,
    )
    results = [
        _diagnose_transition(
            transition,
            events=normalized_events,
            prefix=prefix,
            seconds_before=seconds_before,
            seconds_after=seconds_after,
        )
        for transition in transitions
    ]

    primary_event = results[0] if results else None
    return {
        "status": "ok",
        "event_found": bool(results),
        "event_type": "pss_interlock_to_unlock",
        "event_time": primary_event["event_time"] if primary_event else None,
        "trigger": primary_event["state_transition"] if primary_event else None,
        "primary_cause": primary_event["diagnosis"]["primary_cause"] if primary_event else None,
        "candidates": primary_event["candidate_reasons"] if primary_event else [],
        "companion_events": primary_event["auxiliary_events"] if primary_event else [],
        "events": results,
        "window": {
            "seconds_before": seconds_before,
            "seconds_after": seconds_after,
            "transition_window_seconds": transition_window_seconds,
        },
        "summary": _build_overall_summary(results),
    }


def build_fake_pss_interlock_interrupt_events(*, prefix: str | None = None) -> list[dict[str, Any]]:
    prefix = prefix or pss_prefix()
    return [
        {
            "pv": full_pss_pv("sysStatus_interlocked:bi", prefix=prefix),
            "value": 1,
            "time": "2026-05-21T10:03:10+08:00",
        },
        {
            "pv": full_pss_pv("emergencyStopButton_3:bi", prefix=prefix),
            "value": 1,
            "time": "2026-05-21T10:03:10+08:00",
        },
        {
            "pv": full_pss_pv("emergencyStopButton_3:bi", prefix=prefix),
            "value": 0,
            "time": "2026-05-21T10:03:13+08:00",
        },
        {
            "pv": full_pss_pv("sysStatus_interlocked:bi", prefix=prefix),
            "value": 0,
            "time": "2026-05-21T10:03:14+08:00",
        },
        {
            "pv": full_pss_pv("sysStatus_unlocked:bi", prefix=prefix),
            "value": 0,
            "time": "2026-05-21T10:03:14+08:00",
        },
        {
            "pv": full_pss_pv("sysStatus_unlocked:bi", prefix=prefix),
            "value": 1,
            "time": "2026-05-21T10:03:15+08:00",
        },
        {
            "pv": full_pss_pv("sysStatus_Eunlocked:bi", prefix=prefix),
            "value": 0,
            "time": "2026-05-21T10:03:14+08:00",
        },
        {
            "pv": full_pss_pv("sysStatus_Eunlocked:bi", prefix=prefix),
            "value": 1,
            "time": "2026-05-21T10:03:15+08:00",
        },
    ]


def build_fake_pss_interlock_interrupt_events_with_event(
    *,
    prefix: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    events = build_fake_pss_interlock_interrupt_events(prefix=prefix)
    return events[-1], events


def _detect_interlock_to_unlock_events(
    events: list[dict[str, Any]],
    *,
    prefix: str,
    start: str | None,
    end: str | None,
    transition_window_seconds: int,
) -> list[dict[str, Any]]:
    interlocked_pv = full_pss_pv(PSS_STATE_PVS["interlocked"], prefix=prefix)
    unlocked_pv = full_pss_pv(PSS_STATE_PVS["unlocked"], prefix=prefix)
    interlocked_falls = _detect_edges(
        events,
        pv=interlocked_pv,
        normal=1,
        abnormal=0,
        prefix=prefix,
    )
    unlocked_rises = _detect_edges(
        events,
        pv=unlocked_pv,
        normal=0,
        abnormal=1,
        prefix=prefix,
    )

    if start and end:
        start_dt = _to_datetime(start)
        end_dt = _to_datetime(end)
        unlocked_rises = [
            edge for edge in unlocked_rises if start_dt <= _to_datetime(edge["time"]) <= end_dt
        ]

    transitions: list[dict[str, Any]] = []
    used_interlocked_edges: set[int] = set()
    for unlocked_edge in unlocked_rises:
        unlocked_time = _to_datetime(unlocked_edge["time"])
        matched_index = None
        matched_edge = None
        for index, interlocked_edge in enumerate(interlocked_falls):
            if index in used_interlocked_edges:
                continue
            delta = abs((_to_datetime(interlocked_edge["time"]) - unlocked_time).total_seconds())
            if delta <= transition_window_seconds:
                matched_index = index
                matched_edge = interlocked_edge
                break
        if matched_edge is None or matched_index is None:
            continue
        used_interlocked_edges.add(matched_index)
        transitions.append(
            {
                "event_time": unlocked_edge["time"],
                "interlocked_edge": matched_edge,
                "unlocked_edge": unlocked_edge,
            }
        )
    transitions.sort(key=lambda item: item["event_time"])
    return transitions


def _diagnose_transition(
    transition: dict[str, Any],
    *,
    events: list[dict[str, Any]],
    prefix: str,
    seconds_before: int,
    seconds_after: int,
) -> dict[str, Any]:
    event_time = _to_datetime(transition["event_time"])
    window_events = [
        item
        for item in events
        if event_time - timedelta(seconds=seconds_before)
        <= _event_time(item)
        <= event_time + timedelta(seconds=seconds_after)
    ]
    candidates = _detect_rule_edges(
        window_events,
        rules=PSS_COMMAND_RULES + PSS_REASON_RULES,
        prefix=prefix,
        event_time=event_time,
    )
    auxiliary_events = _detect_rule_edges(
        window_events,
        rules=PSS_AUXILIARY_RULES,
        prefix=prefix,
        event_time=event_time,
    )
    candidates = _rank_candidates(candidates)
    primary = _select_primary_candidate(candidates)
    diagnosis = _build_diagnosis(primary, candidates, auxiliary_events)
    return {
        "event_type": "PSS_INTERLOCK_TO_UNLOCK",
        "event_time": transition["event_time"],
        "state_transition": {
            "from": "interlocked",
            "to": "unlocked",
            "trigger_pvs": [
                _edge_public_view(transition["interlocked_edge"]),
                _edge_public_view(transition["unlocked_edge"]),
            ],
        },
        "diagnosis": diagnosis,
        "candidate_reasons": candidates,
        "auxiliary_events": auxiliary_events,
        "confidence": diagnosis["confidence"],
        "limitations": _limitations(primary, auxiliary_events),
        "summary": diagnosis["main_reason_text"],
    }


def _detect_rule_edges(
    events: list[dict[str, Any]],
    *,
    rules: list[dict[str, Any]],
    prefix: str,
    event_time: datetime,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for rule in rules:
        for pv in _pvs_matching_rule(events, rule, prefix=prefix):
            for edge in _detect_edges(
                events,
                pv=pv,
                normal=rule["normal"],
                abnormal=rule["abnormal"],
                prefix=prefix,
            ):
                offset = (_to_datetime(edge["time"]) - event_time).total_seconds()
                key = (rule["cause_type"], edge["pv"], edge["time"])
                if key in seen:
                    continue
                edges.append(
                    {
                        "type": rule["cause_type"],
                        "cause_type": rule["cause_type"],
                        "pv": edge["pv"],
                        "change": edge["change"],
                        "time": edge["time"],
                        "offset_seconds": offset,
                        "priority": rule["priority"],
                        "confidence": _confidence(rule["base_confidence"], offset),
                        "subsystem": rule["subsystem"],
                        "description": _specific_description(rule, edge["pv"], prefix=prefix),
                    }
                )
                seen.add(key)
    return edges


def _detect_edges(
    events: list[dict[str, Any]],
    *,
    pv: str,
    normal: int | float,
    abnormal: int | float,
    prefix: str,
) -> list[dict[str, Any]]:
    samples = sorted(
        [item for item in events if _same_pv(item["pv"], pv, prefix=prefix)],
        key=lambda item: (_event_time(item), int(item.get("nanosecs") or 0)),
    )
    edges: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for sample in samples:
        if previous is not None and previous.get("value") == normal and sample.get("value") == abnormal:
            edges.append(
                {
                    "pv": sample["pv"],
                    "time": sample["time"],
                    "prev_value": previous.get("value"),
                    "curr_value": sample.get("value"),
                    "change": f"{previous.get('value')} -> {sample.get('value')}",
                }
            )
        previous = sample
    return edges


def _pvs_matching_rule(
    events: list[dict[str, Any]],
    rule: dict[str, Any],
    *,
    prefix: str,
) -> list[str]:
    pvs = sorted(
        {
            item["pv"]
            for item in events
            if match_pss_pattern(item["pv"], rule["pattern"], prefix=prefix)
        }
    )
    return pvs


def _rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (
            item["offset_seconds"] > 0,
            abs(item["offset_seconds"]),
            item["priority"],
            item["time"],
        ),
    )


def _select_primary_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return candidates[0]


def _build_diagnosis(
    primary: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    auxiliary_events: list[dict[str, Any]],
) -> dict[str, Any]:
    if primary is None:
        return {
            "main_reason": "unknown",
            "main_reason_text": (
                "PSS 从联锁状态进入解锁状态，但当前已归档 PV 中未找到明确原因。"
                "建议检查 PLC 内部变量 OpenReady_But_UnexpectedlyTrigger、"
                "Unexpectedly_StateMark、All_IOStation_UnNormal 是否已映射到 IOC。"
            ),
            "primary_cause": None,
            "evidence": None,
            "confidence": "low",
        }
    concurrent = [
        item for item in candidates if abs(item["offset_seconds"] - primary["offset_seconds"]) <= 0.5
    ]
    if len(concurrent) > 1:
        return {
            "main_reason": "multiple_candidates",
            "main_reason_text": "多个 PSS 原因 PV 几乎同时异常，无法仅凭当前采样确定唯一先因。",
            "primary_cause": primary,
            "evidence": primary,
            "confidence": "medium",
        }
    return {
        "main_reason": primary["cause_type"],
        "main_reason_text": _main_reason_text(primary, auxiliary_events),
        "primary_cause": primary,
        "evidence": primary,
        "confidence": "high" if primary["offset_seconds"] <= 0 else "low",
    }


def _main_reason_text(primary: dict[str, Any], auxiliary_events: list[dict[str, Any]]) -> str:
    text = primary["description"]
    emergency_state = [
        item for item in auxiliary_events if item["cause_type"] == "emergency_unlocked_status"
    ]
    if emergency_state and primary["cause_type"] != "manual_emergency_unlock":
        text += " 本次事件伴随紧急解锁状态置位，但当前归档 PV 中没有人工紧急解锁命令证据。"
    return text


def _limitations(primary: dict[str, Any] | None, auxiliary_events: list[dict[str, Any]]) -> list[str]:
    limitations = [
        "当前第一版基于已归档 PV 回溯原因，不能完全复现 PLC 内部逻辑状态。",
    ]
    if primary is None:
        limitations.append(
            "未发现明确原因 PV 边沿，建议确认 OpenReady_But_UnexpectedlyTrigger 等内部变量是否归档。"
        )
    if any(item["cause_type"] == "emergency_unlocked_status" for item in auxiliary_events):
        limitations.append("sysStatus_Eunlocked:bi 仅作为伴随状态，不作为人工紧急解锁原因。")
    return limitations


def _specific_description(rule: dict[str, Any], pv: str, *, prefix: str) -> str:
    suffix = pv
    if pv.startswith(prefix):
        suffix = pv[len(prefix) :]
    index = _trailing_index(suffix)
    cause_type = rule["cause_type"]
    if cause_type == "emergency_stop" and index:
        return f"第 {index} 个急停按钮触发导致 PSS 联锁中断。"
    if cause_type == "radiation_overlimit" and index:
        kind = "Gamma" if suffix.startswith("gamma") else "Neutron"
        return f"第 {index} 路 {kind} 剂量超标导致 PSS 联锁中断。"
    if cause_type == "door_open" and index:
        return f"运行中第 {index} 扇门打开导致 PSS 联锁中断。"
    if cause_type == "door_fault" and index:
        return f"第 {index} 扇门故障导致 PSS 联锁中断。"
    if cause_type == "plc_io_fault" and suffix.startswith("IOstationStatus") and index:
        return f"第 {index} 个 IO 子站通信/硬件异常导致 PSS 联锁中断。"
    return rule["description"]


def _trailing_index(value: str) -> str | None:
    stem = value.split(":", 1)[0]
    if "_" not in stem:
        return None
    candidate = stem.rsplit("_", 1)[1]
    return candidate if candidate.isdigit() else None


def _edge_public_view(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "pv": edge["pv"],
        "change": edge["change"],
        "time": edge["time"],
    }


def _build_overall_summary(results: list[dict[str, Any]]) -> str:
    if not results:
        return "未发现 PSS interlocked -> unlocked 联锁中断事件。"
    if len(results) == 1:
        return results[0]["summary"]
    return f"发现 {len(results)} 个 PSS interlocked -> unlocked 联锁中断事件。"


def _normalize_event(event: dict[str, Any] | None, *, prefix: str) -> dict[str, Any]:
    if event is None:
        raise ValueError("PSS event cannot be None.")
    pv = str(event.get("pv") or event.get("name") or event.get("channel_name") or "").strip()
    if not pv:
        raise ValueError("PSS event requires pv.")
    normalized_pv = pv if pv.startswith(prefix) else full_pss_pv(pv, prefix=prefix)
    time = str(event.get("time") or event.get("timestamp") or event.get("smpl_time") or "").strip()
    if not time:
        raise ValueError("PSS event requires time, timestamp or smpl_time.")
    return {
        **event,
        "pv": normalized_pv,
        "value": _normalize_value(event.get("value", event.get("num_val"))),
        "time": parse_time_arg(time),
        "nanosecs": int(event.get("nanosecs") or 0),
    }


def _normalize_value(value: Any) -> int | float | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return value
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _same_pv(left: str, right: str, *, prefix: str) -> bool:
    return left == right or match_pss_pattern(left, right, prefix=prefix)


def _event_time(event: dict[str, Any]) -> datetime:
    return _to_datetime(event["time"])


def _to_datetime(value: str) -> datetime:
    return parse_iso_datetime(parse_time_arg(value))


def _confidence(base: float, offset: float) -> float:
    distance = abs(offset)
    if distance <= 2:
        return base
    if distance <= 10:
        return max(base - 0.10, 0.30)
    return max(base - 0.20, 0.20)

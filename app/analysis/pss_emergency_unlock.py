from __future__ import annotations

from datetime import datetime
from typing import Any

from app.data_sources.time_utils import parse_iso_datetime, parse_time_arg
from app.diagnosis.pss_catalog import (
    PSS_CAUSE_RULES,
    PSS_COMPANION_RULES,
    PSS_TRIGGER_CHANNEL,
    full_pss_pv,
    match_pss_pattern,
    pss_prefix,
)


def analyze_pss_emergency_unlock(
    *,
    event: dict[str, Any] | None = None,
    context_events: list[dict[str, Any]] | None = None,
    prefix: str | None = None,
    seconds_before: int = 120,
    seconds_after: int = 30,
    start: str | None = None,
    end: str | None = None,
    use_demo_data: bool = False,
) -> dict[str, Any]:
    prefix = prefix or pss_prefix()
    context_events = list(context_events or [])
    if use_demo_data and event is None and not context_events:
        event, context_events = build_demo_pss_emergency_unlock_data(prefix=prefix)

    normalized_context = [_normalize_event(item, prefix=prefix) for item in context_events]
    normalized_event = _normalize_event(event, prefix=prefix) if event else None
    trigger = _select_trigger(
        event=normalized_event,
        context_events=normalized_context,
        prefix=prefix,
        start=start,
        end=end,
    )
    if trigger is None:
        return {
            "status": "ok",
            "event_found": False,
            "event_type": "pss_emergency_unlock",
            "trigger": None,
            "primary_cause": None,
            "candidates": [],
            "companion_events": [],
            "summary": "未发现 PSS EmergencyUnlocked 紧急解锁事件记录。",
        }

    event_time = _event_time(trigger)
    window_events = [
        item
        for item in normalized_context
        if _is_in_window(item, center=event_time, seconds_before=seconds_before, seconds_after=seconds_after)
    ]
    if normalized_event and normalized_event not in window_events:
        window_events.append(normalized_event)

    candidates = _match_rules(
        events=window_events,
        rules=PSS_CAUSE_RULES,
        center=event_time,
        prefix=prefix,
        max_after_seconds=1.0,
    )
    companion_events = _match_rules(
        events=window_events,
        rules=PSS_COMPANION_RULES,
        center=event_time,
        prefix=prefix,
        max_after_seconds=1.0,
    )
    candidates.sort(key=lambda item: (item["priority"], abs(item["offset_seconds"]), item["time"]))
    companion_events.sort(key=lambda item: (item["priority"], abs(item["offset_seconds"]), item["time"]))
    primary = candidates[0] if candidates else None
    return {
        "status": "ok",
        "event_found": True,
        "event_type": "pss_emergency_unlock",
        "event_time": trigger["time"],
        "trigger": trigger,
        "primary_cause": primary,
        "candidates": candidates,
        "companion_events": companion_events,
        "window": {
            "seconds_before": seconds_before,
            "seconds_after": seconds_after,
        },
        "summary": _build_summary(trigger, primary),
    }


def build_demo_pss_emergency_unlock_data(
    *,
    prefix: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prefix = prefix or pss_prefix()
    event = {
        "pv": full_pss_pv("sysStatus_Eunlocked:bi", prefix=prefix),
        "value": 1,
        "time": "2026-05-21T10:03:15+08:00",
    }
    context_events = [
        {
            "pv": full_pss_pv("emergencyStopButton_3:bi", prefix=prefix),
            "value": 0,
            "time": "2026-05-21T10:03:13+08:00",
        },
        {
            "pv": full_pss_pv("interlockOutputDorBtnCrdbox:bi", prefix=prefix),
            "value": 0,
            "time": "2026-05-21T10:03:14+08:00",
        },
        event,
    ]
    return event, context_events


def _select_trigger(
    *,
    event: dict[str, Any] | None,
    context_events: list[dict[str, Any]],
    prefix: str,
    start: str | None,
    end: str | None,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    if event and _is_trigger(event, prefix=prefix):
        candidates.append(event)
    candidates.extend(item for item in context_events if _is_trigger(item, prefix=prefix))
    if start and end:
        start_dt = _to_datetime(start)
        end_dt = _to_datetime(end)
        candidates = [
            item for item in candidates if start_dt <= _event_time(item) <= end_dt
        ]
    if not candidates:
        return None
    candidates.sort(key=_event_time)
    return candidates[0]


def _match_rules(
    *,
    events: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    center: datetime,
    prefix: str,
    max_after_seconds: float,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | float | str | None]] = set()
    for item in events:
        offset = (_event_time(item) - center).total_seconds()
        if offset > max_after_seconds:
            continue
        for rule in rules:
            if not match_pss_pattern(item["pv"], rule["pattern"], prefix=prefix):
                continue
            if item.get("value") != rule["event_value"]:
                continue
            key = (rule["cause_type"], item["pv"], item.get("value"))
            if key in seen:
                continue
            matched.append(
                {
                    "cause_type": rule["cause_type"],
                    "pv": item["pv"],
                    "value": item.get("value"),
                    "time": item["time"],
                    "offset_seconds": offset,
                    "priority": rule["priority"],
                    "confidence": _confidence(rule["base_confidence"], offset),
                    "subsystem": rule["subsystem"],
                    "description": rule["description"],
                }
            )
            seen.add(key)
    return matched


def _is_trigger(event: dict[str, Any], *, prefix: str) -> bool:
    return (
        match_pss_pattern(event["pv"], PSS_TRIGGER_CHANNEL["pv_suffix"], prefix=prefix)
        and event.get("value") == PSS_TRIGGER_CHANNEL["event_value"]
    )


def _normalize_event(event: dict[str, Any] | None, *, prefix: str) -> dict[str, Any]:
    if event is None:
        raise ValueError("PSS event cannot be None.")
    pv = str(event.get("pv") or event.get("name") or "").strip()
    if not pv:
        raise ValueError("PSS event requires pv.")
    if ":" in pv and not pv.startswith(prefix):
        normalized_pv = pv if "PSS:" in pv else full_pss_pv(pv, prefix=prefix)
    else:
        normalized_pv = pv if pv.startswith(prefix) else full_pss_pv(pv, prefix=prefix)
    time = str(event.get("time") or event.get("timestamp") or "").strip()
    if not time:
        raise ValueError("PSS event requires time or timestamp.")
    return {
        **event,
        "pv": normalized_pv,
        "value": _normalize_value(event.get("value")),
        "time": parse_time_arg(time),
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


def _is_in_window(
    event: dict[str, Any],
    *,
    center: datetime,
    seconds_before: int,
    seconds_after: int,
) -> bool:
    event_time = _event_time(event)
    return center.timestamp() - seconds_before <= event_time.timestamp() <= center.timestamp() + seconds_after


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


def _build_summary(trigger: dict[str, Any], primary: dict[str, Any] | None) -> str:
    if primary is None:
        return (
            f"{trigger['time']} 检测到 PSS 紧急解锁，"
            "但在上下文事件中未发现明确的急停、剂量、门或 PLC/IO 异常记录。"
        )
    return (
        f"{trigger['time']} 检测到 PSS 紧急解锁，"
        f"最可能原因是 {primary['description']} 相关 PV 为 {primary['pv']}。"
    )

from __future__ import annotations

import os
from fnmatch import fnmatchcase
from typing import Any


DEFAULT_PSS_PREFIX = "HALF-BTP:PSS:"

PSS_TRIGGER_CHANNEL: dict[str, Any] = {
    "key": "emergency_unlocked_status",
    "pv_suffix": "sysStatus_Eunlocked:bi",
    "diagnostic_role": "trigger",
    "description": "PSS 紧急解锁状态；value=1 表示发生 EmergencyUnlocked 紧急解锁事件。",
    "event_value": 1,
}

PSS_CAUSE_RULES: list[dict[str, Any]] = [
    {
        "cause_type": "pss_emergency_stop",
        "pattern": "emergencyStopButton_*:bi",
        "event_value": 0,
        "priority": 1,
        "base_confidence": 0.95,
        "subsystem": "emergency_stop",
        "description": "急停按钮动作，可能触发 PSS 紧急解锁。",
    },
    {
        "cause_type": "pss_plc_io_fault",
        "pattern": "PLCstatus:bi",
        "event_value": 0,
        "priority": 2,
        "base_confidence": 0.85,
        "subsystem": "plc_io",
        "description": "PLC 状态异常，可能导致 PSS 进入失效安全状态。",
    },
    {
        "cause_type": "pss_plc_io_fault",
        "pattern": "IOstationStatus_*:bi",
        "event_value": 0,
        "priority": 2,
        "base_confidence": 0.85,
        "subsystem": "plc_io",
        "description": "IO 子站状态异常，可能导致 PSS 进入失效安全状态。",
    },
    {
        "cause_type": "pss_gamma_overlimit",
        "pattern": "gammaOverlimit_*:bi",
        "event_value": 1,
        "priority": 3,
        "base_confidence": 0.85,
        "subsystem": "dose",
        "description": "Gamma 剂量超限，可能触发 PSS 紧急解锁。",
    },
    {
        "cause_type": "pss_neutron_overlimit",
        "pattern": "neutrOverlimit_*:bi",
        "event_value": 1,
        "priority": 3,
        "base_confidence": 0.85,
        "subsystem": "dose",
        "description": "Neutron 剂量超限，可能触发 PSS 紧急解锁。",
    },
    {
        "cause_type": "pss_door_open_or_fault",
        "pattern": "doorStatus_*:bi",
        "event_value": 0,
        "priority": 4,
        "base_confidence": 0.80,
        "subsystem": "door",
        "description": "门状态打开，可能导致 PSS 联锁条件失效。",
    },
    {
        "cause_type": "pss_door_open_or_fault",
        "pattern": "doorFault_*:bi",
        "event_value": 0,
        "priority": 4,
        "base_confidence": 0.80,
        "subsystem": "door",
        "description": "门状态故障，可能导致 PSS 联锁条件失效。",
    },
    {
        "cause_type": "pss_emergency_unlock_command",
        "pattern": "sysStatus_Eunlocked:bo",
        "event_value": 1,
        "priority": 5,
        "base_confidence": 0.90,
        "subsystem": "operator_command",
        "description": "上位紧急解锁命令记录；其可靠性取决于写入历史是否被归档。",
    },
]

PSS_COMPANION_RULES: list[dict[str, Any]] = [
    {
        "cause_type": "pss_cardbox_not_ready",
        "pattern": "CardboxOutput:bi",
        "event_value": 0,
        "priority": 6,
        "base_confidence": 0.55,
        "subsystem": "access_control",
        "description": "门禁卡箱链路未满足，作为伴随异常而非默认主因。",
    },
    {
        "cause_type": "pss_check_button_released",
        "pattern": "checkButton_*:bi",
        "event_value": 0,
        "priority": 7,
        "base_confidence": 0.50,
        "subsystem": "search_check",
        "description": "检查/登记按钮状态释放，作为伴随异常而非默认主因。",
    },
    {
        "cause_type": "pss_searching_button_released",
        "pattern": "searchingButton_*:bi",
        "event_value": 0,
        "priority": 7,
        "base_confidence": 0.50,
        "subsystem": "search_check",
        "description": "搜索/巡查按钮状态释放，作为伴随异常而非默认主因。",
    },
]


def pss_prefix() -> str:
    return os.getenv("PSS_PV_PREFIX", DEFAULT_PSS_PREFIX)


def full_pss_pv(suffix: str, *, prefix: str | None = None) -> str:
    prefix = prefix if prefix is not None else pss_prefix()
    return f"{prefix}{suffix}"


def pss_suffix(pv: str, *, prefix: str | None = None) -> str:
    prefix = prefix if prefix is not None else pss_prefix()
    if pv.startswith(prefix):
        return pv[len(prefix) :]
    for marker in ("PSS:", "PSS-"):
        if marker in pv:
            return pv.split(marker, 1)[1]
    return pv


def match_pss_pattern(pv: str, pattern: str, *, prefix: str | None = None) -> bool:
    return fnmatchcase(pss_suffix(pv, prefix=prefix), pattern)

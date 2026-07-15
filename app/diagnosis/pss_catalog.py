from __future__ import annotations

import os
from fnmatch import fnmatchcase
from typing import Any


DEFAULT_PSS_PREFIX = "STCF-BTP:PSS:"

PSS_STATE_PVS: dict[str, str] = {
    "interlocked": "sysStatus_interlocked:bi",
    "unlocked": "sysStatus_unlocked:bi",
    "searching": "sysStatus_searching:bi",
    "emergency_unlocked": "sysStatus_Eunlocked:bi",
}

PSS_RESULT_PVS: dict[str, str] = {
    "acc_interlock": "interlockOutputAcc:bi",
    "door_button_cardbox_interlock": "interlockOutputDorBtnCrdbox:bi",
}

PSS_COMMAND_RULES: list[dict[str, Any]] = [
    {
        "cause_type": "manual_unlock",
        "pattern": "Order_Unlock_Button",
        "normal": 0,
        "abnormal": 1,
        "priority": 1,
        "base_confidence": 0.95,
        "subsystem": "operator_command",
        "description": "人工普通解锁命令触发。",
    },
    {
        "cause_type": "manual_emergency_unlock",
        "pattern": "Order_EmergencyUnlock_Button",
        "normal": 0,
        "abnormal": 1,
        "priority": 1,
        "base_confidence": 0.95,
        "subsystem": "operator_command",
        "description": "人工紧急解锁命令触发。",
    },
]

PSS_REASON_RULES: list[dict[str, Any]] = [
    {
        "cause_type": "emergency_stop",
        "pattern": "emergencyStopButton_*:bi",
        "normal": 1,
        "abnormal": 0,
        "priority": 2,
        "base_confidence": 0.90,
        "subsystem": "emergency_stop",
        "description": "急停按钮触发导致 PSS 联锁中断。",
    },
    {
        "cause_type": "radiation_overlimit",
        "pattern": "gammaOverlimit_*:bi",
        "normal": 0,
        "abnormal": 1,
        "priority": 3,
        "base_confidence": 0.88,
        "subsystem": "radiation",
        "description": "Gamma 剂量超标导致 PSS 联锁中断。",
    },
    {
        "cause_type": "radiation_overlimit",
        "pattern": "neutrOverlimit_*:bi",
        "normal": 0,
        "abnormal": 1,
        "priority": 3,
        "base_confidence": 0.88,
        "subsystem": "radiation",
        "description": "Neutron 剂量超标导致 PSS 联锁中断。",
    },
    {
        "cause_type": "door_open",
        "pattern": "doorStatus_*:bi",
        "normal": 1,
        "abnormal": 0,
        "priority": 4,
        "base_confidence": 0.85,
        "subsystem": "door",
        "description": "运行中门打开导致 PSS 联锁中断。",
    },
    {
        "cause_type": "door_fault",
        "pattern": "doorFault_*:bi",
        "normal": 1,
        "abnormal": 0,
        "priority": 4,
        "base_confidence": 0.85,
        "subsystem": "door",
        "description": "门状态故障导致 PSS 联锁中断。",
    },
    {
        "cause_type": "cardbox_not_ready",
        "pattern": "CardboxOutput:bi",
        "normal": 1,
        "abnormal": 0,
        "priority": 5,
        "base_confidence": 0.82,
        "subsystem": "access_control",
        "description": "卡盒状态异常或门禁卡未全部归位导致 PSS 联锁中断。",
    },
    {
        "cause_type": "plc_io_fault",
        "pattern": "PLCstatus:bi",
        "normal": 1,
        "abnormal": 0,
        "priority": 6,
        "base_confidence": 0.86,
        "subsystem": "communication",
        "description": "PLC 状态异常导致 PSS 联锁中断。",
    },
    {
        "cause_type": "plc_io_fault",
        "pattern": "IOstationStatus_*:bi",
        "normal": 1,
        "abnormal": 0,
        "priority": 6,
        "base_confidence": 0.86,
        "subsystem": "communication",
        "description": "IO 子站状态异常导致 PSS 联锁中断。",
    },
]

PSS_AUXILIARY_RULES: list[dict[str, Any]] = [
    {
        "cause_type": "emergency_unlocked_status",
        "pattern": "sysStatus_Eunlocked:bi",
        "normal": 0,
        "abnormal": 1,
        "priority": 20,
        "base_confidence": 0.50,
        "subsystem": "state_result",
        "description": "本次事件伴随紧急解锁状态置位，但该 PV 不是原因证据。",
    },
    {
        "cause_type": "acc_interlock_output_lost",
        "pattern": "interlockOutputAcc:bi",
        "normal": 1,
        "abnormal": 0,
        "priority": 21,
        "base_confidence": 0.50,
        "subsystem": "state_result",
        "description": "加速器联锁输出掉线，作为结果/伴随状态记录。",
    },
    {
        "cause_type": "door_button_cardbox_interlock_output_lost",
        "pattern": "interlockOutputDorBtnCrdbox:bi",
        "normal": 1,
        "abnormal": 0,
        "priority": 21,
        "base_confidence": 0.50,
        "subsystem": "state_result",
        "description": "门/按钮/卡盒联锁输出掉线，作为结果/伴随状态记录。",
    },
]


def pss_prefix() -> str:
    return _normalize_prefix(os.getenv("PSS_PV_PREFIX", DEFAULT_PSS_PREFIX))


def full_pss_pv(suffix: str, *, prefix: str | None = None) -> str:
    prefix = _normalize_prefix(prefix if prefix is not None else pss_prefix())
    suffix = suffix.lstrip(":")
    return f"{prefix}{suffix}"


def pss_suffix(pv: str, *, prefix: str | None = None) -> str:
    prefix = _normalize_prefix(prefix if prefix is not None else pss_prefix())
    if pv.startswith(prefix):
        return pv[len(prefix) :]
    for marker in ("PSS:", "PSS-"):
        if marker in pv:
            return pv.split(marker, 1)[1]
    return pv


def match_pss_pattern(pv: str, pattern: str, *, prefix: str | None = None) -> bool:
    return fnmatchcase(pss_suffix(pv, prefix=prefix), pattern)


def pss_state_pv_names(*, prefix: str | None = None) -> list[str]:
    return [full_pss_pv(suffix, prefix=prefix) for suffix in PSS_STATE_PVS.values()]


def pss_auxiliary_pv_names(*, prefix: str | None = None) -> list[str]:
    return [full_pss_pv(suffix, prefix=prefix) for suffix in PSS_RESULT_PVS.values()]


def pss_reason_pv_names(*, prefix: str | None = None) -> list[str]:
    patterns = [rule["pattern"] for rule in PSS_COMMAND_RULES + PSS_REASON_RULES]
    names: list[str] = []
    for pattern in patterns:
        names.extend(_expand_known_pattern(pattern, prefix=prefix))
    return names


def pss_all_diagnosis_pv_names(*, prefix: str | None = None) -> list[str]:
    names = pss_state_pv_names(prefix=prefix) + pss_auxiliary_pv_names(prefix=prefix)
    names.extend(pss_reason_pv_names(prefix=prefix))
    return sorted(set(names))


def _expand_known_pattern(pattern: str, *, prefix: str | None) -> list[str]:
    if "*" not in pattern:
        return [full_pss_pv(pattern, prefix=prefix)]
    if pattern == "emergencyStopButton_*:bi":
        return [full_pss_pv(f"emergencyStopButton_{index}:bi", prefix=prefix) for index in range(1, 11)]
    if pattern == "gammaOverlimit_*:bi":
        return [full_pss_pv(f"gammaOverlimit_{index}:bi", prefix=prefix) for index in range(1, 5)]
    if pattern == "neutrOverlimit_*:bi":
        return [full_pss_pv(f"neutrOverlimit_{index}:bi", prefix=prefix) for index in range(1, 5)]
    if pattern == "doorStatus_*:bi":
        return [full_pss_pv(f"doorStatus_{index}:bi", prefix=prefix) for index in range(1, 7)]
    if pattern == "doorFault_*:bi":
        return [full_pss_pv(f"doorFault_{index}:bi", prefix=prefix) for index in range(1, 4)]
    if pattern == "IOstationStatus_*:bi":
        return [full_pss_pv(f"IOstationStatus_{index}:bi", prefix=prefix) for index in range(1, 6)]
    return []


def _normalize_prefix(prefix: str) -> str:
    prefix = prefix.strip().replace("：", ":")
    return prefix if prefix.endswith(":") else f"{prefix}:"

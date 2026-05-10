from __future__ import annotations

from typing import Any

from app.skills.common import SkillContext, SkillResult


class QuadrupolePowerSkill:
    """Find quadrupole power candidates around a beam fault time.

    Parameters:
        fault_time: Center time for power fault search. Can be inferred from state.
        power_pattern: Power PV pattern.
        pv_pattern: Backward-compatible alias for power_pattern.
        window_seconds: Search window in seconds.

    Returns:
        SkillResult with power fault evidence and candidate causes from the tool.
    """

    def run(self, context: SkillContext, arguments: dict[str, Any]) -> SkillResult:
        fault_time = arguments.get("fault_time") or _infer_fault_time(context.state)
        if not fault_time:
            return SkillResult(
                ok=False,
                summary="缺少束流故障时间，无法定位四极铁电源异常。",
                evidence=[],
                candidate_causes=[],
                output={
                    "required_next_step": (
                        "先调用 beam_state_diagnosis 或 diagnose_beam_fault 获取故障时间。"
                    )
                },
                error="missing_fault_time",
            )

        tool_arguments: dict[str, Any] = {"fault_time": fault_time}
        window_seconds = arguments.get("window_seconds")
        if window_seconds is not None:
            tool_arguments["window_seconds"] = window_seconds

        power_pattern = arguments.get("power_pattern") or arguments.get("pv_pattern")
        if power_pattern:
            tool_arguments["power_pattern"] = power_pattern

        result = context.tools.call("diagnose_power_faults", tool_arguments)
        if not result.ok:
            return SkillResult(
                ok=False,
                summary=result.summary,
                evidence=[],
                candidate_causes=[],
                output={},
                error=result.error,
            )

        output = result.output if isinstance(result.output, dict) else {}
        evidence = [
            {
                "type": "quadrupole_power_fault_diagnosis",
                "fault_time": fault_time,
                "power_pattern": power_pattern,
                "summary": result.summary,
                "features": output,
            }
        ]

        candidate_causes = _extract_candidate_causes(output)
        return SkillResult(
            ok=True,
            summary=result.summary,
            evidence=evidence,
            candidate_causes=candidate_causes,
            output={
                "tool": "diagnose_power_faults",
                "tool_arguments": tool_arguments,
                "tool_output": output,
            },
        )


def _infer_fault_time(state: dict[str, Any]) -> str | None:
    for collection_name in ("candidate_causes", "evidence", "observations"):
        for item in state.get(collection_name, []) or []:
            found = _find_time_value(item)
            if found:
                return str(found)
    return None


def _find_time_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("fault_time", "drop_time", "trip_time"):
            if value.get(key):
                return value[key]
        for nested in value.values():
            found = _find_time_value(nested)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_time_value(item)
            if found:
                return found
    return None


def _extract_candidate_causes(output: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = output.get("candidate_causes") or output.get("candidates") or []
    if isinstance(candidates, list) and candidates:
        return [item for item in candidates if isinstance(item, dict)]

    power_faults = output.get("power_faults") or []
    if isinstance(power_faults, list):
        extracted = []
        for item in power_faults:
            if not isinstance(item, dict):
                continue
            device = item.get("channel_name") or item.get("device")
            extracted.append(
                {
                    "cause_type": "quadrupole_power_fault",
                    "device": device,
                    "description": item.get("evidence")
                    or f"{device} 在束流故障附近存在电源异常候选。",
                    "confidence": 0.75,
                    "fault_time": item.get("fault_time"),
                    "fault_type": item.get("fault_type"),
                }
            )
        if extracted:
            return extracted

    devices = output.get("candidate_devices") or output.get("faulty_devices") or []
    if not isinstance(devices, list):
        return []

    return [
        {
            "cause_type": "quadrupole_power_fault",
            "device": device,
            "description": f"{device} 在束流故障附近存在电源异常候选。",
            "confidence": 0.7,
        }
        for device in devices
    ]

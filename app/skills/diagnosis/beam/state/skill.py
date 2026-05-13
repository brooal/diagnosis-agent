from __future__ import annotations

from typing import Any

from app.skills.common import SkillContext, SkillResult


class BeamStateDiagnosisSkill:
    def run(self, context: SkillContext, arguments: dict[str, Any]) -> SkillResult:
        start = arguments["start"]
        end = arguments["end"]
        beam_channel = arguments.get("beam_channel") or arguments.get("beam_current_pv")

        tool_arguments: dict[str, Any] = {"start": start, "end": end}
        if beam_channel:
            tool_arguments["beam_channel"] = beam_channel

        result = context.tools.call("diagnose_beam_fault", tool_arguments)
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
        drop_time = _first_present(output, "drop_time", "fault_time", "trip_time")
        drop_detected = bool(
            output.get("drop_detected")
            or output.get("fault_detected")
            or output.get("beam_trip")
            or output.get("fault_present_in_window")
            or output.get("fault_start_in_window")
            or output.get("fault_count", 0) > 0
        )

        phenomena = [
            {
                "type": "beam_trip" if drop_detected else "normal",
                "start": start,
                "end": end,
                "fault_time": drop_time,
                "confidence": 0.85 if drop_detected else 0.7,
            }
        ]
        evidence = [
            {
                "type": "beam_fault_diagnosis",
                "start": start,
                "end": end,
                "beam_channel": beam_channel,
                "summary": result.summary,
                "features": output,
            }
        ]

        candidate_causes: list[dict[str, Any]] = []
        recommended_next_skills: list[dict[str, Any]] = []
        if drop_detected:
            candidate_causes.append(
                {
                    "cause_type": "beam_trip",
                    "description": "束流诊断工具检测到诊断窗口内存在束流掉束特征。",
                    "confidence": 0.8,
                    "drop_time": drop_time,
                }
            )
            recommended_next_skills = [
                {
                    "name": "beam_trip_cause_analysis",
                    "reason": "检测到 beam_trip，需要进入多系统故障排查。",
                },
                {
                    "name": "quadrupole_power_diagnosis",
                    "reason": "当前已接入的电源原因分析 Skill 可继续排查四极铁电源异常。",
                },
            ]

        return SkillResult(
            ok=True,
            summary=result.summary,
            evidence=evidence,
            candidate_causes=candidate_causes,
            output={
                "phenomena": phenomena,
                "recommended_next_skills": recommended_next_skills,
                "tool": "diagnose_beam_fault",
                "tool_arguments": tool_arguments,
                "tool_output": output,
            },
        )


def _first_present(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    faults = data.get("faults")
    if isinstance(faults, list) and faults:
        first_fault = faults[0]
        if isinstance(first_fault, dict):
            return first_fault.get("fault_time") or first_fault.get("drop_time")
    return None

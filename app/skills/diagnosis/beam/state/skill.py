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

        decay_result = context.tools.call("diagnose_topoff_decay", tool_arguments)
        if decay_result.ok:
            decay_output = decay_result.output if isinstance(decay_result.output, dict) else {}
            if _decay_output_has_decision(decay_output):
                return _build_decay_skill_result(
                    result=decay_result,
                    output=decay_output,
                    start=start,
                    end=end,
                    beam_channel=beam_channel,
                    tool_arguments=tool_arguments,
                )

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
                "type": "beam_state_diagnosis",
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


def _decay_output_has_decision(output: dict[str, Any]) -> bool:
    if output.get("event_count", 0) > 0:
        return True
    return output.get("overall_status") in {"beam_decay_like_unknown", "beam_drop"}


def _build_decay_skill_result(
    *,
    result: Any,
    output: dict[str, Any],
    start: str,
    end: str,
    beam_channel: str | None,
    tool_arguments: dict[str, Any],
) -> SkillResult:
    events = output.get("events") if isinstance(output.get("events"), list) else []
    phenomena: list[dict[str, Any]] = []
    candidate_causes: list[dict[str, Any]] = []
    recommended_next_skills: list[dict[str, Any]] = []

    for event in events:
        if not isinstance(event, dict):
            continue
        classification = event.get("classification") or "mode_interrupt_unknown"
        event_id = event.get("event_id")
        fault_time = event.get("interrupt_time") or event.get("known_active_at")
        phenomena.append(
            {
                "type": _phenomenon_type_for_classification(classification),
                "classification": classification,
                "event_id": event_id,
                "start": start,
                "end": end,
                "fault_time": fault_time,
                "confidence": _confidence_number(event.get("confidence")),
            }
        )
        root_candidates = event.get("root_cause_candidates") or []
        if root_candidates:
            primary = root_candidates[0]
            candidate_causes.append(
                {
                    "cause_type": _cause_type_for_candidate(primary),
                    "description": primary.get("description"),
                    "confidence": _confidence_number(event.get("confidence")),
                    "event_id": event_id,
                    "fault_time": fault_time,
                    "pv": primary.get("pv"),
                    "channel_id": primary.get("channel_id"),
                    "value": primary.get("value"),
                    "meaning": primary.get("meaning"),
                    "subsystem": primary.get("subsystem"),
                    "time": primary.get("time"),
                }
            )

        if classification in {"topoff_decay", "topoff_interrupt_with_beam_drop"}:
            recommended_next_skills.append(
                {
                    "name": "decay_cause_analysis",
                    "event_id": event_id,
                    "reason": f"{event_id} 检测到 {classification}，需要解释恒流中断/decay 原因。",
                }
            )
        elif classification == "beam_drop_related_mode_interrupt":
            recommended_next_skills.append(
                {
                    "name": "quadrupole_power_diagnosis",
                    "event_id": event_id,
                    "reason": f"{event_id} 存在 MODE=0 且束流表现为掉束，需要检查四极铁电源。",
                }
            )

    if not events and output.get("overall_status") in {"beam_decay_like_unknown", "beam_drop"}:
        status = output["overall_status"]
        phenomena.append(
            {
                "type": "beam_decay_like" if status == "beam_decay_like_unknown" else "beam_trip",
                "classification": status,
                "event_id": None,
                "start": start,
                "end": end,
                "fault_time": None,
                "confidence": 0.55,
            }
        )
        if status == "beam_drop":
            candidate_causes.append(
                {
                    "cause_type": "beam_trip",
                    "description": "未找到 MODE=0 恒流中断事件，但束流曲线存在掉束特征。",
                    "confidence": 0.65,
                    "drop_time": None,
                }
            )
            recommended_next_skills.append(
                {
                    "name": "quadrupole_power_diagnosis",
                    "reason": "束流曲线存在掉束特征，需要检查四极铁电源。",
                }
            )

    evidence = [
        {
            "type": "beam_state_diagnosis",
            "start": start,
            "end": end,
            "beam_channel": beam_channel,
            "summary": result.summary,
            "features": output,
        }
    ]
    return SkillResult(
        ok=True,
        summary=result.summary,
        evidence=evidence,
        candidate_causes=candidate_causes,
        output={
            "phenomena": phenomena,
            "recommended_next_skills": recommended_next_skills,
            "tool": "diagnose_topoff_decay",
            "tool_arguments": tool_arguments,
            "tool_output": output,
        },
    )


def _phenomenon_type_for_classification(classification: str) -> str:
    if classification in {"topoff_decay", "mode_interrupt_unknown"}:
        return "topoff_decay"
    if classification in {"topoff_interrupt_with_beam_drop", "beam_drop_related_mode_interrupt"}:
        return "beam_trip"
    return "uncertain"


def _cause_type_for_candidate(candidate: dict[str, Any]) -> str:
    subsystem = str(candidate.get("subsystem") or "topoff").lower()
    return f"topoff_{subsystem}_error"


def _confidence_number(value: Any) -> float:
    if value == "high":
        return 0.9
    if value == "medium":
        return 0.75
    if value == "low":
        return 0.55
    if isinstance(value, int | float):
        return float(value)
    return 0.65


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

from __future__ import annotations

from typing import Any

from app.skills.common import SkillContext, SkillResult


class DecayCauseAnalysisSkill:
    def run(self, context: SkillContext, arguments: dict[str, Any]) -> SkillResult:
        event_id = arguments.get("event_id")
        event = _find_decay_event(context.state, event_id=event_id)
        if event is None:
            return SkillResult(
                ok=False,
                summary="未找到可用于 decay 原因分析的 beam_state_diagnosis 事件证据。",
                evidence=[],
                candidate_causes=[],
                output={"required_next_step": "先调用 beam_state_diagnosis。"},
                error="missing_decay_event",
            )

        root_candidates = event.get("root_cause_candidates") or []
        primary = root_candidates[0] if root_candidates else None
        if primary:
            summary = (
                f"{event.get('event_id')} 的主要候选原因为 "
                f"{primary.get('pv')}={primary.get('value')} ({primary.get('meaning')})，"
                f"分类为 {event.get('classification')}。"
            )
            candidate_causes = [
                {
                    "cause_type": _cause_type(primary),
                    "event_id": event.get("event_id"),
                    "classification": event.get("classification"),
                    "confidence": event.get("confidence"),
                    "pv": primary.get("pv"),
                    "channel_id": primary.get("channel_id"),
                    "value": primary.get("value"),
                    "meaning": primary.get("meaning"),
                    "subsystem": primary.get("subsystem"),
                    "time": primary.get("time"),
                    "description": primary.get("description"),
                }
            ]
        else:
            summary = (
                f"{event.get('event_id')} 检测到 {event.get('classification')}，"
                "但未匹配到 TOPOFF/温度根因报警。"
            )
            candidate_causes = []

        evidence = [
            {
                "type": "decay_cause_analysis",
                "event_id": event.get("event_id"),
                "classification": event.get("classification"),
                "root_cause_candidates": root_candidates,
                "beam_curve_summary": event.get("beam_curve_summary"),
            }
        ]
        return SkillResult(
            ok=True,
            summary=summary,
            evidence=evidence,
            candidate_causes=candidate_causes,
            output={
                "event_id": event.get("event_id"),
                "classification": event.get("classification"),
                "primary_cause": primary,
                "secondary_causes": root_candidates[1:],
                "recommended_actions": _recommended_actions(primary),
            },
        )


def _find_decay_event(
    state: dict[str, Any],
    *,
    event_id: str | None,
) -> dict[str, Any] | None:
    for evidence in reversed(state.get("evidence", [])):
        if evidence.get("type") != "beam_state_diagnosis":
            continue
        features = evidence.get("features") or {}
        events = features.get("events") or []
        for event in events:
            if not isinstance(event, dict):
                continue
            if event_id and event.get("event_id") != event_id:
                continue
            if event.get("classification") in {
                "topoff_decay",
                "topoff_interrupt_with_beam_drop",
                "mode_interrupt_unknown",
                "beam_drop_related_mode_interrupt",
            }:
                return event
    return None


def _cause_type(candidate: dict[str, Any]) -> str:
    subsystem = str(candidate.get("subsystem") or "topoff").lower()
    return f"topoff_{subsystem}_error"


def _recommended_actions(primary: dict[str, Any] | None) -> list[str]:
    if not primary:
        return ["检查 MODE=0 附近是否存在缺失的 TOPOFF/温度状态 PV 记录。"]
    subsystem = primary.get("subsystem") or "相关子系统"
    pv = primary.get("pv") or "报警 PV"
    meaning = primary.get("meaning") or "异常状态"
    return [
        f"检查 {subsystem} 子系统，重点核对 {pv} 的 {meaning} 状态。",
        "核对报警恢复时间与 MODE=1 恒流恢复时间是否一致。",
    ]

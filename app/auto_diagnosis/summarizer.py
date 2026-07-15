from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.auto_diagnosis.schemas import BeamFaultEvent
from app.llm.client import LLMClient
from app.utils.json import make_json_safe


@dataclass(frozen=True)
class SummaryResult:
    text: str
    token_usage: dict[str, Any] | None = None


class BeamAutoSummarizer:
    def __init__(self, llm: LLMClient | None = None, *, enable_llm: bool = True):
        self.llm = llm or LLMClient()
        self.enable_llm = enable_llm

    def summarize_new_incident(
        self,
        *,
        event: BeamFaultEvent,
        schedule: dict,
        detect_window: dict,
    ) -> str:
        return self.summarize_new_incident_with_usage(
            event=event,
            schedule=schedule,
            detect_window=detect_window,
        ).text

    def summarize_new_incident_with_usage(
        self,
        *,
        event: BeamFaultEvent,
        schedule: dict,
        detect_window: dict,
    ) -> SummaryResult:
        if not self.enable_llm:
            return SummaryResult(
                text=fallback_summary(event=event, schedule=schedule, detect_window=detect_window),
                token_usage=None,
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "你是加速器束流自动诊断报告生成器。"
                    "只根据输入的结构化诊断结果生成简洁中文邮件正文。"
                    "不要编造未提供的证据。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    make_json_safe(
                        {
                            "schedule": schedule,
                            "detect_window": detect_window,
                            "event": event,
                            "output_format": "Markdown email body in Chinese",
                        }
                    ),
                    ensure_ascii=False,
                ),
            },
        ]
        try:
            completion = self.llm.complete_with_usage(messages, temperature=0.2)
            return SummaryResult(text=completion.content, token_usage=completion.usage)
        except Exception:
            return SummaryResult(
                text=fallback_summary(event=event, schedule=schedule, detect_window=detect_window),
                token_usage=None,
            )

    def summarize_manual_diagnosis(
        self,
        *,
        diagnosis: dict,
        fallback: str,
    ) -> str:
        return self.summarize_manual_diagnosis_with_usage(
            diagnosis=diagnosis,
            fallback=fallback,
        ).text

    def summarize_manual_diagnosis_with_usage(
        self,
        *,
        diagnosis: dict,
        fallback: str,
    ) -> SummaryResult:
        if not self.enable_llm:
            return SummaryResult(text=fallback, token_usage=None)

        compact = _compact_manual_payload(diagnosis)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是加速器束流手动诊断报告生成器。"
                    "只根据输入的结构化诊断证据生成中文 Markdown 结论。"
                    "不要编造未提供的原因。"
                    "如果是 drop，重点说明掉束现象和已接入的原因诊断结果；"
                    "如果是 decay，重点说明 MODE/报警 PV 证据；"
                    "如果正常，简洁说明未发现明确 drop 或 decay。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    make_json_safe(
                        {
                            "diagnosis": compact,
                            "output_format": "Markdown report in Chinese",
                        }
                    ),
                    ensure_ascii=False,
                ),
            },
        ]
        try:
            completion = self.llm.complete_with_usage(messages, temperature=0.2)
            return SummaryResult(text=completion.content, token_usage=completion.usage)
        except Exception:
            return SummaryResult(text=fallback, token_usage=None)


def fallback_summary(
    *,
    event: BeamFaultEvent,
    schedule: dict,
    detect_window: dict,
) -> str:
    cause = event.primary_cause or {}
    cause_line = (
        f"- 候选原因：{cause.get('pv')}={cause.get('value')} ({cause.get('meaning')})"
        if cause
        else "- 候选原因：当前未匹配到明确报警 PV"
    )
    return "\n".join(
        [
            "## 束流自动诊断告警",
            f"- 供光计划：{schedule.get('status')} / {schedule.get('status_cn')}",
            f"- 检测窗口：{detect_window.get('start')} 至 {detect_window.get('end')}",
            f"- 事件分类：{event.classification}",
            f"- 严重程度：{event.severity}",
            f"- 事件时间：{event.event_time}",
            f"- 摘要：{event.summary}",
            cause_line,
        ]
    )


def _compact_manual_payload(diagnosis: dict) -> dict:
    evidence = diagnosis.get("evidence") or {}
    beam = evidence.get("beam") or {}
    alarms = evidence.get("alarms") or {}
    mode = evidence.get("mode") or {}
    quadrupole = evidence.get("quadrupole_power") or {}
    return {
        "time_window": diagnosis.get("time_window"),
        "diagnosis_status": diagnosis.get("diagnosis_status"),
        "summary": diagnosis.get("summary"),
        "event": diagnosis.get("event"),
        "beam": {
            "sample_count": beam.get("sample_count"),
            "min": beam.get("min"),
            "max": beam.get("max"),
            "median": beam.get("median"),
            "first": beam.get("first"),
            "last": beam.get("last"),
            "drop_ratio": beam.get("drop_ratio"),
            "normal_range": beam.get("normal_range"),
            "has_low_points": beam.get("has_low_points"),
        },
        "mode": {
            "has_zero": mode.get("has_zero"),
            "transitions": mode.get("transitions"),
            "zero_times": mode.get("zero_times"),
        },
        "active_alarms": alarms.get("active_alarms"),
        "quadrupole_power": {
            "status": quadrupole.get("status"),
            "power_fault_count": quadrupole.get("power_fault_count"),
            "power_faults": quadrupole.get("power_faults"),
            "message": quadrupole.get("message"),
        },
    }

# app/skills/quadrupole_power_skill.py

from __future__ import annotations

from typing import Any

from app.agent.state import DiagnosisState
from app.skills.base import SkillResult
from app.tools.registry import ToolRegistry


class QuadrupolePowerSkill:
    name = "quadrupole_power_diagnosis"

    description = (
        "分析指定时间段内所有四级铁相关电源状态，寻找电流跌落、状态异常、"
        "开关机异常或与束流故障时间相关的候选电源。"
    )

    parameters = {
        "type": "object",
        "properties": {
            "start": {"type": "string"},
            "end": {"type": "string"},
            "pv_pattern": {
                "type": "string",
                "description": "四级铁电源 PV 通配符或分组名",
            },
        },
        "required": ["start", "end", "pv_pattern"],
    }

    def run(
        self,
        state: DiagnosisState,
        arguments: dict[str, Any],
        tools: ToolRegistry,
    ) -> SkillResult:
        start = arguments["start"]
        end = arguments["end"]
        pv_pattern = arguments["pv_pattern"]

        # 第一版先写死几个 PV，后续替换为从配置表查询
        quadrupole_pvs = [
            "QF01:PS:CURRENT",
            "QF02:PS:CURRENT",
            "QF03:PS:CURRENT",
        ]

        evidence: list[dict[str, Any]] = []
        candidate_causes: list[dict[str, Any]] = []

        for pv in quadrupole_pvs:
            result = tools.call(
                "query_pv_range",
                {
                    "pv_name": pv,
                    "start": start,
                    "end": end,
                },
            )

            if not result.ok:
                evidence.append(
                    {
                        "type": "query_failed",
                        "pv": pv,
                        "summary": f"查询 {pv} 失败：{result.error}",
                    }
                )
                continue

            data = result.output

            evidence.append(
                {
                    "type": "quadrupole_power_range",
                    "pv": pv,
                    "start": start,
                    "end": end,
                    "summary": result.summary,
                    "features": data,
                }
            )

            if data.get("drop_detected"):
                candidate_causes.append(
                    {
                        "cause_type": "quadrupole_power_drop",
                        "device": pv,
                        "description": f"{pv} 在诊断窗口内出现电流跌落。",
                        "confidence": 0.75,
                        "drop_time": data.get("drop_time"),
                    }
                )

        if candidate_causes:
            summary = f"发现 {len(candidate_causes)} 个四级铁电源异常候选。"
        else:
            summary = "未发现明显四级铁电源异常。"

        return SkillResult(
            ok=True,
            summary=summary,
            evidence=evidence,
            candidate_causes=candidate_causes,
            output={
                "checked_pvs": quadrupole_pvs,
                "candidate_count": len(candidate_causes),
            },
        )
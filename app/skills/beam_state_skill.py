from __future__ import annotations

from typing import Any
from app.agent.state import DiagnosisState
from app.skills.base import SkillResult
from app.tools.registry import ToolRegistry

class BeamStateSkill:
    name = "beam_state_diagnosis"

    description = (
        "检测某个时间段内的束流状态，判断是否存在掉束、束流衰减decay、"
        "明显波动或者基本正常。"
    )

    parameters = {
        "type" : "object",
        "properties" : {
            "beam_current_pv" : {
                "type" : "string",
                "description" : "束流流强PV名称",
            },
            "start" :{
                "type" : "string",
                "description" : "诊断开始时间",
            },
            "end" : {
                "type" : "string",
                "description" : "诊断结束时间",
            },
        },
        "required" : ["beam_current_pv", "start", "end"],
    }

    def run(
            self,
            state : DiagnosisState,
            arguments : dict[str, Any],
            tools : ToolRegistry,
    ) -> SkillResult:
        pv = arguments["beam_current_pv"]
        start = arguments["start"]
        end = arguments["end"]
        result = tools.call(
            "query_pv_range",
            {
                "pv_name" : pv,
                "start" : start,
                "end" : end,
            }
        )
        if not result.ok:
            return SkillResult(
                ok = False,
                summary= "束流状态检测失败",
                evidence = [],
                candidate_causes = [],
                output = {},
                error = result.error,
            )

        data = result.output

        evidence = [
            {
                "type" : "beam_current_range",
                "pv" : pv,
                "start" : start,
                "end" : end,
                "summary" : result.summary,
                "features" : data,
            }
        ]
        candidate_causes : list[dict[str, Any]] = []

        if data.get("drop_detected"):
            beam_state = "beam_trip"
            summary = f"检测到束流掉束，掉束时间约为{data.get('drop_time')}"
            candidate_causes.append(
                {
                    "cause_type" : "beam_trip",
                    "description" : "束流流强在诊断窗口内快速跌落，如何掉束特征",
                    "confidence" : 0.8,
                    "evidence_index" : [0]
                }
            )
        else:
            beam_state = "normal"
            summary = "未检测到明显掉束，束流状态基本正常"

        return SkillResult(
            ok = True,
            summary = summary,
            evidence = evidence,
            candidate_causes = candidate_causes,
            output = {
                "beam_state" : beam_state,
                "beam_current_pv" : pv,
                "start" : start,
                "end" : end,
            },
        )


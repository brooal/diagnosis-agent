
from __future__ import annotations

from curses import panel
from typing import Any
import json

from app.agent.state import DiagnosisState
from app.skills.registry import SkillRegistry
from app.tools.registry import ToolRegistry
from app.tracing.recorder import TraceRecorder

#初始节点，创建trace_id,追加jsonl，更新诊断状态
def initialize_node(
        state : DiagnosisState,
        recorder : TraceRecorder
) -> DiagnosisState:

    case_id = state["case_id"]
    trace_id = recorder.create_trace_id(case_id)

    new_state: DiagnosisState = {
        **state,
        "trace_id" : trace_id,
        "step" : 0,
        "max_steps" : state.get("max_steps", 8),
        "tool_history" : [],
        "skill_history" : [],
        "evidence" : [],
        "candidate_causes" : [],
        "done" : False,
        "status" : "running"
    }

    recorder.append(
        trace_id = trace_id,
        case_id = case_id,
        event_type= "case_started",
        payload = {
            "trigger_source" : new_state.get("trigger_source"),
            "user_query" : new_state.get("user_query"),
            "time_window" : new_state.get("time_window"),
            "scope": new_state.get("scope"),
        },
    )
    return new_state


#计划节点，直接做规则路由后续再修改
def plan_node(
        state : DiagnosisState,
        recorder : TraceRecorder
) -> DiagnosisState:

    user_query = state["user_query"] or ""
    time_window = state["time_window"] or {}
    scope = state.get("scope") or {}

    plan: list[dict[str, Any]] = []

    if any(k in user_query for k in ["束流","掉束","decay","衰减"]):
        plan.append(
            {
                "type":"skill",
                "name" : "beam_state_diagnosis",
                "arguments" : {
                    "beam_current_pv" : scope.get(
                        "beam_current_pv",
                        "RING:BEAM:CURRENT"
                    ),
                    "start" : time_window.get("start"),
                    "end" : time_window.get("end"),
                },
                "reason" : "用户问题涉及束流的状态，先判断是否存在掉束或者衰减"
            }
        )
    if any(k in user_query for k in ["四级铁","电源","quadrupole"]):
        plan.append(
            {
                "type" : "skill",
                "name" : "quadrupole_power_diagnosis",
                "arguments" : {
                    "start" : time_window.get("start"),
                    "end" : time_window.get("end"),
                    "pv_pattern" : scope.get("quadrupole_pattern", "Q*:PS:*"),
                },
                "reason": "用户问题涉及到四级铁电源，分析相关的电源状态。"
            }
        )
    if not plan:
        plan.append({
            "type" : "tool",
            "name" : "test_db_connection",
            "arguments" : {},
            "reason" : "没有明确的诊断意图，先检查数据库连接是否正常"
        })

    new_state: DiagnosisState = {
        **state,
        "plan" : plan,
    }

    recorder.append(
        trace_id=state["trace_id"],
        case_id=state["case_id"],
        event_type="plan_created",
        payload={"plan" : plan}

    )
    return new_state

#执行节点，执行plan中的当前步骤
def act_node(
        state : DiagnosisState,
        recorder : TraceRecorder,
        tools: ToolRegistry,
        skills: SkillRegistry
) -> DiagnosisState:
    step = state.get("step", 0)
    plan = state.get("plan", [])

    if step >= len(plan):
        return {
            **state,
            "done" : True,
        }

    action = plan[step]
    action_type = action["type"]
    name = action["name"]
    arguments = action.get("arguments", {})
    reason = action.get("reason", "")

    trace_id = state["trace_id"]
    case_id = state["case_id"]

    if action_type == "tool":
        result = tools.call(name, arguments)

        record = {
            "step" : step,
            "name" : name,
            "arguments" : arguments,
            "ok" : result.ok,
            "summary" : result.summary,
            "output": result.output,
            "error" : result.error,
            "reason" : reason,
        }

        tool_history = state.get("tool_history", []) + [record]

        recorder.append(
            trace_id = trace_id,
            case_id = case_id,
            event_type="tool_called",
            payload = record,
        )
        return {
            **state,
            "step" : step +1,
            "tool_history" : tool_history,
        }
    if action_type == "skill":
        result = skills.call(
            name=name,
            arguments=arguments,
            state=state,
            tools=tools,
        )

        record = {
            "step": step,
            "name": name,
            "arguments": arguments,
            "ok": result.ok,
            "summary": result.summary,
            "output": result.output,
            "error": result.error,
            "reason": reason,
        }

        skill_history = state.get("skill_history", []) + [record]
        evidence = state.get("evidence", []) + result.evidence
        candidate_causes = (
                state.get("candidate_causes", []) + result.candidate_causes
        )

        recorder.append(
            trace_id=trace_id,
            case_id=case_id,
            event_type="skill_called",
            payload=record,
        )

        if result.evidence:
            recorder.append(
                trace_id=trace_id,
                case_id=case_id,
                event_type="evidence_added",
                payload={"evidence": result.evidence},
            )

        if result.candidate_causes:
            recorder.append(
                trace_id=trace_id,
                case_id=case_id,
                event_type="candidate_causes_updated",
                payload={"candidate_causes": candidate_causes},
            )

        return {
            **state,
            "step": step + 1,
            "skill_history": skill_history,
            "evidence": evidence,
            "candidate_causes": candidate_causes,
        }

    raise ValueError(f"Unknown action type: {action_type}")


#是否继续
def should_continue(state : DiagnosisState) -> str:
    if state.get("done"):
        return "summarize"
    if state.get("step", 0) >= len(state.get("plan", [])):
        return "summarize"
    if state.get("step", 0) >= len(state.get("tool_history", [])):
        return "summarize"
    return "act"

# 总结节点
def summarize_node(
    state: DiagnosisState,
    recorder: TraceRecorder,
) -> DiagnosisState:
    candidate_causes = state.get("candidate_causes", [])
    evidence = state.get("evidence", [])

    if candidate_causes:
        lines = ["诊断完成，发现以下候选原因："]

        for i, cause in enumerate(candidate_causes, start=1):
            lines.append(
                f"{i}. {cause.get('description')} "
                f"置信度：{cause.get('confidence', 'unknown')}"
            )
    else:
        lines = ["诊断完成，暂未发现明确候选原因。"]

    if evidence:
        lines.append("")
        lines.append("主要证据：")
        for i, ev in enumerate(evidence[:5], start=1):
            lines.append(f"{i}. {ev.get('summary')}")

    final_answer = "\n".join(lines)

    new_state : DiagnosisState = {
        **state,
        "done": True,
        "status": "completed",
        "final_answer": final_answer,
    }

    recorder.append(
        trace_id=state["trace_id"],
        case_id=state["case_id"],
        event_type="final_answer",
        payload={"final_answer": final_answer},
    )

    recorder.append(
        trace_id=state["trace_id"],
        case_id=state["case_id"],
        event_type="case_completed",
        payload={
            "candidate_causes": candidate_causes,
            "evidence_count": len(evidence),
        },
    )

    return new_state



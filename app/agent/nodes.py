
from __future__ import annotations

from curses import panel
from typing import Any
import json
from app.harness.service import HarnessService
from app.agent.state import DiagnosisState
from app.llm.client import LLMClient
from app.llm.parser import extract_json_object
from app.llm.prompts import build_planner_messages, build_summerize_messages
from app.skills.registry import SkillRegistry
from app.tools.registry import ToolRegistry
from app.tracing.recorder import TraceRecorder
from app.tracing.db_recorder import DBTraceRecorder

#初始节点，创建trace_id,追加jsonl，更新诊断状态
def initialize_node(
        state : DiagnosisState,
        recorder : DBTraceRecorder
) -> DiagnosisState:

    new_state: DiagnosisState = {
        **state,
        "step" : 0,
        "max_steps" : state.get("max_steps", 8),
        "tool_history" : [],
        "skill_history" : [],
        "evidence" : [],
        "candidate_causes" : [],
        "plan" : [],
        "done" : False,
        "status" : "running"
        "error" : None,
    }

    recorder.append(
        trace_id = new_state['run_uid'],
        case_id = new_state['case_uid'],
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
        *,
        llm: LLMClient,
        tools: ToolRegistry,
        skills: SkillRegistry,
        recorder : DBTraceRecorder
) -> DiagnosisState:

    messages = build_planner_messages(
        user_query=state['user_query'],
        time_window=state['time_window'],
        scope=state['scope'],
        tool_specs= tools.list_spec(),
        skill_sepcs = skills.list_spec(),
    )
    raw = llm.complete(messages, temperature= 0.1)
    parsed = extract_json_object(raw)
    intent = parsed.get("intent","unknown")

    plan = parsed.get("plan", [])
    # 降级处理
    if not isinstance(plan, list) or not plan:
        plan = [
            {
                "type" : "tool",
                "name" : "test_db_connection",
                "arguments" : [],
                "reason" : "LLM未生成有效计划，降级为数据库连通性检查"
            }
        ]
    new_state : DiagnosisState = {
        **state,
        "intent" : intent,
        "plan" : plan,
    }

    recorder.append(
        run_uid = state['run_uid'],
        case_uid= state['case_uid'],
        event_type= "plan_created",
        payload = {
            "intent" : intent,
            "plan" : plan,
            "raw_llm_output" : raw
        }
    )

    return new_state

#执行节点，执行plan中的当前步骤
def act_node(
        state : DiagnosisState,
        *,
        harness:HarnessService,
        recorder : DBTraceRecorder,
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

    run_uid = state['run_uid']
    case_uid = state['case_uid']

    try:
        if action_type == "tool":
            result = tools.call(name, arguments)

            record = {
                "step" : step,
                "type" : "tool",
                "name" : name,
                "arguments" : arguments,
                "ok" : result.ok,
                "summary" : result.summary,
                "output": result.output,
                "error" : result.error,
                "reason" : reason,
            }
            harness.add_tool_call(
                run_uid = run_uid,
                case_uid=case_uid,
                step = step,
                tool_name=name,
                arguments = arguments,
                ok = result.ok,
                output_summary=result.ouput,
                error = result.error,
                reason = reason,
            )
            tool_history = state.get("tool_history", []) + [record]

            recorder.append(
                run_uid = run_uid,
                case_id = case_id,
                event_type="tool_called",
                payload = record,
            )
            return {
                **state,
                "step" : step + 1,
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
                "type" : "skill",
                "name": name,
                "arguments": arguments,
                "ok": result.ok,
                "summary": result.summary,
                "output": result.output,
                "error": result.error,
                "reason": reason,
            }
            harness.add_skill_call(
                run_uid = run_uid,
                case_uid=case_uid,
                step = step,
                skill_name=name,
                arguments=arguments,
                ok=result.ok,
                summary=result.summary,
                evidence=result.evidence,
                candidate_causes=result.candidate_causes,
                error = result.error,
                reason = reason,
            )

            skill_history = state.get("skill_history", []) + [record]
            evidence = state.get("evidence", []) + result.evidence
            candidate_causes = (
                    state.get("candidate_causes", []) + result.candidate_causes
            )

            recorder.append(
                run_uid = run_uid,
                case_uid=case_uid,
                event_type="skill_called",
                payload=record,
            )

            if result.evidence:
                recorder.append(
                    run_uid = run_uid,
                    case_uid= case_uid,
                    event_type="evidence_added",
                    payload={"evidence": result.evidence},
                )

            if result.candidate_causes:
                recorder.append(
                    run_uid = run_uid,
                    case_uid = case_uid,
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
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

        recorder.append(
            run_uid = run_uid,
            case_uid = case_uid,
            event_type="step_failed",
            payload = {
                "step" : step,
                "action" : action,
                "error" : error,
            },
        )
        return {
            **state,
            "done" : True,
            "status" : "failed",
            "error" : error,
        }


#是否继续
def should_continue(state : DiagnosisState) -> str:
    if state.get("status") == "failed":
        return "fail"
    if state.get("done"):
        return "summarize"
    if state.get("step", 0) >= len(state.get("plan", [])):
        return "summarize"
    if state.get("step", 0) >= state.get("max_steps", 8):
        return "summarize"
    return "act"

# 总结节点
def summarize_node(
    state: DiagnosisState,
    *,
    llm : LLMClient,
    recorder: DBTraceRecorder,
    harness:HarnessService
) -> DiagnosisState:
    messages = build_summerize_messages(
        user_query=state.get("user_query"),
        evidence=state.get("evidence", []),
        candidate_causes = state.get("candidate_causes", []),
        tool_history=state.get("tool_history",[]),
        skill_history=state.get("skill_history",[]),
    )
    final_answer = llm.complete(messages,temperature= 0.2)

    new_state : DiagnosisState = {
        **state,
        "done": True,
        "status": "completed",
        "final_answer": final_answer,
    }

    recorder.append(
        run_uid=state["run_uid"],
        case_uid=state["case_uid"],
        event_type="final_answer",
        payload={"final_answer": final_answer},
    )

    recorder.append(
        run_uid=state["run_uid"],
        case_uid=state["case_uid"],
        event_type="case_completed",
        payload={
            "candidate_causes": candidate_causes,
            "evidence_count": len(evidence),
        },
    )

    return new_state

# 使用工具失败节点
def fail_node(
        state : DiagnosisState,
        *,
        recorder : DBTraceRecorder,
        harness : HarnessService
) -> DiagnosisState:
    error = state.get("error") or "unknown_error"

    harness.fail_run(
        run_uid=state["run_uid"],
        case_uid=state["case_uid"],
        error = error,
    )

    recorder.append(
        run_uid= state["run_uid"],
        case_uid = state["case_uid"],
        event_type= "case_failed",
        payload ={"error" : error},
    )
    return {
        **state,
        "done" : True,
        "status" : "failed",
        "final_answer": f"诊断失败：{error}"
    }

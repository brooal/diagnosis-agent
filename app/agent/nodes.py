from __future__ import annotations

from typing import Any

from app.harness.service import HarnessService
from app.agent.context_builder import build_rag_context
from app.agent.state import DiagnosisState
from app.llm.client import LLMClient
from app.llm.parser import extract_json_object
from app.llm.prompts import build_final_messages, build_react_messages
from app.rag.service import RagService
from app.skills.common import SkillRegistry
from app.tools.registry import ToolRegistry
from app.tracing.db_recorder import DBTraceRecorder


# 初始节点，创建 ReAct 执行所需的状态。
def initialize_node(
    state: DiagnosisState,
    recorder: DBTraceRecorder,
) -> DiagnosisState:
    new_state: DiagnosisState = {
        **state,
        "step": 0,
        "max_steps": state.get("max_steps", 8),
        "done": False,
        "status": "running",
        "current_thought": None,
        "current_action": None,
        "react_history": [],
        "rag_context": state.get("rag_context", {"enabled": False, "results": []}),
        "rag_history": state.get("rag_history", []),
        "tool_history": [],
        "skill_history": [],
        "observations": [],
        "evidence": [],
        "candidate_causes": [],
        "final_answer": None,
        "error": None,
    }

    recorder.append(
        run_uid=new_state["run_uid"],
        case_uid=new_state["case_uid"],
        event_type="case_started",
        payload={
            "trigger_source": new_state.get("trigger_source"),
            "user_query": new_state.get("user_query"),
            "time_window": new_state.get("time_window"),
            "scope": new_state.get("scope"),
        },
    )
    return new_state


def retrieve_rag_node(
    state: DiagnosisState,
    *,
    rag: RagService | None,
    recorder: DBTraceRecorder,
) -> DiagnosisState:
    if not state.get("enable_rag", False):
        return {
            **state,
            "rag_context": {"enabled": False, "results": []},
        }

    limit = int(state.get("rag_limit", 5))
    include_system_design = bool(state.get("rag_include_system_design", False))

    if rag is None:
        context = {
            "enabled": True,
            "limit": limit,
            "include_system_design": include_system_design,
            "results": [],
            "error": "rag_service_not_configured",
        }
        recorder.append(
            run_uid=state["run_uid"],
            case_uid=state["case_uid"],
            event_type="rag_retrieval_failed",
            payload=context,
        )
        return {
            **state,
            "rag_context": context,
            "rag_history": state.get("rag_history", []) + [context],
        }

    try:
        context = build_rag_context(
            rag,
            state,
            limit=limit,
            include_system_design=include_system_design,
        )
        recorder.append(
            run_uid=state["run_uid"],
            case_uid=state["case_uid"],
            event_type="rag_retrieved",
            payload=context,
        )
    except Exception as exc:
        context = {
            "enabled": True,
            "limit": limit,
            "include_system_design": include_system_design,
            "results": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
        recorder.append(
            run_uid=state["run_uid"],
            case_uid=state["case_uid"],
            event_type="rag_retrieval_failed",
            payload=context,
        )

    return {
        **state,
        "rag_context": context,
        "rag_history": state.get("rag_history", []) + [context],
    }


# ReAct 计划节点：基于已有 observation 决定下一步单个动作。
def plan_node(
    state: DiagnosisState,
    *,
    llm: LLMClient,
    tools: ToolRegistry,
    skills: SkillRegistry,
    recorder: DBTraceRecorder,
) -> DiagnosisState:
    step = state.get("step", 0)
    max_steps = state.get("max_steps", 8)
    run_uid = state["run_uid"]
    case_uid = state["case_uid"]

    if step >= max_steps:
        recorder.append(
            run_uid=run_uid,
            case_uid=case_uid,
            event_type="react_max_steps_reached",
            payload={"step": step, "max_steps": max_steps},
        )
        return {
            **state,
            "done": True,
            "current_action": None,
            "current_thought": "达到最大执行步数，进入总结。",
        }

    try:
        messages = build_react_messages(
            user_query=state.get("user_query"),
            time_window=state.get("time_window"),
            scope=state.get("scope"),
            conversation_context=state.get("conversation_context"),
            rag_context=state.get("rag_context"),
            tool_specs=tools.list_spec(expose_to_agent_only=True),
            skill_specs=skills.list_spec(),
            react_history=state.get("react_history", []),
            observations=state.get("observations", []),
            evidence=state.get("evidence", []),
            candidate_causes=state.get("candidate_causes", []),
        )
        raw = llm.complete(messages, temperature=0.1)
        parsed = extract_json_object(raw)

        thought = str(parsed.get("thought") or "").strip()
        action_type = str(parsed.get("action_type") or "").strip().lower()
        action_name = str(parsed.get("action_name") or parsed.get("name") or "").strip()
        arguments = parsed.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValueError("ReAct action arguments must be an object.")

        if action_type == "finish":
            final_answer = str(parsed.get("final_answer") or "").strip() or None
            action = {
                "type": "finish",
                "name": "",
                "arguments": {},
                "reason": thought,
            }
            react_entry = {
                "step": step,
                "thought": thought,
                "action": action,
                "final_answer": final_answer,
            }

            recorder.append(
                run_uid=run_uid,
                case_uid=case_uid,
                event_type="react_finished",
                payload={
                    **react_entry,
                    "raw_llm_output": raw,
                },
            )
            return {
                **state,
                "done": True,
                "current_thought": thought,
                "current_action": action,
                "react_history": state.get("react_history", []) + [react_entry],
                "final_answer": final_answer,
            }

        if action_type not in {"tool", "skill"}:
            raise ValueError(f"Unknown ReAct action type: {action_type}")
        if not action_name:
            raise ValueError("ReAct action name is required for tool or skill actions.")
        if action_type == "tool":
            tools.get(action_name)
        else:
            skills.get(action_name)

        action = {
            "type": action_type,
            "name": action_name,
            "arguments": arguments,
            "reason": thought,
        }
        react_entry = {
            "step": step,
            "thought": thought,
            "action": action,
        }

        recorder.append(
            run_uid=run_uid,
            case_uid=case_uid,
            event_type="react_action_planned",
            payload={
                **react_entry,
                "raw_llm_output": raw,
            },
        )

        return {
            **state,
            "current_thought": thought,
            "current_action": action,
            "react_history": state.get("react_history", []) + [react_entry],
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        recorder.append(
            run_uid=run_uid,
            case_uid=case_uid,
            event_type="react_planning_failed",
            payload={"step": step, "error": error},
        )
        return {
            **state,
            "done": True,
            "status": "failed",
            "error": error,
            "current_action": None,
        }


# 执行节点，执行当前 ReAct 动作并把结果写入 observation。
def act_node(
    state: DiagnosisState,
    *,
    harness: HarnessService,
    recorder: DBTraceRecorder,
    tools: ToolRegistry,
    skills: SkillRegistry,
) -> DiagnosisState:
    step = state.get("step", 0)
    action = state.get("current_action")
    if not action:
        return {**state, "done": True}

    action_type = action["type"]
    name = action["name"]
    arguments = action.get("arguments", {})
    reason = action.get("reason", "")

    run_uid = state["run_uid"]
    case_uid = state["case_uid"]

    try:
        if action_type == "tool":
            result = tools.call(name, arguments)

            record = {
                "step": step,
                "type": "tool",
                "name": name,
                "arguments": arguments,
                "ok": result.ok,
                "summary": result.summary,
                "output": result.output,
                "error": result.error,
                "reason": reason,
            }
            harness.add_tool_call(
                run_uid=run_uid,
                case_uid=case_uid,
                step=step,
                tool_name=name,
                arguments=arguments,
                ok=result.ok,
                output_summary=result.summary,
                error=result.error,
                reason=reason,
            )
            tool_history = state.get("tool_history", []) + [record]
            observation = _build_observation(record)

            recorder.append(
                run_uid=run_uid,
                case_uid=case_uid,
                event_type="tool_called",
                payload=record,
            )
            recorder.append(
                run_uid=run_uid,
                case_uid=case_uid,
                event_type="observation_added",
                payload=observation,
            )
            return {
                **state,
                "step": step + 1,
                "current_thought": None,
                "current_action": None,
                "tool_history": tool_history,
                "observations": state.get("observations", []) + [observation],
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
                "type": "skill",
                "name": name,
                "arguments": arguments,
                "ok": result.ok,
                "summary": result.summary,
                "output": result.output,
                "error": result.error,
                "reason": reason,
            }
            harness.add_skill_call(
                run_uid=run_uid,
                case_uid=case_uid,
                step=step,
                skill_name=name,
                arguments=arguments,
                ok=result.ok,
                summary=result.summary,
                evidence=result.evidence,
                candidate_causes=result.candidate_causes,
                error=result.error,
                reason=reason,
            )

            skill_history = state.get("skill_history", []) + [record]
            evidence = state.get("evidence", []) + result.evidence
            candidate_causes = (
                state.get("candidate_causes", []) + result.candidate_causes
            )
            observation = _build_observation(record)

            recorder.append(
                run_uid=run_uid,
                case_uid=case_uid,
                event_type="skill_called",
                payload=record,
            )
            recorder.append(
                run_uid=run_uid,
                case_uid=case_uid,
                event_type="observation_added",
                payload=observation,
            )

            if result.evidence:
                recorder.append(
                    run_uid=run_uid,
                    case_uid=case_uid,
                    event_type="evidence_added",
                    payload={"evidence": result.evidence},
                )

            if result.candidate_causes:
                recorder.append(
                    run_uid=run_uid,
                    case_uid=case_uid,
                    event_type="candidate_causes_updated",
                    payload={"candidate_causes": candidate_causes},
                )

            return {
                **state,
                "step": step + 1,
                "current_thought": None,
                "current_action": None,
                "skill_history": skill_history,
                "evidence": evidence,
                "candidate_causes": candidate_causes,
                "observations": state.get("observations", []) + [observation],
            }

        raise ValueError(f"Unknown action type: {action_type}")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

        recorder.append(
            run_uid=run_uid,
            case_uid=case_uid,
            event_type="step_failed",
            payload={
                "step": step,
                "action": action,
                "error": error,
            },
        )
        return {
            **state,
            "done": True,
            "status": "failed",
            "error": error,
        }


def _build_observation(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": record["step"],
        "source_type": record["type"],
        "source_name": record["name"],
        "ok": record["ok"],
        "summary": record["summary"],
        "output": record["output"],
        "error": record["error"],
    }


def route_after_plan(state: DiagnosisState) -> str:
    if state.get("status") == "failed":
        return "fail"
    if state.get("done"):
        return "summarize"
    if state.get("current_action"):
        return "act"
    return "summarize"


def route_after_act(state: DiagnosisState) -> str:
    if state.get("status") == "failed":
        return "fail"
    if state.get("done"):
        return "summarize"
    if state.get("step", 0) >= state.get("max_steps", 8):
        return "summarize"
    return "plan"


# 兼容旧 import；新图结构使用 route_after_plan / route_after_act。
def should_continue(state: DiagnosisState) -> str:
    return route_after_act(state)


# 总结节点
def summarize_node(
    state: DiagnosisState,
    *,
    llm: LLMClient,
    recorder: DBTraceRecorder,
    harness: HarnessService,
) -> DiagnosisState:
    evidence = state.get("evidence", [])
    candidate_causes = state.get("candidate_causes", [])
    observations = state.get("observations", [])
    final_answer = state.get("final_answer")

    should_generate_report = bool(observations or evidence or candidate_causes)
    if not final_answer or should_generate_report:
        messages = build_final_messages(
            user_query=state.get("user_query"),
            conversation_context=state.get("conversation_context"),
            rag_context=state.get("rag_context"),
            observations=observations,
            evidence=evidence,
            candidate_causes=candidate_causes,
            react_history=state.get("react_history", []),
        )
        final_answer = llm.complete(messages, temperature=0.2)

    harness.complete_run(
        run_uid=state["run_uid"],
        case_uid=state["case_uid"],
        final_answer=final_answer,
        candidate_causes=candidate_causes,
    )

    new_state: DiagnosisState = {
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
    state: DiagnosisState,
    *,
    recorder: DBTraceRecorder,
    harness: HarnessService,
) -> DiagnosisState:
    error = state.get("error") or "unknown_error"

    harness.fail_run(
        run_uid=state["run_uid"],
        case_uid=state["case_uid"],
        error=error,
    )

    recorder.append(
        run_uid=state["run_uid"],
        case_uid=state["case_uid"],
        event_type="case_failed",
        payload={"error": error},
    )
    return {
        **state,
        "done": True,
        "status": "failed",
        "final_answer": f"诊断失败：{error}",
    }

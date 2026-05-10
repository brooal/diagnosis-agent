from __future__ import annotations

import json

def build_planner_messages(
        *,
        user_query : str,
        time_window: str | None = None,
        scope : dict | None,
        tool_specs : list[dict],
        skill_specs : list[dict],
) -> list[dict]:
    system = """
你是加速器故障诊断Agent的规划器。
你只能输出 JSON，不要输出 MarkDown，不要解释。

你可以选择两类动作：
1.tool：细粒度工具，例如查询单个PV、测试数据库的连通性。
2.skill：粗粒度诊断技能，例如束流状态诊断、四级铁电源诊断、PLC状态诊断。

优先选择skill完整完整的诊断任务。
只有当用户询问非常简单的问题时，才选择tool。
不要编造不存在的tool或skill。
"""
    user = {
        "user_query": user_query,
        "time_window": time_window,
        "scope": scope,
        "available_tools" : tool_specs,
        "available_skills" : skill_specs,
        "output_schema": {
            "intent" : "string",
            "plan" : [
                {
                    "type" : "tool | skill",
                    "name" : "string",
                    "arguments": {},
                    "reason" : "string",
                }
            ]
        }
    }

    return [
        {"role" : "system", "content" : system.strip()},
        {"role" : "user", "content" : json.dumps(user,ensure_ascii=False)},
    ]

def build_summerize_messages(
        *,
        user_query : str,
        evidence : list[dict],
        candidate_causes : list[dict],
        tool_history : list[dict],
        skill_history : list[dict],
) -> list[dict]:
    system = """
你是加速器故障诊断报告生成器。
请基于证据和候选原因生成清晰、谨慎、可追溯的中文诊断报告。

要求：
1.不要编造没有证据支持原因。
2.明确说明候选原因、证据、置信度。
3.如果证据不足，要说明证据不足。
4、输出自然语言即可。
"""
    user = {
        "user_query": user_query,
        "evidence": evidence,
        "candidate": candidate_causes,
        "tool_history": tool_history,
        "skill_history": skill_history,
    }
    return [
        {"role" : "system", "content" : system.strip()},
        {"role" : "user", "content" : json.dumps(user,ensure_ascii=False)},
    ]


def build_react_messages(
    *,
    user_query: str | None,
    time_window: dict | None,
    scope: dict | None,
    tool_specs: list[dict],
    skill_specs: list[dict],
    react_history: list[dict],
    observations: list[dict],
    evidence: list[dict],
    candidate_causes: list[dict],
    max_history: int = 8,
) -> list[dict]:
    system = """
你是一个加速器故障诊断 ReAct Agent。

你需要根据用户问题、已有 observation、证据和候选原因，决定下一步动作。

你可以选择：
1. 调用 tool：适合查询数据库、查询 PV、执行简单诊断工具。
2. 调用 skill：适合执行完整诊断能力。
3. finish：当证据足够时，输出最终诊断结论。

重要规则：
- 你只能输出 JSON，不要输出 Markdown。
- 不要编造不存在的 tool 或 skill。
- 不要编造数据库中没有查询到的事实。
- 如果需要事实依据，必须先调用 tool 或 skill。
- 如果工具返回证据不足，可以继续调用其他工具或结束并说明证据不足。
- 每次只选择一个 action。
- 如果已经有足够证据，请选择 finish。
"""

    payload = {
        "user_query": user_query,
        "time_window": time_window,
        "scope": scope,
        "available_tools": tool_specs,
        "available_skills": skill_specs,
        "recent_react_history": react_history[-max_history:],
        "recent_observations": observations[-max_history:],
        "evidence": evidence[-max_history:],
        "candidate_causes": candidate_causes[-max_history:],
        "output_schema_for_action": {
            "thought": "string，说明你为什么选择下一步动作",
            "action_type": "tool | skill | finish",
            "action_name": "tool 或 skill 名称；finish 时可以为空",
            "arguments": "object，调用参数；finish 时可以为空",
            "final_answer": "string，仅 action_type=finish 时填写",
        },
        "examples": [
            {
                "thought": "用户询问某时间段是否发生掉束，需要先调用束流故障诊断工具。",
                "action_type": "tool",
                "action_name": "diagnose_beam_fault",
                "arguments": {
                    "start": "2026-05-06 10:00:00",
                    "end": "2026-05-06 10:05:00"
                }
            },
            {
                "thought": "已经检测到束流掉束，需要围绕掉束时间查询电源异常。",
                "action_type": "tool",
                "action_name": "diagnose_power_faults",
                "arguments": {
                    "fault_time": "2026-05-06T10:02:31+08:00",
                    "window_seconds": 10
                }
            },
            {
                "thought": "已有束流掉束和候选电源异常证据，可以输出最终诊断。",
                "action_type": "finish",
                "action_name": "",
                "arguments": {},
                "final_answer": "根据查询结果，检测到束流掉束，并发现候选电源异常..."
            }
        ],
    }

    return [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def build_final_messages(
    *,
    user_query: str | None,
    observations: list[dict],
    evidence: list[dict],
    candidate_causes: list[dict],
    react_history: list[dict],
) -> list[dict]:
    system = """
你是加速器故障诊断报告生成器。
请根据 observation、证据和候选原因，生成简洁、可信、可追溯的中文诊断结论。

要求：
1. 不要编造证据中没有的信息。
2. 明确说明是否发生故障。
3. 如果有候选原因，说明候选原因和依据。
4. 如果证据不足，明确说明证据不足。
5. 不要输出 JSON，输出自然语言。
"""

    payload = {
        "user_query": user_query,
        "react_history": react_history,
        "observations": observations,
        "evidence": evidence,
        "candidate_causes": candidate_causes,
    }

    return [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
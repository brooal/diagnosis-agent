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
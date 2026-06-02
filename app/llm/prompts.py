from __future__ import annotations

import json

from app.utils.json import make_json_safe
from app.utils.times import now_shanghai_aware

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

自然语言理解规则：
1. time_window 和 scope 可能为空，表示用户只输入了自然语言。
2. 你需要先判断用户意图：
   - 如果是闲聊、询问概念、询问系统能力、询问如何使用、或没有诊断/实时查询意图，不要调用 tool/skill，返回空 plan，并在 intent 中说明是普通问答。
   - 如果是故障诊断或历史数据查询，必须从 user_query 中抽取诊断时间和诊断对象，写入 plan.arguments。
   - 如果用户有诊断意图但没有提供可执行的时间点或时间范围，返回空 plan，并在 intent 中说明需要用户补充时间；但“当前PSS状态/现在安全联锁状态”属于例外，按当前 fake 数据演示模式处理。
3. 时间表达可以来自用户自然语言，例如“2026-05-06 10:00到10:05”“今天10:00到10:05”“昨天10:00到10:05”。相对日期按 current_datetime/timezone 解释。
4. 如果问题涉及束流、束流电流、掉束、beam trip、decay、topoff/恒流中断，优先选择 beam_state_diagnosis，并在 arguments 中填 start/end。不要要求用户明示束流 PV；若用户没有提供 PV，不填 beam_channel/beam_current_pv，让 skill 使用默认配置。
5. 如果 beam_state_diagnosis 的结果显示存在束流故障、beam_drop、beam_trip、decay 或 topoff 中断现象，应查看该 skill 输出中的 recommended_next_skills，并按推荐继续调用当前已实现的原因诊断 skill。当前 quadrupole_power_diagnosis 只是已接入的一类原因排查，不代表全部故障原因；不要要求用户必须提到四极铁才继续排查。
6. 如果问题涉及 PSS、安全联锁、联锁中断、interlocked/unlocked，优先选择 pss_interlock_interrupt_diagnosis；历史诊断要在 arguments 中填 start/end；如果用户询问“当前PSS状态/现在PSS状态/当前安全联锁状态”且没有给出时间窗口，arguments 中设置 use_current_fake_data=true，用当前上海时间生成本地演示 fake 数据；不要把 sysStatus_Eunlocked:bi 当作根因。
"""
    user = {
        "user_query": user_query,
        "time_window": time_window,
        "scope": scope,
        "current_datetime": now_shanghai_aware().isoformat(),
        "timezone": "Asia/Shanghai",
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
        {"role" : "user", "content" : _dump_json(user)},
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
        {"role" : "user", "content" : _dump_json(user)},
    ]


def build_react_messages(
    *,
    user_query: str | None,
    time_window: dict | None,
    scope: dict | None,
    conversation_context: dict | None,
    rag_context: dict | None,
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
- 相关检索资料只作为背景参考；如果与 tool 或 skill 的实时结果冲突，以实时结果为准。
- 引用检索资料时使用资料编号，例如 [RAG-1]。
- 每次只选择一个 action。
- 如果已经有足够证据，请选择 finish。
- finish 的 final_answer 只是草稿；最终报告会由报告生成器统一规范化。PSS 诊断草稿也不要使用“候选原因/候选根因”，应表述为“诊断结果是...”。

自然语言理解规则：
- time_window 和 scope 可能为空；这表示调用方只传入了自然语言 user_query。
- 你必须先判断用户问题类型：
  1. 如果用户是在闲聊、询问系统能力、询问概念、询问如何使用、或没有诊断/查询实时数据的意图，选择 finish，直接回答，不要调用 tool/skill。
  2. 如果用户有故障诊断或历史数据查询意图，你要从 user_query 中抽取时间窗口和诊断对象，并把它们写入下一步 action 的 arguments。
  3. 如果用户有诊断意图但没有给出可执行的时间点或时间范围，选择 finish，礼貌要求用户补充具体时间，不要调用 tool/skill；但“当前PSS状态/现在安全联锁状态”属于例外，应调用 PSS skill 并设置 use_current_fake_data=true。
- 时间抽取要求：
  - 支持“2026-05-06 10:00到10:05”“2026年5月6日10:00到10:05”“今天10:00到10:05”“昨天10:00到10:05”等表达。
  - 相对日期必须基于 payload.current_datetime 和 payload.timezone 解释。
  - 传给 tool/skill 时尽量使用 ISO 格式，例如 2026-05-06T10:00:00+08:00。
- 诊断对象和后续动作要求：
  - 如果用户提到束流、束流电流、掉束、beam trip、decay、topoff/恒流中断，优先调用 beam_state_diagnosis，arguments 中包含 start/end。不要要求用户明示束流 PV；若用户没有提供 PV，不填 beam_channel/beam_current_pv，让 skill 使用默认配置。
  - 如果 beam_state_diagnosis 的 observation 显示存在束流故障、beam_drop、beam_trip、decay 或 topoff 中断现象，应查看该 skill 输出中的 recommended_next_skills，并按推荐继续调用当前已实现的原因诊断 skill。
  - 当前 quadrupole_power_diagnosis 只是已接入的一类束流故障原因排查，不代表全部故障原因；不要要求用户必须提到四极铁才调用后续原因排查。
  - 如果用户提到 PSS、安全联锁、联锁中断、interlocked/unlocked，优先调用 pss_interlock_interrupt_diagnosis；历史诊断时 arguments 中包含 start/end；PSS 前缀可从用户文本抽取为 prefix，否则不填。
  - 如果用户询问“当前PSS状态/现在PSS状态/当前安全联锁状态”等当前状态问题且没有给出时间窗口，调用 pss_interlock_interrupt_diagnosis，并设置 arguments.use_current_fake_data=true。该模式用于本地演示：工具会用当前上海时间随机模拟一次 interlocked->unlocked 变化，并在七类 fake 原因中随机选择一种。
  - 不要把 sysStatus_Eunlocked:bi 当作 PSS 根因；它只能作为伴随状态，PSS 原因应由 interlocked->unlocked 事件后的原因 PV 回溯确定。
"""

    payload = {
        "conversation_context": conversation_context or {"recent_turns": []},
        "current_datetime": now_shanghai_aware().isoformat(),
        "timezone": "Asia/Shanghai",
        "retrieved_context": _render_rag_context(rag_context),
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
                "thought": "用户询问某时间段是否发生掉束或 decay，需要先调用束流状态诊断 skill；用户未提供束流 PV，因此不传 beam_channel，使用默认配置。",
                "action_type": "skill",
                "action_name": "beam_state_diagnosis",
                "arguments": {
                    "start": "2026-05-06 10:00:00",
                    "end": "2026-05-06 10:05:00"
                }
            },
            {
                "thought": "beam_state_diagnosis 已检测到束流故障，并推荐继续调用 quadrupole_power_diagnosis；这是当前已接入的一类原因排查。",
                "action_type": "skill",
                "action_name": "quadrupole_power_diagnosis",
                "arguments": {
                    "fault_time": "2026-05-06T10:02:31+08:00"
                }
            },
            {
                "thought": "已有束流掉束和候选电源异常证据，可以输出最终诊断。",
                "action_type": "finish",
                "action_name": "",
                "arguments": {},
                "final_answer": "根据查询结果，检测到束流掉束，并发现电源异常证据..."
            }
        ],
    }

    return [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": _dump_json(payload)},
    ]


def build_final_messages(
    *,
    user_query: str | None,
    conversation_context: dict | None,
    rag_context: dict | None,
    observations: list[dict],
    evidence: list[dict],
    candidate_causes: list[dict],
    react_history: list[dict],
) -> list[dict]:
    system = """
你是加速器故障诊断报告生成器。
请根据 observation、证据和结构化诊断结果，生成规范、专业、可截图用于论文展示的最终诊断报告。

要求：
1. 不要编造证据中没有的信息。
2. 输出语言必须跟随用户问题：用户问题主要为英文时输出英文；否则输出中文。
3. 不要使用“候选原因”“候选根因”“可能根因”作为最终表述；如果证据充分，直接写“诊断结果是……”或“Diagnosis result: ...”。
4. 如果证据不足，写“诊断结果：证据不足，暂不能确定直接原因”，并说明缺少什么证据。
5. 相关检索资料只作为背景参考；如果与实时 observation 冲突，以实时 observation 为准。
6. 如果引用检索资料，请使用资料编号，例如 [RAG-1]。
7. 不要输出 JSON，输出自然语言。可以使用 Markdown 标题和列表，便于前端渲染和论文截图。

PSS 安全联锁诊断报告格式要求：
- 如果 observation 或 skill 名称涉及 pss_interlock_interrupt_diagnosis、PSS、安全联锁、interlocked/unlocked，请使用下面的固定结构。
- 如果 observation/tool_output 中包含 fake_data.mode=current_fake，不要在最终报告中展示“本地模拟 fake 数据”“不代表真实线上状态”等数据来源说明；该标记仅用于后端调试和测试。
- 中文结构：
  ## PSS安全联锁异常诊断报告
  **诊断结果：** 用一句话说明直接诊断结论，例如“诊断结果是第 3 个急停按钮触发导致 PSS 由联锁状态转为解锁状态。”
  **事件概况：** 写明检测时间窗口、事件时间、状态变化（interlocked -> unlocked）。
  **关键证据：**
  - 状态迁移证据：列出 sysStatus_interlocked 和 sysStatus_unlocked 的变化及时间。
  - 直接原因证据：列出直接原因 PV、变化、时间、相对事件时间、置信度。
  - 伴随状态：列出 sysStatus_Eunlocked 或 interlock output 等伴随/结果状态，并明确“该状态不是直接原因证据”。
  **结论说明：** 用 1-2 句话说明为什么该 PV 被判定为直接原因，以及是否需要进一步复查。
- 英文结构：
  ## PSS Interlock Abnormality Diagnosis Report
  **Diagnosis result:** ...
  **Event overview:** ...
  **Key evidence:**
  - State transition evidence: ...
  - Direct-cause evidence: ...
  - Accompanying states: ...
  **Conclusion:** ...
- PSS 报告中不要使用“候选原因/候选根因/candidate cause/candidate root cause”等词；可以使用“直接原因证据”“伴随状态”“结构化证据”。
- 对 sysStatus_Eunlocked:bi 的表述必须规范：它是紧急解锁状态或伴随结果状态，不应作为直接原因，除非 evidence 中存在明确人工紧急解锁命令 PV。
"""

    payload = {
        "conversation_context": conversation_context or {"recent_turns": []},
        "retrieved_context": _render_rag_context(rag_context),
        "user_query": user_query,
        "react_history": react_history,
        "observations": observations,
        "evidence": evidence,
        "candidate_causes": candidate_causes,
    }

    return [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": _dump_json(payload)},
    ]


def _dump_json(payload: dict) -> str:
    return json.dumps(make_json_safe(payload), ensure_ascii=False)


def _render_rag_context(rag_context: dict | None) -> str:
    if not rag_context or not rag_context.get("enabled"):
        return "未启用 RAG 检索。"
    if rag_context.get("error"):
        return f"RAG 检索失败：{rag_context['error']}"

    results = rag_context.get("results") or []
    if not results:
        return "RAG 检索未返回相关资料。"

    lines = [
        "相关检索资料：",
        "这些资料仅作为背景参考；实时 tool/skill observation 的优先级更高。",
    ]
    for index, item in enumerate(results, start=1):
        metadata = item.get("metadata") or {}
        doc_type = item.get("doc_type") or metadata.get("doc_type") or "unknown"
        source = item.get("source") or metadata.get("source") or "unknown"
        title = metadata.get("title")
        section = metadata.get("section") or metadata.get("section_title")
        case_id = metadata.get("case_id")
        extra = _format_rag_metadata(
            {
                "title": title,
                "section": section,
                "case_id": case_id,
            }
        )
        text = str(item.get("text") or "").strip()
        if len(text) > 1200:
            text = f"{text[:1200]}..."
        lines.extend(
            [
                f"[RAG-{index}] 类型：{doc_type}",
                f"来源：{source}",
            ]
        )
        if extra:
            lines.append(f"信息：{extra}")
        lines.extend(["内容：", text])
    return "\n".join(lines)


def _format_rag_metadata(metadata: dict[str, object | None]) -> str:
    parts = [
        f"{key}={value}"
        for key, value in metadata.items()
        if value is not None and value != ""
    ]
    return "；".join(parts)

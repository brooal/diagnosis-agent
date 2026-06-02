from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.prompts import build_final_messages


def test_final_prompt_requires_standard_pss_report_and_language_following() -> None:
    messages = build_final_messages(
        user_query="诊断2026-05-21 10:00到10:10的PSS安全联锁状态",
        conversation_context=None,
        rag_context=None,
        observations=[
            {
                "source_name": "pss_interlock_interrupt_diagnosis",
                "summary": "第 3 个急停按钮触发导致 PSS 联锁中断。",
            }
        ],
        evidence=[],
        candidate_causes=[],
        react_history=[],
    )

    system = messages[0]["content"]

    assert "PSS安全联锁异常诊断报告" in system
    assert "诊断结果是" in system
    assert "输出语言必须跟随用户问题" in system
    assert "不要使用“候选原因”“候选根因”“可能根因”" in system
    assert "sysStatus_Eunlocked:bi" in system
    assert "不是直接原因证据" in system
    assert "fake_data.mode=current_fake" in system
    assert "不要在最终报告中展示" in system
    assert "仅用于后端调试和测试" in system

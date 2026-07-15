from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BEAM_KEYWORDS = ("束流", "掉束", "流强", "beam", "drop", "decay", "topoff", "恒流")
PSS_KEYWORDS = ("pss", "安全联锁", "人身安全", "联锁", "急停", "门禁", "解锁", "interlock")
POWER_KEYWORDS = ("四极铁", "四级铁", "quadrupole", "电源", "power", "current:ai")
DIAGNOSIS_KEYWORDS = ("诊断", "排查", "分析", "故障", "异常", "为什么", "原因", "检查")


def classify(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _classify(payload)
    except Exception as exc:
        return {
            "ok": False,
            "summary": "故障类型判断失败。",
            "diagnosis": {
                "classification": "unknown",
                "diagnostic_intent": False,
                "recommended_next_skill": None,
                "reason": "",
            },
            "error": f"{type(exc).__name__}: {exc}",
        }


def _classify(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("user_query") or "").lower()
    scope = payload.get("scope") or {}
    scope_text = json.dumps(scope, ensure_ascii=False).lower() if isinstance(scope, dict) else str(scope).lower()
    text = f"{query} {scope_text}"

    has_beam_samples = bool(payload.get("beam_samples") or payload.get("mode_samples") or payload.get("alarm_samples"))
    has_power_samples = bool(payload.get("power_samples"))
    has_pss_samples = bool(payload.get("pss_samples"))
    diagnostic_intent = _contains(text, DIAGNOSIS_KEYWORDS) or any(
        [has_beam_samples, has_power_samples, has_pss_samples]
    )

    classification = "unknown"
    next_skill = None
    reason = "未识别到明确的诊断对象。"

    if _contains(text, PSS_KEYWORDS) or has_pss_samples:
        classification = "pss"
        next_skill = "pss_interlock_diagnosis"
        reason = "问题或样本指向 PSS 安全联锁系统。"
    elif _contains(text, POWER_KEYWORDS) and not _contains(text, BEAM_KEYWORDS):
        classification = "quadrupole_power"
        next_skill = "quadrupole_power_diagnosis"
        reason = "问题指向四极铁电源状态。"
    elif _contains(text, BEAM_KEYWORDS) or has_beam_samples:
        classification = "beam"
        next_skill = "beam_decay_drop_diagnosis"
        reason = "问题或样本指向束流状态、decay 或掉束。"
    elif not diagnostic_intent:
        classification = "general_question"
        reason = "没有明确故障诊断意图，不建议调用诊断 Skill。"

    summary = (
        f"判断为 {classification} 类型，建议调用 {next_skill}。"
        if next_skill
        else f"判断为 {classification} 类型，暂不建议调用专项诊断 Skill。"
    )
    return {
        "ok": True,
        "summary": summary,
        "diagnosis": {
            "classification": classification,
            "diagnostic_intent": diagnostic_intent,
            "recommended_next_skill": next_skill,
            "reason": reason,
            "time_window": {
                "start": payload.get("start"),
                "end": payload.get("end"),
            },
        },
        "error": None,
    }


def _contains(text: str, keywords: tuple[str, ...]) -> bool:
    return any(item.lower() in text for item in keywords)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run portable accelerator fault classification.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = classify(payload)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    _main()

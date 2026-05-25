from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.runner import DiagnosisAgentRunner
from app.tools import build_tool_registry


def main() -> None:
    args = _parse_args()
    scope = {
        "beam_current_pv": args.beam_channel,
        "power_pattern": args.power_pattern,
        "enable_rag": args.enable_rag,
    }

    if args.dry_tool:
        _run_tool_smoke(args)
        return

    runner = DiagnosisAgentRunner()
    try:
        state = runner.run_chat(
            user_query=args.query,
            time_window={"start": args.start, "end": args.end},
            scope=scope,
            enable_rag=args.enable_rag,
            rag_limit=args.rag_limit,
        )
    finally:
        runner.close()

    print("status:", state.get("status"))
    print("thread_uid:", state.get("thread_uid"))
    print("case_uid:", state.get("case_uid"))
    print("run_uid:", state.get("run_uid"))
    if state.get("error"):
        print("error:", state["error"])

    print("\nreact_history:")
    print(_json_dump(state.get("react_history", [])))

    print("\nobservations:")
    print(_json_dump(_compact_observations(state.get("observations", []))))

    print("\nfinal_answer:")
    print(state.get("final_answer") or "")


def _run_tool_smoke(args: argparse.Namespace) -> None:
    tools = build_tool_registry()
    result = tools.call(
        "fetch_beam_samples",
        {
            "beam_channel": args.beam_channel,
            "start": args.start,
            "end": args.end,
            "limit": args.limit,
        },
    )
    print("tool:", "fetch_beam_samples")
    print("ok:", result.ok)
    print("summary:", result.summary)
    if result.error:
        print("error:", result.error)
    output = result.output if isinstance(result.output, list) else []
    print("sample_count:", len(output))
    print("first_samples:")
    print(_json_dump(output[: min(len(output), 5)]))


def _compact_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted = []
    for item in observations:
        output = item.get("output")
        if isinstance(output, list):
            output_summary: Any = {"list_count": len(output), "first_items": output[:3]}
        elif isinstance(output, dict):
            output_summary = output
        else:
            output_summary = output
        compacted.append(
            {
                "step": item.get("step"),
                "source_type": item.get("source_type"),
                "source_name": item.get("source_name"),
                "ok": item.get("ok"),
                "summary": item.get("summary"),
                "error": item.get("error"),
                "output": output_summary,
            }
        )
    return compacted


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local diagnosis-agent smoke test.")
    parser.add_argument("--start", required=True, help="ISO time, e.g. 2026-05-06T10:00:00+08:00")
    parser.add_argument("--end", required=True, help="ISO time, e.g. 2026-05-06T10:05:00+08:00")
    parser.add_argument("--beam-channel", default="RNG:BEAM:CURR")
    parser.add_argument("--power-pattern", default="%SR_PS_QM%:current:ai")
    parser.add_argument("--query", default=None)
    parser.add_argument("--enable-rag", action="store_true")
    parser.add_argument("--rag-limit", type=int, default=5)
    parser.add_argument("--limit", type=int, default=5, help="Sample limit for --dry-tool.")
    parser.add_argument(
        "--dry-tool",
        action="store_true",
        help="Only test DB/PV tool access; skip LLM and Agent graph.",
    )
    args = parser.parse_args()
    if args.query is None:
        args.query = (
            f"请分析 {args.start} 到 {args.end} 是否发生束流掉束，"
            "并在发现掉束时检查四极铁电源是否有异常。"
        )
    return args


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.harness.models import DiagnosisCase, DiagnosisSkillCall, DiagnosisToolCall, HarnessRun, HarnessTurn


def export_sft_jsonl(
    db: Session,
    output_path: Path,
    *,
    case_uid: str | None = None,
    run_uid: str | None = None,
) -> int:
    rows = _load_case_rows(db, case_uid=case_uid, run_uid=run_uid)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with output_path.open("w", encoding="utf-8") as fh:
        for case in rows:
            record = _build_sft_record(db, case)
            if record is None:
                continue
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def _load_case_rows(
    db: Session,
    *,
    case_uid: str | None,
    run_uid: str | None,
) -> list[DiagnosisCase]:
    query = db.query(DiagnosisCase).order_by(DiagnosisCase.created_at.asc())
    if case_uid:
        query = query.filter(DiagnosisCase.case_uid == case_uid)
    if run_uid:
        query = query.filter(DiagnosisCase.run_uid == run_uid)
    return query.all()


def _build_sft_record(db: Session, case: DiagnosisCase) -> dict[str, Any] | None:
    if not case.turn_uid:
        return None

    turn = db.query(HarnessTurn).filter(HarnessTurn.turn_uid == case.turn_uid).one_or_none()
    if turn is None:
        return None

    run = None
    if case.run_uid:
        run = db.query(HarnessRun).filter(HarnessRun.run_uid == case.run_uid).one_or_none()

    tool_calls = (
        db.query(DiagnosisToolCall)
        .filter(DiagnosisToolCall.case_uid == case.case_uid)
        .order_by(DiagnosisToolCall.step.asc(), DiagnosisToolCall.id.asc())
        .all()
    )
    skill_calls = (
        db.query(DiagnosisSkillCall)
        .filter(DiagnosisSkillCall.case_uid == case.case_uid)
        .order_by(DiagnosisSkillCall.step.asc(), DiagnosisSkillCall.id.asc())
        .all()
    )

    assistant_answer = (run.final_answer if run else None) or case.final_answer
    if not assistant_answer:
        return None

    return {
        "case_uid": case.case_uid,
        "run_uid": case.run_uid,
        "messages": [
            {
                "role": "user",
                "content": turn.content,
            },
            {
                "role": "assistant",
                "content": assistant_answer,
            },
        ],
        "metadata": {
            "trigger_source": case.trigger_source,
            "intent": case.intent,
            "time_window": case.time_window,
            "scope": case.scope,
            "candidate_causes": case.candidate_causes,
            "tool_calls": [
                {
                    "step": row.step,
                    "tool_name": row.tool_name,
                    "arguments": row.arguments,
                    "ok": row.ok,
                    "output_summary": row.output_summary,
                    "error": row.error,
                    "reason": row.reason,
                }
                for row in tool_calls
            ],
            "skill_calls": [
                {
                    "step": row.step,
                    "skill_name": row.skill_name,
                    "arguments": row.arguments,
                    "ok": row.ok,
                    "summary": row.summary,
                    "evidence": row.evidence,
                    "candidate_causes": row.candidate_causes,
                    "error": row.error,
                    "reason": row.reason,
                }
                for row in skill_calls
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export SFT training data to JSONL.")
    parser.add_argument("--output", required=True, help="Output JSONL path.")
    parser.add_argument("--case-uid", help="Only export one case.")
    parser.add_argument("--run-uid", help="Only export one run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        count = export_sft_jsonl(
            db,
            Path(args.output),
            case_uid=args.case_uid,
            run_uid=args.run_uid,
        )
    print(f"exported {count} SFT record(s) to {args.output}")


if __name__ == "__main__":
    main()

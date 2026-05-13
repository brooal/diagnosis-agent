from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.harness.models import DiagnosisCase, DiagnosisSkillCall, DiagnosisToolCall, HarnessTurn


def export_eval_cases(
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
            record = _build_eval_case(db, case)
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


def _build_eval_case(db: Session, case: DiagnosisCase) -> dict[str, Any]:
    turn = None
    if case.turn_uid:
        turn = db.query(HarnessTurn).filter(HarnessTurn.turn_uid == case.turn_uid).one_or_none()

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

    return {
        "case_uid": case.case_uid,
        "run_uid": case.run_uid,
        "input": {
            "user_query": turn.content if turn else None,
            "trigger_source": case.trigger_source,
            "intent": case.intent,
            "time_window": case.time_window,
            "scope": case.scope,
        },
        "expected": {
            "final_answer": case.final_answer,
            "candidate_causes": case.candidate_causes,
        },
        "references": {
            "tool_calls": [
                {
                    "step": row.step,
                    "tool_name": row.tool_name,
                    "arguments": row.arguments,
                    "ok": row.ok,
                    "output_summary": row.output_summary,
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
                    "candidate_causes": row.candidate_causes,
                }
                for row in skill_calls
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export evaluation cases to JSONL.")
    parser.add_argument("--output", required=True, help="Output JSONL path.")
    parser.add_argument("--case-uid", help="Only export one case.")
    parser.add_argument("--run-uid", help="Only export one run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        count = export_eval_cases(
            db,
            Path(args.output),
            case_uid=args.case_uid,
            run_uid=args.run_uid,
        )
    print(f"exported {count} eval case(s) to {args.output}")


if __name__ == "__main__":
    main()

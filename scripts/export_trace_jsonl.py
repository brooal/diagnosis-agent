from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.harness.models import DiagnosisCase, DiagnosisSkillCall, DiagnosisToolCall, HarnessItem


def export_trace_jsonl(
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
            record = _build_trace_record(db, case)
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


def _build_trace_record(db: Session, case: DiagnosisCase) -> dict[str, Any]:
    items = (
        db.query(HarnessItem)
        .filter(HarnessItem.case_uid == case.case_uid)
        .order_by(HarnessItem.seq.asc(), HarnessItem.id.asc())
        .all()
    )
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
        "trigger_source": case.trigger_source,
        "intent": case.intent,
        "status": case.status,
        "time_window": case.time_window,
        "scope": case.scope,
        "final_answer": case.final_answer,
        "candidate_causes": case.candidate_causes,
        "items": [
            {
                "seq": item.seq,
                "item_type": item.item_type,
                "content": item.content,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
        "tool_calls": [
            {
                "step": row.step,
                "tool_name": row.tool_name,
                "arguments": row.arguments,
                "ok": row.ok,
                "output_summary": row.output_summary,
                "error": row.error,
                "reason": row.reason,
                "created_at": row.created_at.isoformat(),
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
                "created_at": row.created_at.isoformat(),
            }
            for row in skill_calls
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export harness trace data to JSONL.")
    parser.add_argument("--output", required=True, help="Output JSONL path.")
    parser.add_argument("--case-uid", help="Only export one case.")
    parser.add_argument("--run-uid", help="Only export one run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        count = export_trace_jsonl(
            db,
            Path(args.output),
            case_uid=args.case_uid,
            run_uid=args.run_uid,
        )
    print(f"exported {count} case(s) to {args.output}")


if __name__ == "__main__":
    main()

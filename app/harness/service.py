# app/harness/service.py

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.harness.models import (
    HarnessThread,
    HarnessTurn,
    HarnessRun,
    HarnessItem,
    DiagnosisCase,
    DiagnosisToolCall,
    DiagnosisSkillCall,
    DiagnosisTraceEvent,
)


def new_uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class HarnessService:
    def __init__(self, db: Session):
        self.db = db

    def create_thread(self, title: str | None = None) -> str:
        thread_uid = new_uid("thread")
        row = HarnessThread(
            thread_uid=thread_uid,
            title=title,
            status="active",
        )
        self.db.add(row)
        self.db.commit()
        return thread_uid

    def create_turn(
        self,
        thread_uid: str,
        role: str,
        content: str,
    ) -> str:
        turn_uid = new_uid("turn")
        row = HarnessTurn(
            turn_uid=turn_uid,
            thread_uid=thread_uid,
            role=role,
            content=content,
        )
        self.db.add(row)
        self.db.commit()
        return turn_uid

    def create_case(
        self,
        *,
        thread_uid: str | None,
        turn_uid: str | None,
        trigger_source: str,
        intent: str | None,
        time_window: dict | None,
        scope: dict | None,
    ) -> str:
        case_uid = new_uid("case")
        row = DiagnosisCase(
            case_uid=case_uid,
            thread_uid=thread_uid,
            turn_uid=turn_uid,
            trigger_source=trigger_source,
            intent=intent,
            status="running",
            time_window=time_window,
            scope=scope,
        )
        self.db.add(row)
        self.db.commit()
        return case_uid

    def create_run(
        self,
        *,
        thread_uid: str,
        turn_uid: str,
        case_uid: str,
        trigger_source: str,
    ) -> str:
        run_uid = new_uid("run")
        row = HarnessRun(
            run_uid=run_uid,
            thread_uid=thread_uid,
            turn_uid=turn_uid,
            case_uid=case_uid,
            status="running",
            trigger_source=trigger_source,
        )
        self.db.add(row)

        case = self.db.query(DiagnosisCase).filter_by(case_uid=case_uid).one()
        case.run_uid = run_uid

        self.db.commit()
        return run_uid

    def add_item(
        self,
        *,
        run_uid: str,
        case_uid: str,
        item_type: str,
        content: dict,
        seq: int,
    ) -> None:
        row = HarnessItem(
            run_uid=run_uid,
            case_uid=case_uid,
            item_type=item_type,
            content=content,
            seq=seq,
        )
        self.db.add(row)
        self.db.commit()

    def add_trace_event(
        self,
        *,
        run_uid: str,
        case_uid: str,
        seq: int,
        event_type: str,
        payload: dict,
    ) -> None:
        row = DiagnosisTraceEvent(
            run_uid=run_uid,
            case_uid=case_uid,
            seq=seq,
            event_type=event_type,
            payload=payload,
        )
        self.db.add(row)
        self.db.commit()

    def add_tool_call(
        self,
        *,
        run_uid: str,
        case_uid: str,
        step: int,
        tool_name: str,
        arguments: dict,
        ok: bool,
        output_summary: str | None,
        error: str | None,
        reason: str | None,
    ) -> None:
        row = DiagnosisToolCall(
            run_uid=run_uid,
            case_uid=case_uid,
            step=step,
            tool_name=tool_name,
            arguments=arguments,
            ok=ok,
            output_summary=output_summary,
            error=error,
            reason=reason,
        )
        self.db.add(row)
        self.db.commit()

    def add_skill_call(
        self,
        *,
        run_uid: str,
        case_uid: str,
        step: int,
        skill_name: str,
        arguments: dict,
        ok: bool,
        summary: str | None,
        evidence: list | None,
        candidate_causes: list | None,
        error: str | None,
        reason: str | None,
    ) -> None:
        row = DiagnosisSkillCall(
            run_uid=run_uid,
            case_uid=case_uid,
            step=step,
            skill_name=skill_name,
            arguments=arguments,
            ok=ok,
            summary=summary,
            evidence=evidence,
            candidate_causes=candidate_causes,
            error=error,
            reason=reason,
        )
        self.db.add(row)
        self.db.commit()

    def complete_run(
        self,
        *,
        run_uid: str,
        case_uid: str,
        final_answer: str,
        candidate_causes: list,
    ) -> None:
        now = datetime.utcnow()

        run = self.db.query(HarnessRun).filter_by(run_uid=run_uid).one()
        run.status = "completed"
        run.finished_at = now
        run.final_answer = final_answer

        case = self.db.query(DiagnosisCase).filter_by(case_uid=case_uid).one()
        case.status = "completed"
        case.final_answer = final_answer
        case.candidate_causes = candidate_causes
        case.updated_at = now

        self.db.commit()

    def fail_run(
        self,
        *,
        run_uid: str,
        case_uid: str,
        error: str,
    ) -> None:
        now = datetime.utcnow()

        run = self.db.query(HarnessRun).filter_by(run_uid=run_uid).one()
        run.status = "failed"
        run.finished_at = now
        run.final_answer = error

        case = self.db.query(DiagnosisCase).filter_by(case_uid=case_uid).one()
        case.status = "failed"
        case.final_answer = error
        case.updated_at = now

        self.db.commit()
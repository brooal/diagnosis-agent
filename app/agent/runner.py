from  __future__ import annotations

import os

from app.agent.graph import build_diagnosis_graph
from app.agent.context_builder import build_runtime_context
from app.agent.state import DiagnosisState
from app.harness.service import HarnessService
from app.llm.client import LLMClient
from app.rag import build_rag_service
from app.skills import build_skill_registry
from app.tools import build_tool_registry
from sqlalchemy.orm import Session
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.tracing.db_recorder import DBTraceRecorder

class DiagnosisAgentRunner:
    def __init__(self, db: Session | None = None) ->None:
        if db is None:
            init_db()
            db = SessionLocal()
            self._owns_db = True
        else:
            self._owns_db = False
        self.db = db
        self.harness = HarnessService(db)
        self.recorder = DBTraceRecorder(self.harness)

        self.tools = build_tool_registry()
        self.skills = build_skill_registry()
        self.rag = build_rag_service()

        self.llm = LLMClient()

        self.graph = build_diagnosis_graph(
            tools = self.tools,
            skills = self.skills,
            recorder = self.recorder,
            harness = self.harness,
            llm = self.llm,
            rag = self.rag,
        )

    def close(self) -> None:
        if self._owns_db:
            self.db.close()

    def run_chat(
            self,
            *,
            user_query : str,
            time_window: dict,
            scope : dict | None = None,
            thread_uid : str | None = None,
            enable_rag: bool | None = None,
            rag_limit: int | None = None,
            rag_include_system_design: bool | None = None,
    ) -> DiagnosisState:
        scope = scope or {}
        if thread_uid is None:
            thread_uid = self.harness.create_thread(title = user_query[:80])

        turn_uid = self.harness.create_turn(
            thread_uid = thread_uid,
            role = "user",
            content = user_query,
        )
        case_id = self.harness.create_case(
            thread_uid = thread_uid,
            turn_uid = turn_uid,
            trigger_source = "chat",
            intent= None,
            time_window = time_window,
            scope = scope,
        )
        run_uid = self.harness.create_run(
            thread_uid = thread_uid,
            turn_uid = turn_uid,
            case_uid=case_id,
            trigger_source="chat",
        )
        initial_state : DiagnosisState = {
            "thread_uid" : thread_uid,
            "case_uid" : case_id,
            "turn_uid" : turn_uid,
            "run_uid" : run_uid,
            "trigger_source" : "chat",
            "time_window": time_window,
            "user_query": user_query,
            "scope": scope,
            "conversation_context": build_runtime_context(
                self.harness,
                thread_uid=thread_uid,
                current_turn_uid=turn_uid,
                max_turns=10,
            ),
            "enable_rag": _resolve_enable_rag(enable_rag, scope),
            "rag_limit": _resolve_rag_limit(rag_limit, scope),
            "rag_include_system_design": _resolve_rag_include_system_design(
                rag_include_system_design,
                scope,
            ),
            "max_steps" : 8
        }

        final_state = self.graph.invoke(initial_state)
        final_answer = final_state.get("final_answer")
        if final_answer:
            self.harness.create_turn(
                thread_uid=thread_uid,
                role="assistant",
                content=final_answer,
            )
        return final_state

    def run_auto(
            self,
            *,
            fault_type : str,
            time_window: dict,
            scope : dict | None = None,
            enable_rag: bool | None = None,
            rag_limit: int | None = None,
            rag_include_system_design: bool | None = None,
    ) -> DiagnosisState:
        scope = scope or {}
        thread_uid = self.harness.create_thread(title=f"自动诊断：{fault_type}")
        turn_uid = self.harness.create_turn(
            thread_uid = thread_uid,
            role = "auto",
            content = f"自动触发故障诊断:{fault_type}",
        )
        case_id = self.harness.create_case(
            thread_uid = thread_uid,
            turn_uid = turn_uid,
            trigger_source = "auto",
            intent = fault_type,
            time_window = time_window,
            scope = scope,
        )
        run_uid = self.harness.create_run(
            thread_uid = thread_uid,
            turn_uid = turn_uid,
            case_uid = case_id,
            trigger_source = "auto",
        )
        initial_state : DiagnosisState = {
            "thread_uid" : thread_uid,
            "case_uid" : case_id,
            "turn_uid" : turn_uid,
            "run_uid" : run_uid,
            "trigger_source" : "auto",
            "intent" : fault_type,
            "time_window": time_window,
            "user_query": f"自动触发故障诊断 ：{fault_type}",
            "scope": scope,
            "conversation_context": build_runtime_context(
                self.harness,
                thread_uid=thread_uid,
                current_turn_uid=turn_uid,
                max_turns=10,
            ),
            "enable_rag": _resolve_enable_rag(enable_rag, scope),
            "rag_limit": _resolve_rag_limit(rag_limit, scope),
            "rag_include_system_design": _resolve_rag_include_system_design(
                rag_include_system_design,
                scope,
            ),
            "max_steps" : 8
        }
        final_state = self.graph.invoke(initial_state)
        return final_state


def _resolve_enable_rag(value: bool | None, scope: dict) -> bool:
    if value is not None:
        return value
    if "enable_rag" in scope:
        return _as_bool(scope["enable_rag"], default=False)
    return _as_bool(os.getenv("AGENT_ENABLE_RAG"), default=False)


def _resolve_rag_limit(value: int | None, scope: dict) -> int:
    raw = value if value is not None else scope.get("rag_limit")
    if raw is None:
        raw = os.getenv("AGENT_RAG_LIMIT", "5")
    return int(raw)


def _resolve_rag_include_system_design(
    value: bool | None,
    scope: dict,
) -> bool:
    if value is not None:
        return value
    if "rag_include_system_design" in scope:
        return _as_bool(scope["rag_include_system_design"], default=False)
    if "include_system_design" in scope:
        return _as_bool(scope["include_system_design"], default=False)
    return _as_bool(os.getenv("AGENT_RAG_INCLUDE_SYSTEM_DESIGN"), default=False)


def _as_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default

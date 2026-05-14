from  __future__ import annotations

from app.agent.graph import build_diagnosis_graph
from app.agent.context_builder import build_runtime_context
from app.agent.state import DiagnosisState
from app.harness.service import HarnessService
from app.llm.client import LLMClient
from app.skills import build_skill_registry
from app.tools import build_tool_registry
from sqlalchemy.orm import Session
from app.tracing.db_recorder import DBTraceRecorder

class DiagnosisAgentRunner:
    def __init__(self, db: Session) ->None:
        self.db = db
        self.harness = HarnessService(db)
        self.recorder = DBTraceRecorder(self.harness)

        self.tools = build_tool_registry()
        self.skills = build_skill_registry()

        self.llm = LLMClient()

        self.graph = build_diagnosis_graph(
            tools = self.tools,
            skills = self.skills,
            recorder = self.recorder,
            harness = self.harness,
            llm = self.llm,
        )

    def run_chat(
            self,
            *,
            user_query : str,
            time_window: dict,
            scope : dict | None = None,
            thread_uid : str | None = None
    ) -> DiagnosisState:
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
            scope = scope or {},
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
            "scope": scope or {},
            "conversation_context": build_runtime_context(
                self.harness,
                thread_uid=thread_uid,
                current_turn_uid=turn_uid,
                max_turns=10,
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
    ) -> DiagnosisState:
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
            scope = scope or {},
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
            "scope": scope or {},
            "conversation_context": build_runtime_context(
                self.harness,
                thread_uid=thread_uid,
                current_turn_uid=turn_uid,
                max_turns=10,
            ),
            "max_steps" : 8
        }
        final_state = self.graph.invoke(initial_state)
        return final_state

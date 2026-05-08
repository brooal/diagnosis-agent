from  __future__ import annotations

from uuid import uuid4
from app.agent.graph import build_diagnosis_graph
from app.agent.state import DiagnosisState
from app.skills import build_skill_registry
from app.tools import build_tool_registry

from app.tracing.recorder import TraceRecorder

class DiagnosisAgentRunner:
    def __init__(self) ->None:
        self.tools = build_tool_registry()
        self.recorder = TraceRecorder()
        self.skills = build_skill_registry()
        self.graph = build_diagnosis_graph(
            tools = self.tools,
            skills = self.skills,
            recorder = self.recorder,
        )

    def run_chat(
            self,
            user_query : str,
            time_window: dict,
            scope : dict | None = None,
    ) -> DiagnosisState:
        case_id = f"case_{uuid4().hex[:12]}"

        initial_state : DiagnosisState = {
            "case_id": case_id,
            "trigger_source" : "chat",
            "time_window": time_window,
            "user_query": user_query,
            "scope": scope or {},
            "max_steps" : 8
        }

        final_state = self.graph.invoke(initial_state)
        return final_state

    def run_auto(
            self,
            fault_type : str,
            time_window: dict,
            scope : dict | None = None,
    ) -> DiagnosisState:
        case_id = f"case_{uuid4().hex[:12]}"
        initial_state : DiagnosisState = {
            "case_id": case_id,
            "trigger_source" : "auto",
            "intent" : fault_type,
            "time_window": time_window,
            "user_query": f"自动触发故障诊断 ：{fault_type}",
            "scope": scope or {},
            "max_steps" : 8
        }
        final_state = self.graph.invoke(initial_state)
        return final_state

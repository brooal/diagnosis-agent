from __future__ import annotations
from functools import partial

from langgraph.graph import StateGraph, END
from app.agent.state import DiagnosisState
from app.agent.nodes import (
    initialize_node,
    plan_node,
    act_node,
    should_continue,
    summarize_node
)
from app.skills.registry import SkillRegistry
from app.tools.registry import ToolRegistry
from app.tracing.recorder import TraceRecorder

def build_diagnosis_graph(
        tools : ToolRegistry,
        skills : SkillRegistry,
        recorder : TraceRecorder,
):
    graph = StateGraph(DiagnosisState)

    graph.add_node(
        "initialize",
        partial(initialize_node, recorder=recorder),
    )
    graph.add_node(
        "plan",
        partial(plan_node, recorder=recorder),
    )
    graph.add_node(
        "act",
        partial(act_node, tools = tools, skills = skills,recorder=recorder),
    )
    graph.add_node(
        "summarize",
        partial(summarize_node, recorder=recorder),
    )
    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "plan")
    graph.add_edge("plan", "act")
    graph.add_conditional_edges(
        "act",
        should_continue,
        {
            "act":"act",
            "summarize":"summarize",
        }
    )
    graph.add_edge("summarize", END)
    return graph.compile()


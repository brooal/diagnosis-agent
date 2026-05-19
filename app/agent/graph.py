from __future__ import annotations
from functools import partial

from langgraph.graph import StateGraph, END
from app.agent.state import DiagnosisState
from app.agent.nodes import (
    initialize_node,
    retrieve_rag_node,
    plan_node,
    act_node,
    route_after_plan,
    route_after_act,
    summarize_node,
    fail_node,
)
from app.llm.client import LLMClient
from app.harness.service import HarnessService
from app.rag.service import RagService
from app.skills.common import SkillRegistry
from app.tools.registry import ToolRegistry
from app.tracing.db_recorder import DBTraceRecorder


def build_diagnosis_graph(
    *,
    tools: ToolRegistry,
    skills: SkillRegistry,
    recorder: DBTraceRecorder,
    harness: HarnessService,
    llm: LLMClient,
    rag: RagService | None = None,
):
    graph = StateGraph(DiagnosisState)

    graph.add_node(
        "initialize",
        partial(initialize_node, recorder=recorder),
    )
    graph.add_node(
        "retrieve_rag",
        partial(
            retrieve_rag_node,
            rag=rag,
            recorder=recorder,
        ),
    )
    graph.add_node(
        "plan",
        partial(
            plan_node,
            llm=llm,
            tools=tools,
            skills=skills,
            recorder=recorder,
        ),
    )
    graph.add_node(
        "act",
        partial(
            act_node,
            tools=tools,
            skills=skills,
            recorder=recorder,
            harness=harness,
        ),
    )
    graph.add_node(
        "summarize",
        partial(
            summarize_node,
            llm=llm,
            harness=harness,
            recorder=recorder,
        ),
    )
    graph.add_node(
        "fail",
        partial(
            fail_node,
            recorder=recorder,
            harness=harness,
        )
    )
    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "retrieve_rag")
    graph.add_edge("retrieve_rag", "plan")
    graph.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "fail": "fail",
            "act": "act",
            "summarize": "summarize",
        },
    )
    graph.add_conditional_edges(
        "act",
        route_after_act,
        {
            "fail": "fail",
            "plan": "plan",
            "summarize": "summarize",
        },
    )
    graph.add_edge("summarize", END)
    graph.add_edge("fail", END)
    return graph.compile()

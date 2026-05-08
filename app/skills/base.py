
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.agent.state import DiagnosisState
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry

@dataclass
class SkillResult:
    ok : bool
    summary : str
    evidence : list[dict[str, Any]]
    candidate_causes : list[dict[str, Any]]
    output : dict[str, Any]
    error : str | None = None

class DiagnosisSkill(Protocol):
    name : str
    description : str
    parameters : dict[str, Any]

    def run(
            self,
            state : DiagnosisState,
            arguments : dict[str, Any],
            tools : ToolRegistry
        ) -> SkillResult:
        ...

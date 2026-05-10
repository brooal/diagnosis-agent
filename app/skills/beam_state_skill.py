from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.state import DiagnosisState
from app.skills.common import SkillContext, SkillResult, load_skill_descriptor
from app.skills.data.beam_state_diagnosis import BeamStateSkill as StandardBeamStateSkill
from app.tools.registry import ToolRegistry

_DESCRIPTOR = load_skill_descriptor(
    Path(__file__).parent / "data" / "beam_state_diagnosis" / "SKILL.md"
)


class BeamStateSkill:
    name = _DESCRIPTOR.name
    version = _DESCRIPTOR.version
    category = _DESCRIPTOR.category
    description = _DESCRIPTOR.description
    parameters = _DESCRIPTOR.parameters
    tags = _DESCRIPTOR.tags

    def __init__(self) -> None:
        self._impl = StandardBeamStateSkill()

    def run(
        self,
        state: DiagnosisState,
        arguments: dict[str, Any],
        tools: ToolRegistry,
    ) -> SkillResult:
        return self._impl.run(
            context=SkillContext(state=state, tools=tools),
            arguments=arguments,
        )


from  __future__ import annotations

from app.skills.base import DiagnosisSkill, SkillResult
from app.agent.state import DiagnosisState
from app.tools.registry import ToolRegistry

class SkillRegistry:

    def __init__(self):
        self._skills : dict[str, DiagnosisSkill] = {}

    def register(self, skill : DiagnosisSkill) -> None:
        if skill.name  in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name : str) -> DiagnosisSkill:
        if name not in self._skills:
            raise ValueError(f"Unknown skill: {name}")
        return self._skills[name]

    def list_spec(self) -> list[dict]:
        return [
            {
                "name" : skill.name,
                "description":skill.description,
                "parameters" : skill.parameters,
            }
            for skill in self._skills.values()
        ]

    def call(
            self,
            name:str,
            arguments: dict,
            state : DiagnosisState,
            tools : ToolRegistry
             ) -> SkillResult:
        skill = self.get(name)
        return skill.run(state = state, arguments = arguments, tools = tools)

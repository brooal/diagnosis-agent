from __future__ import annotations

from pathlib import Path

from app.skills.common import SkillRegistry


def build_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.discover(Path(__file__).parent)
    return registry


__all__ = ["SkillRegistry", "build_skill_registry"]

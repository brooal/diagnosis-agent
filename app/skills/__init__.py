
from app.skills.registry import SkillRegistry
from app.skills.beam_state_skill import BeamStateSkill
from app.skills.quadrupole_power_skill import  QuadrupolePowerSkill

def build_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(BeamStateSkill())
    registry.register(QuadrupolePowerSkill())

    return registry

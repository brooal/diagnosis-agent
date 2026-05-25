from app.skills import build_skill_registry


def test_builtin_skills_are_discovered() -> None:
    registry = build_skill_registry()
    names = {item["name"] for item in registry.list_spec()}

    assert "beam_state_diagnosis" in names
    assert "quadrupole_power_diagnosis" in names

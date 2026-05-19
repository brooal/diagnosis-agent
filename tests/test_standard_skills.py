from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.skills import build_skill_registry
from app.skills.common import SkillDescriptor, SkillRegistry, load_skill_descriptor
from app.tools.base import ToolResult


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append((name, arguments))

        if name == "diagnose_topoff_decay":
            return ToolResult(
                ok=True,
                summary="未找到 MODE=0 恒流中断事件，束流曲线未见明确 decay 或掉束特征。",
                output={
                    "event_count": 0,
                    "events": [],
                    "overall_status": "normal",
                },
            )

        if name == "diagnose_beam_fault":
            return ToolResult(
                ok=True,
                summary="Detected 1 beam fault event(s).",
                output={
                    "fault_present_in_window": True,
                    "fault_count": 1,
                    "faults": [{"fault_time": "2026-05-06T10:02:31+09:00"}],
                },
            )

        if name == "diagnose_power_faults":
            return ToolResult(
                ok=True,
                summary="Detected 1 candidate power fault event(s).",
                output={
                    "power_fault_count": 1,
                    "power_faults": [
                        {
                            "channel_name": "QF01:PS:CURRENT",
                            "fault_time": arguments["fault_time"],
                            "fault_type": "sharp_drop",
                            "evidence": "QF01 dropped near the beam fault.",
                        }
                    ],
                },
            )

        raise AssertionError(f"unexpected tool call: {name}")


def test_metadata_parser_reads_skill_md() -> None:
    descriptor = load_skill_descriptor(Path("app/skills/diagnosis/beam/state/SKILL.md"))

    assert descriptor.name == "beam_state_diagnosis"
    assert descriptor.version == "1.0.0"
    assert descriptor.category == "diagnosis"
    assert descriptor.domain == "beam"
    assert descriptor.stage == "phenomenon_detection"
    assert "beam_trip" in descriptor.symptoms
    assert "phenomena" in descriptor.produces
    assert descriptor.parameters["type"] == "object"
    assert "Beam State Diagnosis" in descriptor.docs


def test_registry_versions_category_and_search() -> None:
    registry = SkillRegistry()
    registry.register(
        SkillDescriptor(
            name="sample",
            version="1.0.0",
            category="diagnosis",
            domain="beam",
            stage="phenomenon_detection",
            description="old beam sample",
            entrypoint="tests.fake:Skill",
            parameters={"type": "object"},
            symptoms=["beam_trip"],
            produces=["phenomena"],
            tags=["beam"],
        )
    )
    registry.register(
        SkillDescriptor(
            name="sample",
            version="1.2.0",
            category="diagnosis",
            domain="beam",
            stage="phenomenon_detection",
            description="new beam sample",
            entrypoint="tests.fake:Skill",
            parameters={"type": "object"},
            symptoms=["beam_decay"],
            produces=["phenomena"],
            tags=["beam"],
        )
    )

    assert registry.get_descriptor("sample").version == "1.2.0"
    spec = registry.list_spec(category="diagnosis", include_versions=True)[0]
    assert spec["version"] == "1.2.0"
    assert spec["domain"] == "beam"
    assert spec["stage"] == "phenomenon_detection"
    assert registry.search("beam_decay")[0]["name"] == "sample"


def test_plugin_discovery_is_lazy(tmp_path: Path) -> None:
    marker = tmp_path / "imported.txt"
    skill_dir = tmp_path / "plugin_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: plugin_skill
version: 1.0.0
category: utils
description: Test plugin skill
entrypoint: skill:PluginSkill
tags:
  - plugin
parameters:
  {"type": "object", "properties": {}, "required": []}
---

# Plugin Skill
""",
        encoding="utf-8",
    )
    (skill_dir / "skill.py").write_text(
        f"""from app.skills.common import SkillResult
open({str(marker)!r}, "w").write("imported")

class PluginSkill:
    def run(self, context, arguments):
        return SkillResult(ok=True, summary="ok", evidence=[], candidate_causes=[], output={{}})
""",
        encoding="utf-8",
    )

    registry = SkillRegistry()
    registry.load_plugin(tmp_path)

    assert not marker.exists()
    result = registry.call("plugin_skill", {}, state={}, tools=FakeTools())
    assert result.ok
    assert marker.exists()


def test_standard_skill_registry_discovers_builtin_skills() -> None:
    registry = build_skill_registry()
    specs = registry.list_spec(include_versions=True)

    names = {spec["name"] for spec in specs}
    assert {"beam_state_diagnosis", "quadrupole_power_diagnosis", "decay_cause_analysis"} <= names
    beam_spec = next(spec for spec in specs if spec["name"] == "beam_state_diagnosis")
    assert beam_spec["category"] == "diagnosis"
    assert beam_spec["domain"] == "beam"
    assert beam_spec["stage"] == "phenomenon_detection"


def test_beam_skill_calls_real_diagnosis_tool() -> None:
    registry = build_skill_registry()
    tools = FakeTools()

    result = registry.call(
        "beam_state_diagnosis",
        {
            "start": "2026-05-06T10:00:00+09:00",
            "end": "2026-05-06T10:05:00+09:00",
            "beam_current_pv": "RING:BEAM:CURRENT",
        },
        state={},
        tools=tools,
    )

    assert result.ok
    assert result.output["phenomena"][0]["type"] == "beam_trip"
    assert result.output["recommended_next_skills"][0]["name"] == "quadrupole_power_diagnosis"
    assert result.candidate_causes[0]["drop_time"] == "2026-05-06T10:02:31+09:00"
    assert tools.calls[0] == (
        "diagnose_topoff_decay",
        {
            "start": "2026-05-06T10:00:00+09:00",
            "end": "2026-05-06T10:05:00+09:00",
            "beam_channel": "RING:BEAM:CURRENT",
        },
    )
    assert tools.calls[1] == (
        "diagnose_beam_fault",
        {
            "start": "2026-05-06T10:00:00+09:00",
            "end": "2026-05-06T10:05:00+09:00",
            "beam_channel": "RING:BEAM:CURRENT",
        },
    )


def test_quadrupole_skill_calls_power_tool_and_handles_missing_fault_time() -> None:
    registry = build_skill_registry()
    tools = FakeTools()

    missing = registry.call(
        "quadrupole_power_diagnosis",
        {"power_pattern": "Q*:PS:*"},
        state={},
        tools=tools,
    )
    assert not missing.ok
    assert missing.error == "missing_fault_time"

    result = registry.call(
        "quadrupole_power_diagnosis",
        {"power_pattern": "Q*:PS:*", "window_seconds": 10},
        state={
            "candidate_causes": [
                {"cause_type": "beam_trip", "drop_time": "2026-05-06T10:02:31+09:00"}
            ]
        },
        tools=tools,
    )

    assert result.ok
    assert result.candidate_causes[0]["device"] == "QF01:PS:CURRENT"
    assert tools.calls[-1] == (
        "diagnose_power_faults",
        {
            "fault_time": "2026-05-06T10:02:31+09:00",
            "window_seconds": 10,
            "power_pattern": "Q*:PS:*",
        },
    )

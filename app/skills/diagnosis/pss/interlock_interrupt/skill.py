from __future__ import annotations

from typing import Any

from app.skills.common import SkillContext, SkillResult


class PssInterlockInterruptDiagnosisSkill:
    def run(self, context: SkillContext, arguments: dict[str, Any]) -> SkillResult:
        result = context.tools.call("diagnose_pss_interlock_interrupt", arguments)
        if not result.ok:
            return SkillResult(
                ok=False,
                summary=result.summary,
                evidence=[],
                candidate_causes=[],
                output={},
                error=result.error,
            )

        output = result.output if isinstance(result.output, dict) else {}
        evidence = [
            {
                "type": "pss_interlock_interrupt_diagnosis",
                "event_found": output.get("event_found"),
                "event_time": output.get("event_time"),
                "state_transition": output.get("trigger"),
                "primary_cause": output.get("primary_cause"),
                "candidates": output.get("candidates", []),
                "auxiliary_events": output.get("companion_events", []),
                "events": output.get("events", []),
            }
        ]
        candidate_causes = []
        primary = output.get("primary_cause")
        if isinstance(primary, dict):
            candidate_causes.append(
                {
                    "cause_type": primary.get("cause_type"),
                    "description": primary.get("description"),
                    "confidence": primary.get("confidence"),
                    "pv": primary.get("pv"),
                    "value": primary.get("value"),
                    "time": primary.get("time"),
                    "offset_seconds": primary.get("offset_seconds"),
                    "subsystem": primary.get("subsystem"),
                }
            )

        return SkillResult(
            ok=True,
            summary=result.summary,
            evidence=evidence,
            candidate_causes=candidate_causes,
            output={
                "event_found": output.get("event_found", False),
                "event_type": output.get("event_type", "pss_interlock_to_unlock"),
                "event_time": output.get("event_time"),
                "primary_cause": primary,
                "candidates": output.get("candidates", []),
                "auxiliary_events": output.get("companion_events", []),
                "events": output.get("events", []),
                "tool": "diagnose_pss_interlock_interrupt",
                "tool_arguments": arguments,
                "tool_output": output,
            },
        )

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.context_builder import build_runtime_context


class FakeHarness:
    def __init__(self, turns: list[SimpleNamespace]) -> None:
        self.turns = turns
        self.calls: list[dict] = []

    def get_recent_turns(
        self,
        *,
        thread_uid: str,
        limit: int = 10,
        exclude_turn_uid: str | None = None,
    ) -> list[SimpleNamespace]:
        self.calls.append(
            {
                "thread_uid": thread_uid,
                "limit": limit,
                "exclude_turn_uid": exclude_turn_uid,
            }
        )
        filtered = [turn for turn in self.turns if turn.turn_uid != exclude_turn_uid]
        return filtered[-limit:]


def test_build_runtime_context_uses_recent_turns() -> None:
    turns = [
        SimpleNamespace(
            turn_uid=f"turn_{index}",
            role="user" if index % 2 == 0 else "assistant",
            content=f"message_{index}",
            created_at=SimpleNamespace(isoformat=lambda index=index: f"2026-05-13T00:00:{index:02d}"),
        )
        for index in range(12)
    ]
    harness = FakeHarness(turns)

    context = build_runtime_context(
        harness,
        thread_uid="thread_1",
        current_turn_uid="turn_11",
        max_turns=10,
    )

    assert harness.calls == [
        {
            "thread_uid": "thread_1",
            "limit": 10,
            "exclude_turn_uid": "turn_11",
        }
    ]
    assert len(context["recent_turns"]) == 10
    assert context["recent_turns"][-1]["turn_uid"] == "turn_10"
    assert all(turn["turn_uid"] != "turn_11" for turn in context["recent_turns"])

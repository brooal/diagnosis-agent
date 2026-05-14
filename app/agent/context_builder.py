from __future__ import annotations

from typing import Any

from app.harness.service import HarnessService


def build_runtime_context(
    harness: HarnessService,
    *,
    thread_uid: str,
    current_turn_uid: str | None = None,
    max_turns: int = 10,
) -> dict[str, Any]:
    recent_turns = harness.get_recent_turns(
        thread_uid=thread_uid,
        limit=max_turns,
        exclude_turn_uid=current_turn_uid,
    )
    return {
        "recent_turns": [
            {
                "turn_uid": turn.turn_uid,
                "role": turn.role,
                "content": turn.content,
                "created_at": turn.created_at.isoformat(),
            }
            for turn in recent_turns
        ]
    }

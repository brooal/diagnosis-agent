from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tracing.db_recorder import DBTraceRecorder


class FakeHarness:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.trace_events: list[dict] = []

    def add_item(
        self,
        *,
        run_uid: str,
        case_uid: str,
        item_type: str,
        content: dict,
        seq: int,
    ) -> None:
        self.items.append(
            {
                "run_uid": run_uid,
                "case_uid": case_uid,
                "item_type": item_type,
                "content": content,
                "seq": seq,
            }
        )

    def add_trace_event(self, **kwargs) -> None:
        self.trace_events.append(kwargs)


def test_db_trace_recorder_only_writes_harness_items() -> None:
    harness = FakeHarness()
    recorder = DBTraceRecorder(harness)

    recorder.append(
        run_uid="run_1",
        case_uid="case_1",
        event_type="react_action_planned",
        payload={"step": 1},
    )

    assert harness.items == [
        {
            "run_uid": "run_1",
            "case_uid": "case_1",
            "item_type": "react_action_planned",
            "content": {"step": 1},
            "seq": 1,
        }
    ]
    assert harness.trace_events == []

# app/tracing/db_recorder.py

from __future__ import annotations

from app.harness.service import HarnessService


class DBTraceRecorder:
    def __init__(self, harness: HarnessService):
        self.harness = harness
        self._seq_map: dict[str, int] = {}

    def next_seq(self, run_uid: str) -> int:
        current = self._seq_map.get(run_uid, 0) + 1
        self._seq_map[run_uid] = current
        return current

    def append(
        self,
        *,
        run_uid: str,
        case_uid: str,
        event_type: str,
        payload: dict,
    ) -> None:
        seq = self.next_seq(run_uid)

        self.harness.add_item(
            run_uid=run_uid,
            case_uid=case_uid,
            item_type=event_type,
            content=payload,
            seq=seq,
        )

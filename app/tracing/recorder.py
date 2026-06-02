from __future__ import annotations

import json
from typing import Any
from pathlib import Path

from app.utils.json import make_json_safe
from app.utils.times import now_shanghai

class TraceRecorder:

    def __init__(self, trace_dir : str = "traces") -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents= True, exist_ok = True)

    def create_trace_id(self, case_id : str) -> str:
        return f"{case_id}_{now_shanghai().strftime('%Y%m%d_%H%M%S')}"


    def append(
            self,
            trace_id : str,
            case_id : str,
            event_type : str,
            payload: dict[str, Any]
    ) -> None:
        path = self.trace_dir / f"{trace_id}.jsonl"

        record = {
            "time" : now_shanghai().isoformat(timespec = "seconds"),
            "case_id" : case_id,
            "event_type" : event_type,
            "payload" : payload,
        }
        with path.open("w", encoding = "utf-8") as f:
            f.write(json.dumps(make_json_safe(record), ensure_ascii=False) + "\n")


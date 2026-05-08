from __future__ import annotations

import json
from typing import Any
from pathlib import Path
from datetime import datetime

class TraceRecorder:

    def __init__(self, trace_dir : str = "traces") -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents= True, exist_ok = True)

    def create_trace_id(self, case_id : str) -> str:
        return f"{case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


    def append(
            self,
            trace_id : str,
            case_id : str,
            event_type : str,
            payload: dict[str, Any]
    ) -> None:
        path = self.trace_dir / f"{trace_id}.jsonl"

        record = {
            "time" : datetime.now().isoformat(timespec = "seconds"),
            "case_id" : case_id,
            "event_type" : event_type,
            "payload" : payload,
        }
        with path.open("w", encoding = "utf-8") as f:
            f.write(json.dumps(record,ensure_ascii = False) + "\n")




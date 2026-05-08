from  __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass
class TraceEvent:
    case_id : str
    event_type : str
    payload : list[dict[str, Any]]


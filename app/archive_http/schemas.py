from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArchiveHttpRow:
    pv: str
    timestamp: str
    smpl_time: str
    nanosecs: int
    value: Any
    float_val: float | None
    num_val: int | None
    str_val: str | None
    sample_type: str | None

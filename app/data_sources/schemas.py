# PV Sample等数据结构
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen = True)
class PVSample:
    channel_name: str
    smpl_time : str
    nanosecs : int
    float_val : float

@dataclass(frozen = True)
class QueryResult:
    columns: list[str]
    rows : list[dict]
    row_count : int
    truncated : bool
    max_rows : int


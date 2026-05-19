# PV Sample等数据结构
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen = True)
class PVSample:
    channel_name: str
    smpl_time : str
    nanosecs : int
    float_val : float


@dataclass(frozen=True)
class PVRawSample:
    channel_id: int
    channel_name: str | None
    smpl_time: str
    nanosecs: int
    num_val: int | None
    severity_id: int | None = None
    status_id: int | None = None

@dataclass(frozen = True)
class QueryResult:
    columns: list[str]
    rows : list[dict]
    row_count : int
    truncated : bool
    max_rows : int

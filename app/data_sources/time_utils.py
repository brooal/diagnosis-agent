# 时间格式处理

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

PLAIN_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

def parse_time_arg(value : str, default_offset : str = "+08:00") -> str:
    """
    支持
    1. 2026-05-06 10：00：00
    2. 2026-05-06T10：00：00
    3. 2026—05-06T02：00：00Z
    """
    value = value.strip()

    if PLAIN_RE.match(value):
        return value.replace(" ", "T") + default_offset

    if ISO_RE.match(value):
        return value

    raise ValueError("不合法的时间格式，使用'YYYY-MM-DD HH:MM:SS'.")
def parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)

def format_shanghai_datetime(dt: datetime) -> str:
    tz = timezone(timedelta(hours=8))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    shifted = dt.astimezone(tz)
    return shifted.isoformat(timespec="seconds")

def add_seconds(value : str, seconds : int ) -> str:
    dt = parse_iso_datetime(parse_time_arg(value))
    return format_shanghai_datetime(dt + timedelta(seconds=seconds))


def build_center_window(center_time : str, windows_seconds : int) -> tuple[str, str]:
    center = parse_iso_datetime(parse_time_arg(center_time))
    start = center - timedelta(seconds=windows_seconds)
    end = center + timedelta(seconds=windows_seconds)
    return format_shanghai_datetime(start), format_shanghai_datetime(end)




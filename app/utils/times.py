from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def now_shanghai_aware() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def now_shanghai() -> datetime:
    return now_shanghai_aware().replace(tzinfo=None)

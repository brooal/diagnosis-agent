from __future__ import annotations

from datetime import datetime, timedelta, timezone

SHANGHAI_TZ = timezone(timedelta(hours=8))


def parse_user_time(value: str) -> datetime:
    text = value.strip().replace("T", " ")
    if text.endswith("Z"):
        return datetime.fromisoformat(text.replace(" ", "T").replace("Z", "+00:00")).astimezone(SHANGHAI_TZ)
    if "+" in text[10:] or text[10:].count("-") > 0:
        return datetime.fromisoformat(text.replace(" ", "T")).astimezone(SHANGHAI_TZ)
    return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI_TZ)


def format_api_time(value: datetime | str) -> str:
    dt = parse_user_time(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SHANGHAI_TZ)
    return dt.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def format_iso_shanghai(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ).isoformat(timespec="seconds")


def timestamp_to_ms(timestamp: str | int) -> int:
    text = str(timestamp)
    if len(text) >= 16:
        return int(int(text) // 1_000_000)
    return int(text)


def timestamp_to_nanosecs(timestamp: str | int) -> int:
    text = str(timestamp)
    if len(text) >= 16:
        return int(int(text) % 1_000_000_000)
    return 0


def timestamp_to_iso(timestamp: str | int) -> str:
    ms = timestamp_to_ms(timestamp)
    return format_iso_shanghai(datetime.fromtimestamp(ms / 1000, tz=timezone.utc))


def split_time_range(start: str, end: str, *, chunk_seconds: int) -> list[tuple[str, str]]:
    start_dt = parse_user_time(start)
    end_dt = parse_user_time(end)
    if end_dt < start_dt:
        raise ValueError("end_time must be greater than or equal to start_time")
    if end_dt == start_dt:
        return [(format_api_time(start_dt), format_api_time(end_dt))]

    chunks: list[tuple[str, str]] = []
    current = start_dt
    while current < end_dt:
        next_dt = min(current + timedelta(seconds=chunk_seconds), end_dt)
        chunks.append((format_api_time(current), format_api_time(next_dt)))
        current = next_dt
    return chunks

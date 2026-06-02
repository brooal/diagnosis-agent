from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.archive_http.config import ArchiveHttpConfig
from app.archive_http.repository import ArchiveHttpRepository
from app.archive_http.schemas import ArchiveHttpRow
from app.archive_http.time_utils import split_time_range


class FakeArchiveClient:
    def __init__(self) -> None:
        self.range_calls: list[tuple[str, str, str]] = []

    def fetch_pv_range(self, pv: str, start: str, end: str, *, agg: str = "avg") -> list[ArchiveHttpRow]:
        if pv == "RNG:BEAM:CURR" and start == "2026-05-28 10:00:00" and end == "2026-05-28 13:05:00":
            self.range_calls.append((pv, "2026-05-28 10:00:00", "2026-05-28 12:58:00"))
            self.range_calls.append((pv, "2026-05-28 12:58:00", "2026-05-28 13:05:00"))
            return [
                _row("RNG:BEAM:CURR", "2026-05-28T10:00:00+08:00", 500.0),
                _row("RNG:BEAM:CURR", "2026-05-28T10:00:01+08:00", 499.5),
                _row("RNG:BEAM:CURR", "2026-05-28T13:00:00+08:00", 498.0),
            ]
        self.range_calls.append((pv, start, end))
        rows = {
            ("RNG:BEAM:CURR", "2026-05-28 10:00:00", "2026-05-28 12:58:00"): [
                _row("RNG:BEAM:CURR", "2026-05-28T10:00:00+08:00", 500.0),
                _row("RNG:BEAM:CURR", "2026-05-28T10:00:01+08:00", 499.5),
            ],
            ("RNG:BEAM:CURR", "2026-05-28 12:58:00", "2026-05-28 13:05:00"): [
                _row("RNG:BEAM:CURR", "2026-05-28T13:00:00+08:00", 498.0),
            ],
            ("RNG:OPERATION:MODE:bo", "2026-05-28 10:00:00", "2026-05-28 10:00:30"): [
                _row("RNG:OPERATION:MODE:bo", "2026-05-28T10:00:03+08:00", 0, num_val=0),
                _row("RNG:OPERATION:MODE:bo", "2026-05-28T10:00:20+08:00", 1, num_val=1),
            ],
            ("SR_PS_QM23:current:ai", "2026-05-28 10:00:00", "2026-05-28 10:00:30"): [
                _row("SR_PS_QM23:current:ai", "2026-05-28T10:00:01+08:00", 12.5),
            ],
        }
        return rows.get((pv, start, end), [])

    def fetch_pv_names(self, keyword: str) -> list[dict]:
        if keyword in {"SR_PS_", "SR_PS_QM"}:
            return [
                {"name": "SR_PS_QM23:current:ai"},
                {"name": "SR_PS_QM24:voltage:ai"},
                {"name": "SR_PS_BM:current:ai"},
            ]
        return []


def test_split_time_range_uses_safe_under_three_hour_chunks() -> None:
    chunks = split_time_range(
        "2026-05-28 10:00:00",
        "2026-05-28 15:00:00",
        chunk_seconds=2 * 60 * 60 + 58 * 60,
    )

    assert chunks == [
        ("2026-05-28 10:00:00", "2026-05-28 12:58:00"),
        ("2026-05-28 12:58:00", "2026-05-28 15:00:00"),
    ]


def test_fetch_channel_samples_splits_deduplicates_and_sorts() -> None:
    client = FakeArchiveClient()
    repo = _repo(client)

    rows = repo.fetch_channel_samples(
        "RNG:BEAM:CURR",
        "2026-05-28 10:00:00",
        "2026-05-28 13:05:00",
    )

    assert [row.float_val for row in rows] == [500.0, 499.5, 498.0]
    assert rows[0].smpl_time == "2026-05-28T10:00:00+08:00"
    assert client.range_calls == [
        ("RNG:BEAM:CURR", "2026-05-28 10:00:00", "2026-05-28 12:58:00"),
        ("RNG:BEAM:CURR", "2026-05-28 12:58:00", "2026-05-28 13:05:00"),
    ]


def test_fetch_sample_channel_samples_uses_channel_mapping() -> None:
    repo = _repo(FakeArchiveClient())

    rows = repo.fetch_sample_channel_samples(
        617,
        "2026-05-28 10:00:00",
        "2026-05-28 13:05:00",
    )

    assert rows
    assert {row.channel_name for row in rows} == {"RNG:BEAM:CURR"}


def test_fetch_raw_pv_samples_keeps_num_values() -> None:
    repo = _repo(FakeArchiveClient())

    rows = repo.fetch_raw_pv_samples(
        ["RNG:OPERATION:MODE:bo"],
        "2026-05-28 10:00:00",
        "2026-05-28 10:00:30",
    )

    assert [row.num_val for row in rows] == [0, 1]
    assert rows[0].channel_name == "RNG:OPERATION:MODE:bo"
    assert rows[0].channel_id == 2418


def test_fetch_pattern_samples_discovers_matching_pvs() -> None:
    repo = _repo(FakeArchiveClient())

    rows = repo.fetch_pattern_samples(
        "%SR_PS_QM%:current:ai",
        "2026-05-28 10:00:00",
        "2026-05-28 10:00:30",
    )

    assert len(rows) == 1
    assert rows[0].channel_name == "SR_PS_QM23:current:ai"
    assert rows[0].float_val == 12.5


def _repo(client: FakeArchiveClient) -> ArchiveHttpRepository:
    config = ArchiveHttpConfig(chunk_seconds=2 * 60 * 60 + 58 * 60)
    return ArchiveHttpRepository(config=config, client=client)  # type: ignore[arg-type]


def _ns(value: str) -> str:
    dt = datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Shanghai"))
    return str(int(dt.timestamp() * 1_000_000_000))


def _row(pv: str, time_value: str, value: float | int, *, num_val: int | None = None) -> ArchiveHttpRow:
    timestamp = _ns(time_value)
    return ArchiveHttpRow(
        pv=pv,
        timestamp=timestamp,
        smpl_time=time_value,
        nanosecs=int(timestamp) % 1_000_000_000,
        value=value,
        float_val=float(value) if num_val is None else None,
        num_val=num_val,
        str_val=None,
        sample_type="raw",
    )

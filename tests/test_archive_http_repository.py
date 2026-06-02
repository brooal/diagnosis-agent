from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.archive_http.config import ArchiveHttpConfig
from app.archive_http.errors import ArchiveHttpDataError
from app.archive_http.repository import HttpArchiveRepository
from app.archive_http.schemas import ArchiveHttpRow
from app.archive_http.time_utils import split_time_range, timestamp_to_iso, timestamp_to_nanosecs


class FakeClient:
    def __init__(self) -> None:
        self.names = [
            {"name": "SR_PS_QM23:current:ai"},
            {"name": "SR_PS_QM24:current:ai"},
            {"name": "SR_PS_BM:current:ai"},
        ]

    def fetch_pv_range(self, pv: str, start: str, end: str, *, agg: str = "avg") -> list[ArchiveHttpRow]:
        return [
            ArchiveHttpRow(
                pv=pv,
                timestamp="1780036052624736403",
                smpl_time="2026-05-28T10:00:52+08:00",
                nanosecs=624736403,
                value=498.91302,
                float_val=498.91302,
                num_val=None,
                str_val=None,
                sample_type="raw",
            ),
            ArchiveHttpRow(
                pv=pv,
                timestamp="1780036053624859368",
                smpl_time="2026-05-28T10:00:53+08:00",
                nanosecs=624859368,
                value=498.89642,
                float_val=498.89642,
                num_val=None,
                str_val=None,
                sample_type="raw",
            ),
        ]

    def fetch_pv_names(self, keyword: str) -> list[dict]:
        return self.names


def test_split_time_range_uses_shorter_than_three_hour_chunks() -> None:
    chunks = split_time_range(
        "2026-05-28 10:00:00",
        "2026-05-28 15:00:00",
        chunk_seconds=(3 * 60 * 60) - (2 * 60),
    )

    assert len(chunks) == 2
    assert chunks[0] == ("2026-05-28 10:00:00", "2026-05-28 12:58:00")
    assert chunks[1] == ("2026-05-28 12:58:00", "2026-05-28 15:00:00")


def test_timestamp_supports_raw_nanoseconds_and_minute_avg_milliseconds() -> None:
    assert timestamp_to_nanosecs("1780036052624736403") == 624736403
    assert timestamp_to_nanosecs("1779957540000") == 0
    assert timestamp_to_iso("1780036052624736403").endswith("+08:00")
    assert timestamp_to_iso("1779957540000").endswith("+08:00")


def test_http_repository_converts_beam_channel_id_to_samples() -> None:
    repo = HttpArchiveRepository(
        client=FakeClient(),
        config=ArchiveHttpConfig(require_raw_samples=True),
        channel_id_map={617: "RNG:BEAM:CURR"},
    )

    samples = repo.fetch_sample_channel_samples(
        617,
        "2026-05-28 10:00:00",
        "2026-05-28 10:01:00",
    )

    assert len(samples) == 2
    assert samples[0].channel_name == "RNG:BEAM:CURR"
    assert samples[0].float_val == pytest.approx(498.91302)


def test_http_repository_discovers_pattern_pvs() -> None:
    repo = HttpArchiveRepository(
        client=FakeClient(),
        config=ArchiveHttpConfig(max_pattern_pvs=10),
    )

    names = repo.discover_pv_names("%SR_PS_QM%:current:ai")

    assert names == ["SR_PS_QM23:current:ai", "SR_PS_QM24:current:ai"]


def test_http_repository_rejects_minute_avg_for_diagnosis_when_strict() -> None:
    class AggregatedClient(FakeClient):
        def fetch_pv_range(self, pv: str, start: str, end: str, *, agg: str = "avg") -> list[ArchiveHttpRow]:
            row = super().fetch_pv_range(pv, start, end, agg=agg)[0]
            return [
                ArchiveHttpRow(
                    pv=row.pv,
                    timestamp="1779957540000",
                    smpl_time=row.smpl_time,
                    nanosecs=0,
                    value=row.value,
                    float_val=row.float_val,
                    num_val=row.num_val,
                    str_val=row.str_val,
                    sample_type="minute-avg",
                )
            ]

    repo = HttpArchiveRepository(
        client=AggregatedClient(),
        config=ArchiveHttpConfig(require_raw_samples=True),
        channel_id_map={617: "RNG:BEAM:CURR"},
    )

    with pytest.raises(ArchiveHttpDataError):
        repo.fetch_sample_channel_samples(617, "2026-05-28 10:00:00", "2026-05-28 10:01:00")

from __future__ import annotations

from typing import Protocol

from app.data_sources.schemas import PVRawSample, PVSample


class ArchiveRepository(Protocol):
    def fetch_channel_samples(
        self,
        channel_name: str,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVSample]: ...

    def fetch_sample_channel_samples(
        self,
        channel_id: int,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVSample]: ...

    def fetch_pattern_samples(
        self,
        pattern: str,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVSample]: ...

    def fetch_raw_channel_samples(
        self,
        channel_ids: list[int],
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVRawSample]: ...

    def fetch_raw_pv_samples(
        self,
        pv_names: list[str],
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVRawSample]: ...

    def fetch_latest_raw_sample_before(
        self,
        channel_id: int,
        before_time: str,
    ) -> PVRawSample | None: ...

    def fetch_next_raw_sample_after(
        self,
        channel_id: int,
        after_time: str,
        *,
        expected_value: int | None = None,
        end_time: str | None = None,
    ) -> PVRawSample | None: ...

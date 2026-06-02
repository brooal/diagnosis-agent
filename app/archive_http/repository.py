from __future__ import annotations

from datetime import timedelta

from app.archive_http.client import ArchiveHttpClient
from app.archive_http.config import ArchiveHttpConfig
from app.archive_http.errors import ArchiveHttpDataError
from app.archive_http.pv_name_resolver import (
    default_channel_id_map,
    matches_sql_like,
    name_from_item,
)
from app.archive_http.schemas import ArchiveHttpRow
from app.archive_http.time_utils import format_iso_shanghai, parse_user_time
from app.data_sources.schemas import PVRawSample, PVSample


class HttpArchiveRepository:
    def __init__(
        self,
        client: ArchiveHttpClient | None = None,
        config: ArchiveHttpConfig | None = None,
        channel_id_map: dict[int, str] | None = None,
    ) -> None:
        self.config = config or ArchiveHttpConfig.from_env()
        self.client = client or ArchiveHttpClient(self.config)
        self.channel_id_map = channel_id_map or default_channel_id_map()

    def fetch_channel_samples(
        self,
        channel_name: str,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVSample]:
        rows = self.client.fetch_pv_range(channel_name, start_time, end_time, agg="avg")
        self._assert_raw(rows)
        samples = [
            PVSample(
                channel_name=row.pv,
                smpl_time=row.smpl_time,
                nanosecs=row.nanosecs,
                float_val=float(row.value),
            )
            for row in rows
            if row.value is not None
        ]
        return _limit(samples, limit or self.config.max_points)

    def fetch_sample_channel_samples(
        self,
        channel_id: int,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVSample]:
        return self.fetch_channel_samples(
            self._pv_for_channel_id(channel_id),
            start_time,
            end_time,
            limit=limit,
        )

    def fetch_pattern_samples(
        self,
        pattern: str,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVSample]:
        names = self.discover_pv_names(pattern)
        samples: list[PVSample] = []
        max_points = limit or self.config.max_points
        for name in names:
            samples.extend(
                self.fetch_channel_samples(
                    name,
                    start_time,
                    end_time,
                    limit=max_points,
                )
            )
            if len(samples) >= max_points:
                break
        return samples[:max_points]

    def fetch_raw_channel_samples(
        self,
        channel_ids: list[int],
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVRawSample]:
        pv_names = [self._pv_for_channel_id(channel_id) for channel_id in channel_ids]
        return self.fetch_raw_pv_samples(pv_names, start_time, end_time, limit=limit)

    def fetch_raw_pv_samples(
        self,
        pv_names: list[str],
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVRawSample]:
        samples: list[PVRawSample] = []
        max_points = limit or self.config.max_points
        for pv in pv_names:
            rows = self.client.fetch_pv_range(pv, start_time, end_time, agg="avg")
            self._assert_raw(rows)
            channel_id = self._channel_id_for_pv(pv)
            samples.extend(_raw_samples_from_rows(rows, channel_id=channel_id))
            if len(samples) >= max_points:
                break
        return samples[:max_points]

    def fetch_latest_raw_sample_before(
        self,
        channel_id: int,
        before_time: str,
    ) -> PVRawSample | None:
        before = parse_user_time(before_time)
        start = format_iso_shanghai(before - timedelta(seconds=self.config.lookaround_seconds))
        rows = self.fetch_raw_channel_samples([channel_id], start, before_time)
        return rows[-1] if rows else None

    def fetch_next_raw_sample_after(
        self,
        channel_id: int,
        after_time: str,
        *,
        expected_value: int | None = None,
        end_time: str | None = None,
    ) -> PVRawSample | None:
        after = parse_user_time(after_time)
        end = end_time or format_iso_shanghai(after + timedelta(seconds=self.config.lookaround_seconds))
        rows = self.fetch_raw_channel_samples([channel_id], after_time, end)
        for row in rows:
            if expected_value is None or row.num_val == expected_value:
                return row
        return None

    def discover_pv_names(self, pattern: str) -> list[str]:
        if "%" not in pattern and "_" not in pattern:
            return [pattern]

        names: set[str] = set()
        for prefix in self.config.power_discovery_prefixes:
            for item in self.client.fetch_pv_names(prefix):
                name = name_from_item(item)
                if name and matches_sql_like(name, pattern):
                    names.add(name)
        return sorted(names)[: self.config.max_pattern_pvs]

    def _pv_for_channel_id(self, channel_id: int) -> str:
        pv = self.channel_id_map.get(int(channel_id))
        if not pv:
            raise KeyError(
                f"HTTP archive repository does not know channel_id={channel_id}; "
                "set ARCHIVE_HTTP_CHANNEL_ID_MAP to add this mapping."
            )
        return pv

    def _channel_id_for_pv(self, pv: str) -> int:
        for channel_id, name in self.channel_id_map.items():
            if name == pv:
                return channel_id
        return 0

    def _assert_raw(self, rows: list[ArchiveHttpRow]) -> None:
        if not self.config.require_raw_samples:
            return
        aggregated = [row for row in rows if row.sample_type and row.sample_type != "raw"]
        if aggregated:
            first = aggregated[0]
            raise ArchiveHttpDataError(
                f"Archive HTTP returned aggregated samples for {first.pv}: {first.sample_type}. "
                "HTTP avg diagnostic queries must be split into smaller windows."
            )


def _raw_samples_from_rows(rows: list[ArchiveHttpRow], *, channel_id: int) -> list[PVRawSample]:
    output: list[PVRawSample] = []
    for row in rows:
        num_val = row.num_val
        if num_val is None and row.float_val is not None:
            num_val = int(row.float_val)
        output.append(
            PVRawSample(
                channel_id=channel_id,
                channel_name=row.pv,
                smpl_time=row.smpl_time,
                nanosecs=row.nanosecs,
                num_val=num_val,
                severity_id=None,
                status_id=None,
            )
        )
    return output


def _limit(samples: list, limit: int) -> list:
    if limit is None:
        return samples
    return samples[:limit]


ArchiveHttpRepository = HttpArchiveRepository

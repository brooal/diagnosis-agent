# app/data_sources/pv_repository.py

from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text

from app.config import get_settings
from app.data_sources.remote_db import RemoteDB
from app.data_sources.schemas import PVRawSample, PVSample


class PVRepository:
    def __init__(self, db: RemoteDB) -> None:
        self.db = db
        self.settings = get_settings()

    def _iso_time_sql(self, expr: str) -> str:
        return (
            f"to_char({expr}, 'YYYY-MM-DD\"T\"HH24:MI:SS') "
            f"|| to_char({expr}, 'TZH:TZM')"
        )

    def fetch_channel_samples(
        self,
        channel_name: str,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVSample]:
        s = self.settings
        max_points = limit or s.diag_db_max_query_points

        sql = text(
            f"""
            SELECT
                c.{s.archive_channel_name_col} AS channel_name,
                {self._iso_time_sql("s." + s.archive_sample_time_col)} AS smpl_time,
                s.{s.archive_sample_nanosecs_col} AS nanosecs,
                s.{s.archive_sample_float_col} AS float_val
            FROM {s.archive_sample_table} AS s
            JOIN {s.archive_channel_table} AS c
              ON s.{s.archive_sample_channel_id_col} = c.{s.archive_channel_id_col}
            WHERE c.{s.archive_channel_name_col} = :channel_name
              AND s.{s.archive_sample_time_col} >= CAST(:start_time AS timestamptz)
              AND s.{s.archive_sample_time_col} <= CAST(:end_time AS timestamptz)
            ORDER BY s.{s.archive_sample_time_col}, s.{s.archive_sample_nanosecs_col}
            LIMIT :limit
            """
        )

        with self.db.connect() as conn:
            rows = conn.execute(
                sql,
                {
                    "channel_name": channel_name,
                    "start_time": start_time,
                    "end_time": end_time,
                    "limit": max_points,
                },
            ).mappings().all()

        return [
            PVSample(
                channel_name=row["channel_name"],
                smpl_time=row["smpl_time"],
                nanosecs=int(row["nanosecs"]),
                float_val=float(row["float_val"]),
            )
            for row in rows
        ]

    def fetch_pattern_samples(
        self,
        pattern: str,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVSample]:
        s = self.settings
        max_points = limit or s.diag_db_max_query_points

        sql = text(
            f"""
            SELECT
                c.{s.archive_channel_name_col} AS channel_name,
                {self._iso_time_sql("s." + s.archive_sample_time_col)} AS smpl_time,
                s.{s.archive_sample_nanosecs_col} AS nanosecs,
                s.{s.archive_sample_float_col} AS float_val
            FROM {s.archive_sample_table} AS s
            JOIN {s.archive_channel_table} AS c
              ON s.{s.archive_sample_channel_id_col} = c.{s.archive_channel_id_col}
            WHERE c.{s.archive_channel_name_col} ILIKE :pattern
              AND s.{s.archive_sample_time_col} >= CAST(:start_time AS timestamptz)
              AND s.{s.archive_sample_time_col} <= CAST(:end_time AS timestamptz)
            ORDER BY c.{s.archive_channel_name_col},
                     s.{s.archive_sample_time_col},
                     s.{s.archive_sample_nanosecs_col}
            LIMIT :limit
            """
        )

        with self.db.connect() as conn:
            rows = conn.execute(
                sql,
                {
                    "pattern": pattern,
                    "start_time": start_time,
                    "end_time": end_time,
                    "limit": max_points,
                },
            ).mappings().all()

        return [
            PVSample(
                channel_name=row["channel_name"],
                smpl_time=row["smpl_time"],
                nanosecs=int(row["nanosecs"]),
                float_val=float(row["float_val"]),
            )
            for row in rows
        ]

    def fetch_raw_channel_samples(
        self,
        channel_ids: list[int],
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVRawSample]:
        if not channel_ids:
            return []

        s = self.settings
        max_points = limit or s.diag_db_max_query_points
        sql = text(
            f"""
            SELECT
                s.{s.archive_sample_raw_channel_id_col} AS channel_id,
                c.{s.archive_channel_name_col} AS channel_name,
                {self._iso_time_sql("s." + s.archive_sample_raw_time_col)} AS smpl_time,
                s.{s.archive_sample_raw_nanosecs_col} AS nanosecs,
                s.{s.archive_sample_raw_num_val_col} AS num_val,
                s.{s.archive_sample_raw_severity_id_col} AS severity_id,
                s.{s.archive_sample_raw_status_id_col} AS status_id
            FROM {s.archive_sample_raw_table} AS s
            LEFT JOIN {s.archive_channel_table} AS c
              ON s.{s.archive_sample_raw_channel_id_col} = c.{s.archive_channel_id_col}
            WHERE s.{s.archive_sample_raw_channel_id_col} IN :channel_ids
              AND s.{s.archive_sample_raw_time_col} >= CAST(:start_time AS timestamptz)
              AND s.{s.archive_sample_raw_time_col} <= CAST(:end_time AS timestamptz)
            ORDER BY s.{s.archive_sample_raw_channel_id_col},
                     s.{s.archive_sample_raw_time_col},
                     s.{s.archive_sample_raw_nanosecs_col}
            LIMIT :limit
            """
        ).bindparams(bindparam("channel_ids", expanding=True))

        with self.db.connect() as conn:
            rows = conn.execute(
                sql,
                {
                    "channel_ids": channel_ids,
                    "start_time": start_time,
                    "end_time": end_time,
                    "limit": max_points,
                },
            ).mappings().all()

        return [_raw_sample_from_row(row) for row in rows]

    def fetch_latest_raw_sample_before(
        self,
        channel_id: int,
        before_time: str,
    ) -> PVRawSample | None:
        s = self.settings
        sql = text(
            f"""
            SELECT
                s.{s.archive_sample_raw_channel_id_col} AS channel_id,
                c.{s.archive_channel_name_col} AS channel_name,
                {self._iso_time_sql("s." + s.archive_sample_raw_time_col)} AS smpl_time,
                s.{s.archive_sample_raw_nanosecs_col} AS nanosecs,
                s.{s.archive_sample_raw_num_val_col} AS num_val,
                s.{s.archive_sample_raw_severity_id_col} AS severity_id,
                s.{s.archive_sample_raw_status_id_col} AS status_id
            FROM {s.archive_sample_raw_table} AS s
            LEFT JOIN {s.archive_channel_table} AS c
              ON s.{s.archive_sample_raw_channel_id_col} = c.{s.archive_channel_id_col}
            WHERE s.{s.archive_sample_raw_channel_id_col} = :channel_id
              AND s.{s.archive_sample_raw_time_col} < CAST(:before_time AS timestamptz)
            ORDER BY s.{s.archive_sample_raw_time_col} DESC,
                     s.{s.archive_sample_raw_nanosecs_col} DESC
            LIMIT 1
            """
        )

        with self.db.connect() as conn:
            row = conn.execute(
                sql,
                {"channel_id": channel_id, "before_time": before_time},
            ).mappings().one_or_none()

        return _raw_sample_from_row(row) if row is not None else None

    def fetch_next_raw_sample_after(
        self,
        channel_id: int,
        after_time: str,
        *,
        expected_value: int | None = None,
        end_time: str | None = None,
    ) -> PVRawSample | None:
        s = self.settings
        value_clause = ""
        params: dict[str, object] = {"channel_id": channel_id, "after_time": after_time}
        if expected_value is not None:
            value_clause = f"AND s.{s.archive_sample_raw_num_val_col} = :expected_value"
            params["expected_value"] = expected_value
        end_clause = ""
        if end_time is not None:
            end_clause = (
                f"AND s.{s.archive_sample_raw_time_col} <= CAST(:end_time AS timestamptz)"
            )
            params["end_time"] = end_time

        sql = text(
            f"""
            SELECT
                s.{s.archive_sample_raw_channel_id_col} AS channel_id,
                c.{s.archive_channel_name_col} AS channel_name,
                {self._iso_time_sql("s." + s.archive_sample_raw_time_col)} AS smpl_time,
                s.{s.archive_sample_raw_nanosecs_col} AS nanosecs,
                s.{s.archive_sample_raw_num_val_col} AS num_val,
                s.{s.archive_sample_raw_severity_id_col} AS severity_id,
                s.{s.archive_sample_raw_status_id_col} AS status_id
            FROM {s.archive_sample_raw_table} AS s
            LEFT JOIN {s.archive_channel_table} AS c
              ON s.{s.archive_sample_raw_channel_id_col} = c.{s.archive_channel_id_col}
            WHERE s.{s.archive_sample_raw_channel_id_col} = :channel_id
              AND s.{s.archive_sample_raw_time_col} > CAST(:after_time AS timestamptz)
              {value_clause}
              {end_clause}
            ORDER BY s.{s.archive_sample_raw_time_col},
                     s.{s.archive_sample_raw_nanosecs_col}
            LIMIT 1
            """
        )

        with self.db.connect() as conn:
            row = conn.execute(sql, params).mappings().one_or_none()

        return _raw_sample_from_row(row) if row is not None else None


def _raw_sample_from_row(row: Any) -> PVRawSample:
    return PVRawSample(
        channel_id=int(row["channel_id"]),
        channel_name=row["channel_name"],
        smpl_time=row["smpl_time"],
        nanosecs=int(row["nanosecs"] or 0),
        num_val=int(row["num_val"]) if row["num_val"] is not None else None,
        severity_id=int(row["severity_id"]) if row["severity_id"] is not None else None,
        status_id=int(row["status_id"]) if row["status_id"] is not None else None,
    )

# app/data_sources/pv_repository.py

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.data_sources.remote_db import RemoteDB
from app.data_sources.schemas import PVSample


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
              AND s.{s.archive_sample_time_col} >= :start_time::timestamptz
              AND s.{s.archive_sample_time_col} <= :end_time::timestamptz
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
              AND s.{s.archive_sample_time_col} >= :start_time::timestamptz
              AND s.{s.archive_sample_time_col} <= :end_time::timestamptz
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
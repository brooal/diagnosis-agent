# 远程的timescaledb数据库连接

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import QueuePool

from app.config import get_settings
from app.data_sources.sql_guard import validate_readonly_sql
from app.data_sources.schemas import QueryResult

class RemoteDB:

    def __init__(self) -> None:
        self.settings = get_settings()

        connect_args = {
            "connect_timeout": self.settings.diag_db_connect_timeout,
            "options" : (
                f"-c timezone={self.settings.diag_db_timezone} "
                f"-c statement_timeout={self.settings.diag_db_statement_timeout_ms} "
            ),
        }

        self.engine: Engine = create_engine(
            self.settings.diag_database_url,
            echo=False,
            poolclass=QueuePool,
            pool_size=self.settings.diag_db_pool_size,
            max_overflow=self.settings.diag_db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=self.settings.diag_db_pool_recycle,
            connect_args=connect_args,
            future=True,
        )

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self.engine.connect() as conn:
            yield conn

    def ping(self) -> dict[str, Any]:
        sql = text(
            """
            SELECT 
                current_database() AS database, 
                current_user AS "user",
                current_setting('TIMEZONE') AS session_timezone,
                to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS') || to_char(NOW(), 'TZH:TZM' AS now
            """
        )

        with self.connect() as conn:
            row = conn.execute(sql).mappings().one()

        timezone_ok = row["session_timezone"] == self.settings.diag_db_timezone

        return {
            "status": "ok" if timezone_ok else "timezone_mismatch",
            "database": row["database"],
            "user": row["user"],
            "session_timezone": row["session_timezone"],
            "timezone_expected": self.settings.diag_db_timezone,
            "timezone_ok": timezone_ok,
            "now": row["now"],
        }

    def readonly_query(
            self,
            sql : str,
            params : dict[str, Any] | None = None,
            max_rows : int | None = None
    ) -> QueryResult:
        validated =validate_readonly_sql(sql)
        limit = max_rows or self.settings.diag_db_max_rows
        with self.connect() as conn:
            result = conn.execute(text(validated), params or {})
            rows = result.mappings().fetchmany(limit + 1)

        truncated = len(rows) > limit
        visible_rows = rows[:limit]

        return QueryResult(
            columns=list(result.keys()),
            rows=[dict(row) for row in visible_rows],
            row_count=len(visible_rows),
            truncated=truncated,
            max_rows=limit,
        )

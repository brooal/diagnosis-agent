# app/tools/db_tools.py
# 测试控制网数据库的连通性
from __future__ import annotations

from app.data_sources.remote_db import RemoteDB
from app.tools.base import ToolResult, ToolSpec


class DBTools:
    def __init__(self, remote_db: RemoteDB) -> None:
        self.remote_db = remote_db

    def test_db_connection(self) -> ToolResult:
        try:
            output = self.remote_db.ping()
            return ToolResult(
                ok=output.get("timezone_ok", False),
                output=output,
                summary=(
                    "远程数据库连接正常。"
                    if output.get("timezone_ok")
                    else "远程数据库连接成功，但会话时区与期望不一致。"
                ),
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                output={},
                summary="远程数据库连接失败。",
                error=f"{type(exc).__name__}: {exc}",
            )

    def readonly_query(self, sql: str, max_rows: int | None = None) -> ToolResult:
        try:
            result = self.remote_db.readonly_query(sql=sql, max_rows=max_rows)
            output = {
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "truncated": result.truncated,
                "max_rows": result.max_rows,
            }
            return ToolResult(
                ok=True,
                output=output,
                summary=f"只读 SQL 查询成功，返回 {result.row_count} 行。",
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                output={},
                summary="只读 SQL 查询失败。",
                error=f"{type(exc).__name__}: {exc}",
            )

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="test_db_connection",
                description="测试远程 PostgreSQL 诊断数据库是否可以连接，并检查时区配置。",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=self.test_db_connection,
            ),
            ToolSpec(
                name="readonly_sql_query",
                description=(
                    "执行只读 SQL 查询。只允许 SELECT、SHOW、EXPLAIN、WITH；"
                    "禁止 INSERT、UPDATE、DELETE、DROP 等危险语句。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "只读 SQL"},
                        "max_rows": {"type": "integer", "description": "最多返回行数"},
                    },
                    "required": ["sql"],
                },
                handler=self.readonly_query,
            ),
        ]
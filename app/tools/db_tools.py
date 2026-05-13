from __future__ import annotations

from app.tools.base import ToolResult, get_tool_runtime, tool


def _test_db_connection_with(remote_db: object) -> ToolResult:
    try:
        output = remote_db.ping()
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


def _readonly_query_with(
    remote_db: object,
    sql: str,
    max_rows: int | None = None,
) -> ToolResult:
    try:
        result = remote_db.readonly_query(sql=sql, max_rows=max_rows)
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


@tool(
    name="test_db_connection",
    description="测试远程 PostgreSQL 诊断数据库是否可以连接，并检查时区配置。",
    parameters={"type": "object", "properties": {}, "required": []},
)
def test_db_connection() -> ToolResult:
    runtime = get_tool_runtime()
    if runtime.remote_db is None:
        return ToolResult(
            ok=False,
            output={},
            summary="远程数据库未初始化。",
            error="missing_remote_db",
        )
    return _test_db_connection_with(runtime.remote_db)


@tool(
    name="readonly_sql_query",
    description="执行只读 SQL 查询。只允许 SELECT、SHOW、EXPLAIN、WITH；禁止 INSERT、UPDATE、DELETE、DROP 等危险语句。",
    parameters={
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "只读 SQL"},
            "max_rows": {"type": "integer", "description": "最多返回行数"},
        },
        "required": ["sql"],
    },
)
def readonly_query(sql: str, max_rows: int | None = None) -> ToolResult:
    runtime = get_tool_runtime()
    if runtime.remote_db is None:
        return ToolResult(
            ok=False,
            output={},
            summary="远程数据库未初始化。",
            error="missing_remote_db",
        )
    return _readonly_query_with(runtime.remote_db, sql=sql, max_rows=max_rows)

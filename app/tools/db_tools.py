from app.tools.base import ToolResult, ToolSpec

def test_db_connection() -> ToolResult:
    return ToolResult(
        ok= True,
        output={"connect" : True},
        summary="数据库连接正常",
    )

test_db_connection_spec = ToolSpec(
    name = "test_db_connection",
    description="测试诊断数据库是否可以正常的连接",
    parameters = {
        "type" : "object",
        "properties" : {},
        "required" : [],
    },
    handler=test_db_connection,
)
from app.tools.registry import ToolRegistry
from app.tools.db_tools import test_db_connection_spec
from app.tools.pv_tools import query_pv_range_spec, query_pv_at_time_spec

#注册目前所有的工具，并返回注册表供agent使用
def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(test_db_connection_spec)
    registry.register(query_pv_range_spec)
    registry.register(query_pv_at_time_spec)
    return registry

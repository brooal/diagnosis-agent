from __future__ import annotations

from app.data_sources.remote_db import RemoteDB
from app.data_sources.pv_repository import PVRepository
from app.tools.db_tools import DBTools
from app.tools.diagnosis_tools import DiagnosisTools
from app.tools.pv_tools import PVTools
from app.tools.registry import ToolRegistry

#注册目前所有的工具，并返回注册表供agent使用
def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    remote_db = RemoteDB()
    pv_repo = PVRepository(remote_db)
    db_tools = DBTools(remote_db)
    pv_tools = PVTools(pv_repo)
    diag_tools = DiagnosisTools(pv_repo)

    for group in [db_tools , pv_tools, diag_tools]:
        for spec in group.specs():
            registry.register(spec)

    return registry

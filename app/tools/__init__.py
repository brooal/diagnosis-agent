from __future__ import annotations

import importlib

from app.config import get_settings
from app.data_sources.pv_repository import PVRepository
from app.data_sources.remote_db import RemoteDB
from app.tools.base import ToolRegistry, get_tool_registry, set_tool_runtime

_BUILTIN_TOOL_MODULES = (
    "app.tools.db_tools",
    "app.tools.pv_tools",
    "app.tools.diagnosis_tools",
)
_builtin_tools_loaded = False


def _load_builtin_tool_modules() -> None:
    global _builtin_tools_loaded
    if _builtin_tools_loaded:
        return

    for module_name in _BUILTIN_TOOL_MODULES:
        importlib.import_module(module_name)

    _builtin_tools_loaded = True


def build_tool_registry() -> ToolRegistry:
    remote_db = RemoteDB()
    pv_repo = PVRepository(remote_db)
    set_tool_runtime(
        remote_db=remote_db,
        pv_repo=pv_repo,
        settings=get_settings(),
    )
    _load_builtin_tool_modules()
    return get_tool_registry()


__all__ = ["ToolRegistry", "build_tool_registry"]

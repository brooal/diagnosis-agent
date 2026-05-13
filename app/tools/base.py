from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    ok: bool
    summary: str
    output: Any = None
    error: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., ToolResult]


@dataclass
class ToolRuntime:
    remote_db: Any | None = None
    pv_repo: Any | None = None
    settings: Any | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        func: Callable[..., ToolResult],
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
        )

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        return self._tools[name]

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self._tools:
            return ToolResult(
                ok=False,
                summary=f"未知工具: {name}",
                error="unknown_tool",
            )

        spec = self._tools[name]
        try:
            return spec.func(**arguments)
        except Exception as exc:
            return ToolResult(
                ok=False,
                summary=f"工具 {name} 执行失败: {exc}",
                error=type(exc).__name__,
            )

    def list_spec(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            }
            for spec in self._tools.values()
        ]

    def clear(self) -> None:
        self._tools.clear()


_global_tool_registry = ToolRegistry()
_tool_runtime = ToolRuntime()


def tool(name: str, description: str, parameters: dict[str, Any]) -> Callable[..., Any]:
    def decorator(func: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        _global_tool_registry.register(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
        )
        return func

    return decorator


def get_tool_registry() -> ToolRegistry:
    return _global_tool_registry


def set_tool_runtime(
    *,
    remote_db: Any | None = None,
    pv_repo: Any | None = None,
    settings: Any | None = None,
) -> None:
    _tool_runtime.remote_db = remote_db
    _tool_runtime.pv_repo = pv_repo
    _tool_runtime.settings = settings


def get_tool_runtime() -> ToolRuntime:
    return _tool_runtime


def reset_tool_registry() -> None:
    _global_tool_registry.clear()


def reset_tool_runtime() -> None:
    set_tool_runtime()

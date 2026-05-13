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
    category: str
    read_only: bool
    expose_to_agent: bool
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
        category: str,
        read_only: bool,
        expose_to_agent: bool,
        func: Callable[..., ToolResult],
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            category=category,
            read_only=read_only,
            expose_to_agent=expose_to_agent,
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
        missing_required = _missing_required_arguments(spec.parameters, arguments)
        if missing_required:
            names = ", ".join(missing_required)
            return ToolResult(
                ok=False,
                summary=f"工具 {name} 缺少必填参数: {names}",
                error="missing_required_arguments",
                output={"missing_required": missing_required},
            )
        try:
            return spec.func(**arguments)
        except Exception as exc:
            return ToolResult(
                ok=False,
                summary=f"工具 {name} 执行失败: {exc}",
                error=type(exc).__name__,
            )

    def list_spec(self, expose_to_agent_only: bool = True) -> list[dict[str, Any]]:
        specs = self._tools.values()
        if expose_to_agent_only:
            specs = [spec for spec in specs if spec.expose_to_agent]
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
                "category": spec.category,
                "read_only": spec.read_only,
                "expose_to_agent": spec.expose_to_agent,
            }
            for spec in specs
        ]

    def clear(self) -> None:
        self._tools.clear()


_global_tool_registry = ToolRegistry()
_tool_runtime = ToolRuntime()


def tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    category: str,
    read_only: bool,
    expose_to_agent: bool,
) -> Callable[..., Any]:
    def decorator(func: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        _global_tool_registry.register(
            name=name,
            description=description,
            parameters=parameters,
            category=category,
            read_only=read_only,
            expose_to_agent=expose_to_agent,
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


def _missing_required_arguments(
    parameters: dict[str, Any],
    arguments: dict[str, Any],
) -> list[str]:
    required = parameters.get("required", [])
    if not isinstance(required, list):
        return []
    missing: list[str] = []
    for key in required:
        if not isinstance(key, str):
            continue
        if key not in arguments or arguments[key] is None:
            missing.append(key)
    return missing

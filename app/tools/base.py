from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class ToolResult:
    ok : bool
    output : Any
    summary : str
    error : str | None = None

@dataclass
class ToolSpec:
    name : str
    description : str
    parameters : dict[str, Any]
    handler : Callable[..., ToolResult]
from __future__ import annotations

from json import tool

from app.tools.base import ToolSpec,ToolResult

class ToolRegistry:

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec:ToolSpec) -> None:
        print(f"[ToolRegistry] registering: {spec.name}")
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered : {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name :str) -> ToolSpec:
        if name not in self._tools:
            raise ValueError(f"Unknown tool : {name}")
        return self._tools[name]

    def list_spec(self) -> list[dict]:
        return [
            {
                "name" : spec.name,
                "description" : spec.description,
                "parameters" : spec.parameters,
            }
            for spec in self._tools.values()
        ]

    def call(self,name : str, arguments : dict) -> ToolResult:
        spec = self.get(name)
        return spec.handler(**arguments)




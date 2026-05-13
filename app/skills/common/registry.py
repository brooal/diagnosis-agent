from __future__ import annotations

import difflib
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from app.agent.state import DiagnosisState
from app.skills.common.base import SkillContext, SkillResult
from app.skills.common.metadata import SkillDescriptor, load_skill_descriptor
from app.tools.registry import ToolRegistry


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[tuple[str, str], SkillDescriptor] = {}

    def register(self, descriptor: SkillDescriptor) -> None:
        if descriptor.key in self._skills:
            name, version = descriptor.key
            raise ValueError(f"Skill already registered: {name}@{version}")
        self._skills[descriptor.key] = descriptor

    def discover(self, path: str | Path) -> None:
        root = Path(path)
        for metadata_path in sorted(root.rglob("SKILL.md")):
            self.register(load_skill_descriptor(metadata_path))

    def load_plugin(self, path: str | Path) -> None:
        self.discover(path)

    def get(self, name: str, version: str | None = None) -> Any:
        descriptor = self.get_descriptor(name, version)
        return self._load_instance(descriptor)

    def get_descriptor(self, name: str, version: str | None = None) -> SkillDescriptor:
        if version is not None:
            key = (name, version)
            if key not in self._skills:
                raise ValueError(f"Unknown skill: {name}@{version}")
            return self._skills[key]

        versions = [
            descriptor for (skill_name, _), descriptor in self._skills.items() if skill_name == name
        ]
        if not versions:
            raise ValueError(f"Unknown skill: {name}")
        return max(versions, key=lambda descriptor: _version_key(descriptor.version))

    def list_spec(
        self,
        category: str | None = None,
        include_versions: bool = False,
    ) -> list[dict[str, Any]]:
        descriptors = self._latest_descriptors()
        if category is not None:
            descriptors = [
                descriptor for descriptor in descriptors if descriptor.category == category
            ]
        descriptors.sort(key=lambda descriptor: (descriptor.category, descriptor.name))
        return [descriptor.to_spec(include_version=include_versions) for descriptor in descriptors]

    def search(
        self,
        query: str,
        category: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        descriptors = self._latest_descriptors()
        if category is not None:
            descriptors = [
                descriptor for descriptor in descriptors if descriptor.category == category
            ]

        query = query.strip().lower()
        scored: list[tuple[float, SkillDescriptor]] = []
        for descriptor in descriptors:
            haystack = " ".join(
                [
                    descriptor.name,
                    descriptor.description,
                    descriptor.category,
                    descriptor.domain or "",
                    descriptor.stage or "",
                    " ".join(descriptor.symptoms),
                    " ".join(descriptor.produces),
                    " ".join(descriptor.tags),
                ]
            ).lower()
            score = difflib.SequenceMatcher(None, query, haystack).ratio()
            if query and query in haystack:
                score += 1.0
            scored.append((score, descriptor))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            descriptor.to_spec(include_version=True)
            for score, descriptor in scored[:limit]
            if score > 0
        ]

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        state: DiagnosisState,
        tools: ToolRegistry,
        version: str | None = None,
    ) -> SkillResult:
        skill = self.get(name, version)
        context = SkillContext(state=state, tools=tools, registry=self)
        return skill.run(context=context, arguments=arguments)

    def _latest_descriptors(self) -> list[SkillDescriptor]:
        latest_by_name: dict[str, SkillDescriptor] = {}
        for descriptor in self._skills.values():
            current = latest_by_name.get(descriptor.name)
            if current is None or _version_key(descriptor.version) > _version_key(current.version):
                latest_by_name[descriptor.name] = descriptor
        return list(latest_by_name.values())

    def _load_instance(self, descriptor: SkillDescriptor) -> Any:
        if descriptor._instance is not None:
            return descriptor._instance

        module_name, class_name = descriptor.entrypoint.split(":", 1)
        module = self._import_entrypoint_module(module_name, descriptor)
        cls = getattr(module, class_name)
        descriptor._instance = cls()
        return descriptor._instance

    def _import_entrypoint_module(
        self,
        module_name: str,
        descriptor: SkillDescriptor,
    ) -> Any:
        base_dir = descriptor.base_dir
        if base_dir is not None and "." not in module_name:
            module_path = base_dir / f"{module_name}.py"
            if module_path.exists():
                unique_name = f"_diagnosis_skill_{descriptor.name}_{descriptor.version}".replace(
                    "-", "_"
                ).replace(".", "_")
                spec = importlib.util.spec_from_file_location(unique_name, module_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot load skill module: {module_path}")
                module = importlib.util.module_from_spec(spec)
                sys.modules[unique_name] = module
                spec.loader.exec_module(module)
                return module

        return importlib.import_module(module_name)

def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in version.split("."):
        number = ""
        for char in part:
            if char.isdigit():
                number += char
            else:
                break
        parts.append(int(number or 0))
    return tuple(parts)

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillDescriptor:
    name: str
    version: str
    category: str
    description: str
    entrypoint: str
    parameters: dict[str, Any]
    tags: list[str] = field(default_factory=list)
    metadata_path: Path | None = None
    base_dir: Path | None = None
    docs: str = ""
    _instance: Any | None = field(default=None, repr=False, compare=False)

    @property
    def key(self) -> tuple[str, str]:
        return (self.name, self.version)

    def to_spec(self, *, include_version: bool = False) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "tags": self.tags,
        }
        if include_version:
            spec["version"] = self.version
        return spec


def load_skill_descriptor(path: str | Path) -> SkillDescriptor:
    metadata_path = Path(path)
    text = metadata_path.read_text(encoding="utf-8")
    frontmatter, docs = _split_frontmatter(text)
    data = _parse_frontmatter(frontmatter)

    required = ["name", "version", "category", "description", "entrypoint", "parameters"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{metadata_path} missing required metadata: {', '.join(missing)}")

    parameters = data["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError(f"{metadata_path} metadata field 'parameters' must be an object.")

    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        raise ValueError(f"{metadata_path} metadata field 'tags' must be a list.")

    return SkillDescriptor(
        name=str(data["name"]),
        version=str(data["version"]),
        category=str(data["category"]),
        description=str(data["description"]),
        entrypoint=str(data["entrypoint"]),
        parameters=parameters,
        tags=[str(item) for item in tags],
        metadata_path=metadata_path,
        base_dir=metadata_path.parent,
        docs=docs.strip(),
    )


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        raise ValueError("SKILL.md must start with YAML-style frontmatter.")

    lines = text.splitlines()
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])

    raise ValueError("SKILL.md frontmatter is missing closing '---'.")


def _parse_frontmatter(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        index += 1
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith((" ", "\t")):
            raise ValueError(f"Unexpected indented metadata line: {raw_line}")
        if ":" not in raw_line:
            raise ValueError(f"Invalid metadata line: {raw_line}")

        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if raw_value:
            data[key] = _parse_scalar(raw_value)
            continue

        block_lines: list[str] = []
        while index < len(lines):
            next_line = lines[index]
            if not next_line.strip():
                block_lines.append(next_line)
                index += 1
                continue
            if not next_line.startswith((" ", "\t")):
                break
            block_lines.append(next_line)
            index += 1

        data[key] = _parse_block(block_lines)

    return data


def _parse_block(lines: list[str]) -> Any:
    stripped = "\n".join(line[2:] if line.startswith("  ") else line.lstrip() for line in lines)
    stripped = stripped.strip()
    if not stripped:
        return {}

    if stripped.startswith(("{", "[")):
        return json.loads(stripped)

    items: list[Any] = []
    for line in stripped.splitlines():
        value = line.strip()
        if value.startswith("- "):
            items.append(_parse_scalar(value[2:].strip()))
    if items and len(items) == len([line for line in stripped.splitlines() if line.strip()]):
        return items

    raise ValueError("Only JSON object/list blocks and simple list blocks are supported.")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith(("{", "[")):
        return json.loads(value)
    if value in {"true", "false"}:
        return value == "true"
    if value == "null":
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return ast.literal_eval(value)
    return value

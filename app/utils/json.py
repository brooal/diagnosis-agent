from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def make_json_safe(value: Any) -> Any:
    """Return a recursively JSON-serializable representation."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Enum):
        return make_json_safe(value.value)

    if isinstance(value, bytes):
        return value.hex()

    if is_dataclass(value) and not isinstance(value, type):
        return make_json_safe(asdict(value))

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return make_json_safe(model_dump())

    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set, frozenset)):
        return [make_json_safe(item) for item in value]

    return str(value)

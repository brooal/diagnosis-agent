from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str | None = None
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "source": self.source,
        }


@dataclass(frozen=True)
class LLMCompletion:
    content: str
    usage: dict[str, Any]


def usage_from_openai_response(resp: Any, *, model: str | None = None) -> dict[str, Any]:
    usage = getattr(resp, "usage", None)
    if usage is None and isinstance(resp, dict):
        usage = resp.get("usage")
    prompt_tokens = _read_int(usage, "prompt_tokens")
    completion_tokens = _read_int(usage, "completion_tokens")
    total_tokens = _read_int(usage, "total_tokens")
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        model=model,
        source="provider" if total_tokens > 0 else "provider_missing",
    ).to_dict()


def estimate_usage(
    messages: list[dict[str, Any]],
    completion: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    prompt_text = "\n".join(str(item.get("content") or "") for item in messages)
    prompt_tokens = estimate_text_tokens(prompt_text)
    completion_tokens = estimate_text_tokens(completion)
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        model=model,
        source="estimated",
    ).to_dict()


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, round(ascii_chars / 4 + non_ascii_chars / 1.7))


def merge_usage(*items: dict[str, Any] | None) -> dict[str, Any] | None:
    valid = [item for item in items if item]
    if not valid:
        return None
    prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in valid)
    completion_tokens = sum(int(item.get("completion_tokens") or 0) for item in valid)
    total_tokens = sum(int(item.get("total_tokens") or 0) for item in valid)
    models = sorted({str(item.get("model")) for item in valid if item.get("model")})
    sources = sorted({str(item.get("source")) for item in valid if item.get("source")})
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens or prompt_tokens + completion_tokens,
        "model": models[0] if len(models) == 1 else ", ".join(models) if models else None,
        "source": sources[0] if len(sources) == 1 else "+".join(sources) if sources else "unknown",
        "calls": len(valid),
        "items": valid,
    }


def _read_int(obj: Any, name: str) -> int:
    if obj is None:
        return 0
    if isinstance(obj, dict):
        value = obj.get(name)
    else:
        value = getattr(obj, name, None)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

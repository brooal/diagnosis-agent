# app/llm/client.py

from __future__ import annotations

import os
from openai import OpenAI
from typing import Any

class LLMClient:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY", "EMPTY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def complete(self, messages: list[dict[str, Any]], temperature: float = 0.1) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""


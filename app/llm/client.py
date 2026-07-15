# app/llm/client.py

from __future__ import annotations

import os
from openai import OpenAI
from typing import Any
from dotenv import load_dotenv

from app.llm.token_usage import LLMCompletion, estimate_usage, usage_from_openai_response

load_dotenv()

class LLMClient:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "EMPTY",
            base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL"),
        )
        self.model = os.getenv("OPENAI_MODEL") or os.getenv("DEEPSEEK_MODEL", "gpt-4o-mini")
        self.last_usage: dict[str, Any] | None = None

    def complete(self, messages: list[dict[str, Any]], temperature: float = 0.1) -> str:
        completion = self.complete_with_usage(messages, temperature=temperature)
        return completion.content

    def complete_with_usage(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.1,
    ) -> LLMCompletion:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        content = resp.choices[0].message.content or ""
        usage = usage_from_openai_response(resp, model=self.model)
        if not usage.get("total_tokens"):
            usage = estimate_usage(messages, content, model=self.model)
        self.last_usage = usage
        return LLMCompletion(content=content, usage=usage)

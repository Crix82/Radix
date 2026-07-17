"""Shared OpenAI-compatible chat client (SPEC §8).

Ollama and vLLM both expose the OpenAI `/chat/completions` API, so one streaming client
backs both providers; they differ only in the default base URL / model via env.
"""

import json
from collections.abc import Iterator
from typing import Any

import httpx

from app.services.llm.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _payload(
        self, messages: list[dict[str, str]], stream: bool, json_schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": 0.1,  # grounded, low-variance answers
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "schema", "schema": json_schema},
            }
        return payload

    def complete(
        self,
        messages: list[dict[str, str]],
        stream: bool = True,
        json_schema: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        payload = self._payload(messages, stream, json_schema)
        url = f"{self.base_url}/chat/completions"
        if not stream:
            resp = httpx.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            yield resp.json()["choices"][0]["message"]["content"]
            return
        yield from self._stream(url, payload)

    def _stream(self, url: str, payload: dict[str, Any]) -> Iterator[str]:
        with httpx.stream("POST", url, json=payload, timeout=self.timeout) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                token = delta.get("content")
                if token:
                    yield token

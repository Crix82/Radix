from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class LLMProvider(ABC):
    """Provider abstraction (SPEC §8): Ollama by default, vLLM in production.

    Both talk the OpenAI-compatible chat completions API; concrete providers
    are implemented in M4 alongside the RAG chat.
    """

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        stream: bool = True,
        json_schema: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """Yield completion tokens (or the full response as a single item when stream=False)."""


def get_llm_provider() -> LLMProvider:
    raise NotImplementedError("Implemented in M4 (OllamaProvider / VLLMProvider)")

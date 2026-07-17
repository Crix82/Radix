from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from app.core.config import get_settings


class LLMProvider(ABC):
    """Provider abstraction (SPEC §8): Ollama by default, vLLM in production.

    Both talk the OpenAI-compatible chat completions API; concrete providers live in
    `app.services.llm.providers`.
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
    from app.services.llm.providers import OllamaProvider, VLLMProvider

    settings = get_settings()
    providers: dict[str, type[LLMProvider]] = {"ollama": OllamaProvider, "vllm": VLLMProvider}
    provider_cls = providers.get(settings.llm_provider.lower())
    if provider_cls is None:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")
    return provider_cls(base_url=settings.llm_base_url, model=settings.llm_model)  # type: ignore[call-arg]

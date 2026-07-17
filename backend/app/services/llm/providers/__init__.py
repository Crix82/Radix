from app.services.llm.providers.openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Default provider (SPEC §2): local Ollama, OpenAI-compatible endpoint."""


class VLLMProvider(OpenAICompatibleProvider):
    """Production provider (SPEC §2): vLLM, same OpenAI-compatible API."""


__all__ = ["OllamaProvider", "OpenAICompatibleProvider", "VLLMProvider"]

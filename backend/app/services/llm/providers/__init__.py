from app.services.llm.providers.openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Default provider (SPEC §2): local Ollama, OpenAI-compatible endpoint.

    The bundled Qwen3.5 checkpoints are *reasoning* models: left to their defaults they burn
    ~1k hidden "thinking" tokens per answer (~25-35s) and intermittently emit empty content,
    which our streaming client (content-only) turns into a spurious refusal. reasoning_effort
    "none" disables thinking → ~1s answers with populated content. Only this key works over
    Ollama's OpenAI endpoint; /no_think, think:false and chat_template_kwargs do not.
    """

    extra_payload = {"reasoning_effort": "none"}


class VLLMProvider(OpenAICompatibleProvider):
    """Production provider (SPEC §2): vLLM, same OpenAI-compatible API."""


__all__ = ["OllamaProvider", "OpenAICompatibleProvider", "VLLMProvider"]

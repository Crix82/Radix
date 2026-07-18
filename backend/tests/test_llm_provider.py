from contextlib import contextmanager

import pytest

from app.services.llm.base import get_llm_provider
from app.services.llm.providers import OllamaProvider, VLLMProvider
from app.services.llm.providers.openai_compatible import OpenAICompatibleProvider


class _FakeStreamResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        pass

    def iter_lines(self):
        yield from self._lines


def _sse_lines(tokens: list[str]) -> list[str]:
    lines = []
    for t in tokens:
        lines.append(f'data: {{"choices":[{{"delta":{{"content":"{t}"}}}}]}}')
        lines.append("")  # blank line between events
    lines.append("data: [DONE]")
    return lines


def test_streaming_parses_content_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    @contextmanager
    def fake_stream(method, url, json, timeout):
        captured["url"] = url
        captured["payload"] = json
        yield _FakeStreamResponse(_sse_lines(["Hello", " ", "world"]))

    monkeypatch.setattr("app.services.llm.providers.openai_compatible.httpx.stream", fake_stream)
    provider = OpenAICompatibleProvider(base_url="http://x/v1", model="m")

    out = list(provider.complete([{"role": "user", "content": "hi"}], stream=True))
    assert "".join(out) == "Hello world"
    assert captured["url"] == "http://x/v1/chat/completions"
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["model"] == "m"


def test_streaming_ignores_malformed_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def fake_stream(method, url, json, timeout):
        yield _FakeStreamResponse(
            [
                "event: ping",
                "data: not-json",
                'data: {"choices":[{"delta":{}}]}',  # no content
                'data: {"choices":[{"delta":{"content":"ok"}}]}',
                "data: [DONE]",
                'data: {"choices":[{"delta":{"content":"after done"}}]}',
            ]
        )

    monkeypatch.setattr("app.services.llm.providers.openai_compatible.httpx.stream", fake_stream)
    provider = OpenAICompatibleProvider(base_url="http://x/v1", model="m")
    assert list(provider.complete([{"role": "user", "content": "hi"}])) == ["ok"]


def test_non_streaming_returns_full_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return {"choices": [{"message": {"content": "full answer"}}]}

    monkeypatch.setattr(
        "app.services.llm.providers.openai_compatible.httpx.post",
        lambda url, json, timeout: _Resp(),
    )
    provider = OpenAICompatibleProvider(base_url="http://x/v1", model="m")
    assert list(provider.complete([{"role": "user", "content": "hi"}], stream=False)) == [
        "full answer"
    ]


def test_get_llm_provider_selects_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    get_settings.cache_clear()
    assert isinstance(get_llm_provider(), OllamaProvider)

    monkeypatch.setenv("LLM_PROVIDER", "vllm")
    get_settings.cache_clear()
    assert isinstance(get_llm_provider(), VLLMProvider)

    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_llm_provider()
    get_settings.cache_clear()


def test_json_schema_sets_response_format() -> None:
    provider = OpenAICompatibleProvider(base_url="http://x/v1", model="m")
    payload = provider._payload(
        [{"role": "user", "content": "x"}], stream=False, json_schema={"type": "object"}
    )
    assert payload["response_format"]["type"] == "json_schema"


def test_ollama_disables_reasoning_but_vllm_does_not() -> None:
    # Qwen3.5 on Ollama is a reasoning model; without this it burns hidden thinking tokens and
    # intermittently returns empty content (which surfaces as a spurious refusal).
    msgs = [{"role": "user", "content": "x"}]
    ollama = OllamaProvider(base_url="http://x/v1", model="m")._payload(msgs, False, None)
    assert ollama["reasoning_effort"] == "none"
    vllm = VLLMProvider(base_url="http://x/v1", model="m")._payload(msgs, False, None)
    assert "reasoning_effort" not in vllm

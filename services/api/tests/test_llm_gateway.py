from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import llm_gateway as gateway_module
from app.core.llm_gateway import LLMGateway


def _json_response(content: str = '{"status":"ok"}') -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.mark.asyncio
async def test_openai_gpt5_uses_max_completion_tokens(monkeypatch):
    create = AsyncMock(return_value=_json_response())
    gateway = LLMGateway()
    gateway._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    monkeypatch.setattr(gateway_module.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(gateway_module.settings, "anthropic_api_key", "")
    monkeypatch.setattr(gateway_module.settings, "llm_max_tokens", 1234)

    result = await gateway.call(
        system_prompt="Return JSON.",
        user_message="Hello",
        provider="openai",
        model="gpt-5.5",
    )

    kwargs = create.await_args.kwargs
    assert result == {"status": "ok"}
    assert kwargs["max_completion_tokens"] == 1234
    assert "max_tokens" not in kwargs
    assert "temperature" not in kwargs


@pytest.mark.asyncio
async def test_openai_legacy_models_keep_chat_completion_params(monkeypatch):
    create = AsyncMock(return_value=_json_response())
    gateway = LLMGateway()
    gateway._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    monkeypatch.setattr(gateway_module.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(gateway_module.settings, "anthropic_api_key", "")
    monkeypatch.setattr(gateway_module.settings, "llm_max_tokens", 777)
    monkeypatch.setattr(gateway_module.settings, "llm_temperature", 0.3)

    await gateway.call(
        system_prompt="Return JSON.",
        user_message="Hello",
        provider="openai",
        model="gpt-4o-mini",
    )

    kwargs = create.await_args.kwargs
    assert kwargs["max_tokens"] == 777
    assert kwargs["temperature"] == 0.3
    assert "max_completion_tokens" not in kwargs


@pytest.mark.asyncio
async def test_unavailable_fallback_provider_is_skipped(monkeypatch):
    create = AsyncMock(side_effect=TypeError("primary failure"))
    gateway = LLMGateway()
    gateway._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    monkeypatch.setattr(gateway_module.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(gateway_module.settings, "anthropic_api_key", "")
    monkeypatch.setattr(gateway_module.settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(gateway_module.settings, "llm_fallback_model", "claude-test")

    with pytest.raises(TypeError, match="primary failure"):
        await gateway.call(
            system_prompt="Return JSON.",
            user_message="Hello",
            provider="openai",
            model="gpt-4o-mini",
        )

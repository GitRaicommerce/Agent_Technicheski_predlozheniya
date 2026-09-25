"""WP-01 acceptance: runtime model policy by role (T-21, T-23; cards K-22, K-24)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import llm_gateway as gateway_module
from app.core import model_policy
from app.core.llm_gateway import (
    LLMGateway,
    LLMModelUnavailableError,
    collect_llm_calls,
)
from app.core.model_policy import ModelPolicyError, ROLE_BY_AGENT

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _response(content: str = '{"status":"ok"}', usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason="stop"
            )
        ],
        usage=usage,
    )


def _openai_gateway(create: AsyncMock) -> LLMGateway:
    gateway = LLMGateway()
    gateway._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return gateway


@pytest.fixture
def roles_mode(monkeypatch):
    s = gateway_module.settings
    monkeypatch.setattr(s, "llm_role_policy_mode", "roles")
    monkeypatch.setattr(s, "llm_role_policy", "")
    monkeypatch.setattr(s, "llm_default_provider", "openai")
    monkeypatch.setattr(s, "openai_api_key", "sk-test")
    monkeypatch.setattr(s, "anthropic_api_key", "")
    monkeypatch.setattr(s, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(s, "llm_fallback_model", "claude-test")
    monkeypatch.setattr(s, "llm_max_tokens", 4096)


def test_every_agent_label_in_code_has_an_explicit_role():
    labels: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        labels.update(re.findall(r'agent="([a-z0-9_]+)"', path.read_text(encoding="utf-8")))
    labels.discard("")
    missing = sorted(label for label in labels if label not in ROLE_BY_AGENT)
    assert not missing, f"agent labels without a model role: {missing}"


EXPECTED_ROLES = {
    "understanding_map": ("gpt-6-astra", "xhigh"),
    "understanding_proposal_audit": ("gpt-6-astra", "xhigh"),
    "content_plan_author": ("gpt-6-astra", "xhigh"),
    "plan_audit_extract": ("gpt-6-astra", "xhigh"),
    "plan_audit_compare": ("gpt-6-astra", "xhigh"),
    "drafting": ("gpt-6-sol", "high"),
    "drafting_complex": ("gpt-6-astra", "xhigh"),
    "criteria_verifier": ("gpt-6-astra", "xhigh"),
    "consistency_claims": ("gpt-6-astra", "xhigh"),
    "consistency_conflicts": ("gpt-6-astra", "xhigh"),
    "verifier": ("gpt-6-astra", "xhigh"),
    "schedule": ("gpt-6-astra", "high"),
    "legislation": ("gpt-6-astra", "high"),
    "orchestrator": ("gpt-6-sol", "medium"),
    "examples": ("gpt-6-sol", "medium"),
    "tender_struct": ("gpt-6-astra", "xhigh"),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("agent,expected", sorted(EXPECTED_ROLES.items()))
async def test_roles_mode_sends_the_role_model_and_effort(roles_mode, agent, expected):
    create = AsyncMock(return_value=_response())
    gateway = _openai_gateway(create)

    await gateway.call(system_prompt="Return JSON.", user_message="x", agent=agent)

    kwargs = create.await_args.kwargs
    assert kwargs["model"] == expected[0]
    assert kwargs["extra_body"] == {"reasoning_effort": expected[1]}
    assert kwargs["max_completion_tokens"] == 4096
    assert "temperature" not in kwargs
    assert "max_tokens" not in kwargs
    assert "ultra" not in json.dumps(kwargs, default=str)


@pytest.mark.asyncio
async def test_legacy_mode_keeps_the_global_model_without_effort(monkeypatch):
    s = gateway_module.settings
    monkeypatch.setattr(s, "llm_role_policy_mode", "legacy")
    monkeypatch.setattr(s, "llm_role_policy", "")
    monkeypatch.setattr(s, "llm_default_model", "gpt-5.6")
    monkeypatch.setattr(s, "openai_api_key", "sk-test")
    create = AsyncMock(return_value=_response())
    gateway = _openai_gateway(create)

    await gateway.call(system_prompt="Return JSON.", agent="understanding_map")

    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "gpt-5.6"
    assert "extra_body" not in kwargs


@pytest.mark.asyncio
async def test_unknown_agent_label_is_an_explicit_error(roles_mode):
    create = AsyncMock(return_value=_response())
    gateway = _openai_gateway(create)

    with pytest.raises(ModelPolicyError, match="непознат agent"):
        await gateway.call(system_prompt="x", agent="made_up_role")
    create.assert_not_awaited()


@pytest.mark.parametrize(
    "override,message",
    [
        ({"understanding": {"effort": "ultra"}}, "Невалидно reasoning effort"),
        ({"understanding": {"effort": "none"}}, "не се поддържа"),
        ({"nonexistent_role": {"model": "x"}}, "непозната роля"),
    ],
)
def test_invalid_policy_overrides_are_rejected(roles_mode, monkeypatch, override, message):
    monkeypatch.setattr(gateway_module.settings, "llm_role_policy", json.dumps(override))
    with pytest.raises(ModelPolicyError, match=message):
        model_policy.validate_policy()


def test_sol_supports_effort_none(roles_mode, monkeypatch):
    monkeypatch.setattr(
        gateway_module.settings,
        "llm_role_policy",
        json.dumps({"routing": {"model": "gpt-6-sol", "effort": "none"}}),
    )
    assert model_policy.profile_for_role("routing").effort == "none"


@pytest.mark.asyncio
async def test_critical_role_is_not_silently_downgraded_when_key_missing(
    roles_mode, monkeypatch
):
    s = gateway_module.settings
    monkeypatch.setattr(s, "openai_api_key", "")
    monkeypatch.setattr(s, "anthropic_api_key", "sk-ant-test")
    gateway = LLMGateway()
    gateway._call_provider = AsyncMock(return_value='{"ok": true}')

    with pytest.raises(LLMModelUnavailableError, match="не се понижават"):
        await gateway.call(system_prompt="x", agent="criteria_verifier")
    gateway._call_provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_critical_role_primary_failure_does_not_use_global_fallback(
    roles_mode, monkeypatch
):
    monkeypatch.setattr(gateway_module.settings, "anthropic_api_key", "sk-ant-test")
    gateway = LLMGateway()
    gateway._call_provider = AsyncMock(side_effect=RuntimeError("provider down"))

    with pytest.raises(RuntimeError, match="provider down"):
        await gateway.call(system_prompt="x", agent="understanding_map")
    # The gateway retries the same model; it never switches to the fallback.
    models = {
        (call.kwargs["provider"], call.kwargs["model"])
        for call in gateway._call_provider.await_args_list
    }
    assert models == {("openai", "gpt-6-astra")}


@pytest.mark.asyncio
async def test_explicit_quality_equivalent_fallback_is_used_and_recorded(
    roles_mode, monkeypatch
):
    s = gateway_module.settings
    monkeypatch.setattr(s, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(
        s,
        "llm_role_policy",
        json.dumps(
            {
                "verification": {
                    "fallback_provider": "anthropic",
                    "fallback_model": "claude-equivalent",
                }
            }
        ),
    )
    gateway = LLMGateway()
    gateway._call_provider = AsyncMock(
        side_effect=[RuntimeError("provider down"), '{"ok": true}']
    )

    with collect_llm_calls() as records:
        result = await gateway.call(system_prompt="x", agent="criteria_verifier")

    assert result == {"ok": True}
    second = gateway._call_provider.await_args_list[1].kwargs
    assert (second["provider"], second["model"]) == ("anthropic", "claude-equivalent")
    assert records[0]["fallback_used"] is True
    assert records[0]["requested_model"] == "gpt-6-astra"
    assert records[0]["actual_model"] == "claude-equivalent"


@pytest.mark.asyncio
async def test_non_critical_role_keeps_the_legacy_fallback(roles_mode, monkeypatch):
    monkeypatch.setattr(gateway_module.settings, "anthropic_api_key", "sk-ant-test")
    gateway = LLMGateway()
    gateway._call_provider = AsyncMock(
        side_effect=[RuntimeError("provider down"), '{"ok": true}']
    )

    result = await gateway.call(system_prompt="x", agent="orchestrator")

    assert result == {"ok": True}
    assert gateway._call_provider.await_args_list[1].kwargs["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_json_repair_uses_the_provider_that_returned_broken_json(
    roles_mode, monkeypatch
):
    """T-21: primary fails, fallback returns broken JSON, repair via fallback."""
    monkeypatch.setattr(gateway_module.settings, "anthropic_api_key", "sk-ant-test")
    gateway = LLMGateway()
    gateway._call_provider = AsyncMock(
        side_effect=[RuntimeError("primary down"), "{broken", '{"fixed": true}']
    )

    with collect_llm_calls() as records:
        result = await gateway.call(system_prompt="x", agent="examples")

    assert result == {"fixed": True}
    repair = gateway._call_provider.await_args_list[2].kwargs
    assert (repair["provider"], repair["model"]) == ("anthropic", "claude-test")
    assert records[0]["json_repaired"] is True
    assert records[0]["actual_provider"] == "anthropic"


@pytest.mark.asyncio
async def test_call_records_capture_usage_and_keep_unknown_usage_unknown(roles_mode):
    usage = SimpleNamespace(
        prompt_tokens=120,
        completion_tokens=40,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=25),
    )
    create = AsyncMock(side_effect=[_response(usage=usage), _response(usage=None)])
    gateway = _openai_gateway(create)

    with collect_llm_calls() as outer:
        with collect_llm_calls() as inner:
            await gateway.call(system_prompt="x", agent="drafting")
        await gateway.call(system_prompt="x", agent="drafting")

    assert len(inner) == 1 and len(outer) == 2
    assert inner[0]["usage"] == {
        "input_tokens": 120,
        "output_tokens": 40,
        "reasoning_tokens": 25,
    }
    assert inner[0]["role"] == "drafting_routine"
    assert inner[0]["requested_effort"] == "high"
    assert outer[1]["usage"] is None


@pytest.mark.asyncio
async def test_repair_inherits_writer_role(roles_mode):
    create = AsyncMock(return_value=_response())
    gateway = _openai_gateway(create)

    await gateway.call(
        system_prompt="x",
        agent="drafting_calendar_guard",
        role_override="drafting_complex",
    )

    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "gpt-6-astra"
    assert kwargs["extra_body"] == {"reasoning_effort": "xhigh"}


def test_gpt6_uses_completion_token_limit():
    assert gateway_module._uses_completion_token_limit("gpt-6-sol")
    assert gateway_module._uses_completion_token_limit("gpt-6-astra")
    assert not gateway_module._uses_completion_token_limit("gpt-4o-mini")

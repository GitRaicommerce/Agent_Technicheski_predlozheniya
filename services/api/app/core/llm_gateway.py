"""
LLM Gateway — единен интерфейс за OpenAI и Anthropic.
Смяната на provider/модел не изисква промяна на бизнес логиката.

Моделът и reasoning effort се избират по роля (``app.core.model_policy``):
всяко извикване подава ``agent`` етикет, който се съпоставя с роля и профил.
Критичните роли не падат тихо към по-слаб модел; JSON поправката използва
доставчика, който реално е върнал повредения отговор.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import time
import uuid
from typing import Any, Iterator

import structlog
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.model_policy import (
    ModelPolicyError,
    ModelProfile,
    explicit_profile,
    policy_mode,
    policy_version,
    resolve_profile,
)

log = structlog.get_logger()


class LLMNotConfiguredError(Exception):
    """Raised when no LLM API key is configured."""
    pass


class LLMModelUnavailableError(LLMNotConfiguredError):
    """The role's configured model cannot be reached and no approved fallback exists."""

    pass


class LLMOutputTruncatedError(RuntimeError):
    """Raised when retrying unchanged input cannot overcome the output cap."""

    pass


# Active call-record collectors for the current logical operation (see
# collect_llm_calls). A tuple so collectors nest: a job-level collector and a
# per-generation collector both receive the same record.
_call_records: contextvars.ContextVar[tuple[list[dict[str, Any]], ...]] = (
    contextvars.ContextVar("llm_call_records", default=())
)
# Usage of the most recent provider response in this task.
_last_usage: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "llm_last_usage", default=None
)


@contextlib.contextmanager
def collect_llm_calls() -> Iterator[list[dict[str, Any]]]:
    """Collect a record of every LLM call made inside the block.

    Records hold requested and actual provider/model/effort, role, policy
    version, latency and returned token usage. Unknown usage stays ``None``;
    it is never reported as zero cost.
    """
    records: list[dict[str, Any]] = []
    token = _call_records.set((*_call_records.get(), records))
    try:
        yield records
    finally:
        _call_records.reset(token)


def _record(entry: dict[str, Any]) -> None:
    log.info("llm_call_record", **entry)
    for records in _call_records.get():
        records.append(entry)


class LLMGateway:
    def __init__(self):
        self._openai_client = None
        self._anthropic_client = None

    def _get_openai(self):
        if self._openai_client is None:
            from openai import AsyncOpenAI

            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def _get_anthropic(self):
        if self._anthropic_client is None:
            from anthropic import AsyncAnthropic

            self._anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._anthropic_client

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(
            (LLMNotConfiguredError, LLMOutputTruncatedError, ModelPolicyError)
        ),
        reraise=True,
    )
    async def call(
        self,
        system_prompt: str,
        user_message: str = "",
        agent: str = "",
        trace_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list | None = None,
        role_override: str | None = None,
    ) -> dict[str, Any]:
        """
        Извиква LLM и върна валиден JSON dict.
        При невалиден JSON прави еднократен repair call (без промяна на смисъла)
        през доставчика, който реално е върнал отговора.
        Ако е подаден `messages` (история), той се ползва вместо единичния user_message.
        ``role_override`` позволява на поправка да наследи ролята на писателя.
        """
        trace_id = trace_id or str(uuid.uuid4())
        if model:
            profile = explicit_profile(
                provider or settings.llm_default_provider, model
            )
        else:
            profile = resolve_profile(agent, role_override)

        if not _provider_has_key("openai") and not _provider_has_key("anthropic"):
            raise LLMNotConfiguredError(
                "LLM API ключовете не са конфигурирани. "
                "Моля добавете OPENAI_API_KEY или ANTHROPIC_API_KEY в .env файла."
            )

        started = time.monotonic()
        actual = _primary_target(profile)
        fallback_used = actual != (profile.provider, profile.model, profile.effort)
        if fallback_used:
            log.warning(
                "llm_primary_key_missing_using_approved_fallback",
                agent=agent,
                role=profile.role,
                fallback_provider=actual[0],
                fallback_model=actual[1],
                trace_id=trace_id,
            )

        try:
            raw_text = await self._call_provider(
                provider=actual[0],
                model=actual[1],
                system_prompt=system_prompt,
                user_message=user_message,
                messages=messages,
                effort=actual[2],
            )
        except LLMOutputTruncatedError:
            # Identical input cannot fit a fallback either; callers split input.
            raise
        except Exception as primary_exc:
            fallback = _fallback_target(profile)
            if fallback is None or fallback == actual:
                raise
            log.warning(
                "llm_fallback",
                agent=agent,
                role=profile.role,
                primary_provider=actual[0],
                primary_model=actual[1],
                fallback_provider=fallback[0],
                fallback_model=fallback[1],
                error=str(primary_exc),
                trace_id=trace_id,
            )
            actual = fallback
            fallback_used = True
            raw_text = await self._call_provider(
                provider=actual[0],
                model=actual[1],
                system_prompt=system_prompt,
                user_message=user_message,
                messages=messages,
                effort=actual[2],
            )

        usage = _last_usage.get()
        json_repaired = False
        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError:
            log.warning(
                "llm_json_repair",
                agent=agent,
                provider=actual[0],
                model=actual[1],
                trace_id=trace_id,
            )
            # K-22: repair through the provider that actually returned the text.
            result = await self._repair_json(
                provider=actual[0],
                model=actual[1],
                effort=actual[2],
                broken_text=raw_text,
                trace_id=trace_id,
            )
            json_repaired = True

        _record(
            {
                "agent": agent,
                "role": profile.role,
                "policy_mode": policy_mode(),
                "policy_version": policy_version(),
                "critical": profile.critical,
                "requested_provider": profile.provider,
                "requested_model": profile.model,
                "requested_effort": profile.effort,
                "actual_provider": actual[0],
                "actual_model": actual[1],
                "actual_effort": actual[2],
                "fallback_used": fallback_used,
                "json_repaired": json_repaired,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "usage": usage,
                "trace_id": trace_id,
            }
        )
        return result

    async def _call_provider(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_message: str = "",
        messages: list | None = None,
        effort: str | None = None,
    ) -> str:
        # Build messages list: use provided history or single user_message
        built_messages = (
            messages if messages else [{"role": "user", "content": user_message}]
        )
        _last_usage.set(None)

        if provider == "openai":
            client = self._get_openai()
            request_kwargs: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    *built_messages,
                ],
                "response_format": {"type": "json_object"},
            }
            if _uses_completion_token_limit(model):
                # Reasoning models: no sampling parameters; effort goes in the
                # request body so older SDK releases pass it through unchanged.
                request_kwargs["max_completion_tokens"] = settings.llm_max_tokens
                if effort:
                    request_kwargs["extra_body"] = {"reasoning_effort": effort}
            else:
                request_kwargs["max_tokens"] = settings.llm_max_tokens
                request_kwargs["temperature"] = settings.llm_temperature

            response = await client.chat.completions.create(
                **request_kwargs,
            )
            _last_usage.set(_openai_usage(response))
            choice = response.choices[0]
            if choice.finish_reason == "length":
                raise LLMOutputTruncatedError(
                    "LLM response was truncated by the output token limit."
                )
            return choice.message.content or ""

        elif provider == "anthropic":
            client = self._get_anthropic()
            response = await client.messages.create(
                model=model,
                system=system_prompt,
                messages=built_messages,
                max_tokens=settings.llm_max_tokens,
            )
            _last_usage.set(_anthropic_usage(response))
            if response.stop_reason == "max_tokens":
                raise LLMOutputTruncatedError(
                    "LLM response was truncated by the output token limit."
                )
            return response.content[0].text

        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    async def _repair_json(
        self,
        provider: str,
        model: str,
        broken_text: str,
        trace_id: str,
        effort: str | None = None,
    ) -> dict[str, Any]:
        repair_prompt = (
            "The following text should be a valid JSON object but is malformed. "
            "Return ONLY the corrected JSON object, without any explanation or markdown. "
            "Do NOT change the meaning or content."
        )
        fixed = await self._call_provider(
            provider=provider,
            model=model,
            system_prompt=repair_prompt,
            user_message=broken_text,
            effort=effort,
        )
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"LLM JSON repair failed (trace_id={trace_id}): {e}"
            ) from e


llm_gateway = LLMGateway()


def _provider_has_key(provider: str) -> bool:
    if provider == "openai":
        return bool(settings.openai_api_key and settings.openai_api_key.strip())
    if provider == "anthropic":
        return bool(settings.anthropic_api_key and settings.anthropic_api_key.strip())
    return False


Target = tuple[str, str, "str | None"]


def _fallback_target(profile: ModelProfile) -> Target | None:
    if not (profile.fallback_provider and profile.fallback_model):
        return None
    if not _provider_has_key(profile.fallback_provider):
        return None
    return (profile.fallback_provider, profile.fallback_model, profile.fallback_effort)


def _primary_target(profile: ModelProfile) -> Target:
    """Primary target, or an approved fallback when the primary key is missing."""
    if _provider_has_key(profile.provider):
        return (profile.provider, profile.model, profile.effort)
    fallback = _fallback_target(profile)
    if fallback is not None:
        return fallback
    raise LLMModelUnavailableError(
        f"Моделът за роля '{profile.role}' ({profile.provider}/{profile.model}) "
        "не е достъпен: липсва API ключ за доставчика и няма одобрен "
        "равностоен резервен модел. Критичните роли не се понижават тихо."
    )


def _openai_usage(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    details = getattr(usage, "completion_tokens_details", None)
    return {
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
        "reasoning_tokens": getattr(details, "reasoning_tokens", None)
        if details is not None
        else None,
    }


def _anthropic_usage(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "reasoning_tokens": None,
    }


def _uses_completion_token_limit(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith(("gpt-6", "gpt-5", "o1", "o3", "o4"))

"""
LLM Gateway — единен интерфейс за OpenAI и Anthropic.
Смяната на provider/модел не изисква промяна на бизнес логиката.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

log = structlog.get_logger()


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
        stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10)
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
    ) -> dict[str, Any]:
        """
        Извиква LLM и върна валиден JSON dict.
        При невалиден JSON прави еднократен repair call (без промяна на смисъла).
        Ако е подаден `messages` (история), той се ползва вместо единичния user_message.
        """
        trace_id = trace_id or str(uuid.uuid4())
        provider = provider or settings.llm_default_provider
        model = model or settings.llm_default_model

        log.info(
            "llm_call", agent=agent, provider=provider, model=model, trace_id=trace_id
        )

        raw_text = await self._call_provider(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_message=user_message,
            messages=messages,
        )

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            log.warning("llm_json_repair", agent=agent, trace_id=trace_id)
            return await self._repair_json(
                provider=provider,
                model=model,
                broken_text=raw_text,
                trace_id=trace_id,
            )

    async def _call_provider(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_message: str = "",
        messages: list | None = None,
    ) -> str:
        # Build messages list: use provided history or single user_message
        built_messages = (
            messages if messages else [{"role": "user", "content": user_message}]
        )

        if provider == "openai":
            client = self._get_openai()
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *built_messages,
                ],
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content

        elif provider == "anthropic":
            client = self._get_anthropic()
            response = await client.messages.create(
                model=model,
                system=system_prompt,
                messages=built_messages,
                max_tokens=settings.llm_max_tokens,
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
        )
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"LLM JSON repair failed (trace_id={trace_id}): {e}"
            ) from e


llm_gateway = LLMGateway()

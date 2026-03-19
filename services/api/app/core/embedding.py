"""
Embedding service — генерира text embeddings чрез OpenAI.
Използва се при ingest (записване) и при vector similarity search в агентите.
"""

from __future__ import annotations

import structlog

from app.core.config import settings

log = structlog.get_logger()

_BATCH_SIZE = 100  # OpenAI embedding API limit per request


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Генерира embeddings за списък от текстове (batched).
    Връща списък от float списъци в същия ред.
    При липса на API ключ или грешка — връща списък от None.
    """
    if not settings.openai_api_key:
        log.warning("embedding_skipped_no_api_key")
        return [[] for _ in texts]

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    result: list[list[float]] = []

    for i in range(0, len(texts), _BATCH_SIZE):
        batch = [t[:8000] for t in texts[i : i + _BATCH_SIZE]]  # token safety trim
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
        )
        result.extend(item.embedding for item in response.data)

    return result


async def embed_query(text: str) -> list[float]:
    """Генерира embedding за единична заявка."""
    results = await embed_texts([text])
    return results[0]

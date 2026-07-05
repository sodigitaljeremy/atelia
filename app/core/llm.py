"""Couche d'abstraction LLM via LiteLLM.

Tout appel modèle passe par ici : le provider se change en config
(LLM_MODEL / EMBED_MODEL dans .env), ex. Mistral -> Claude (ADR-001).
Chaque appel remonte latence et tokens consommés (observabilité coûts).
"""

import time

from litellm import acompletion, aembedding

from app.core.config import settings


async def complete(prompt: str, max_tokens: int = 64) -> dict:
    start = time.perf_counter()
    response = await acompletion(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        api_key=settings.mistral_api_key or None,
    )
    return {
        "model": settings.llm_model,
        "content": response.choices[0].message.content,
        "latency_ms": round((time.perf_counter() - start) * 1000),
        "tokens": {
            "prompt": response.usage.prompt_tokens,
            "completion": response.usage.completion_tokens,
        },
    }


async def embed(text: str) -> dict:
    start = time.perf_counter()
    response = await aembedding(
        model=settings.embed_model,
        input=[text],
        api_key=settings.mistral_api_key or None,
    )
    return {
        "model": settings.embed_model,
        "dimensions": len(response.data[0]["embedding"]),
        "latency_ms": round((time.perf_counter() - start) * 1000),
        "tokens": {"prompt": response.usage.prompt_tokens},
    }

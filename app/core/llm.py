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


async def complete_messages(
    messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 1024
) -> dict:
    """Appel chat multi-tours avec tool-use optionnel (format tools OpenAI standard).

    tool_choice="auto" : c'est le MODÈLE qui décide d'appeler un outil, jamais le code
    (vrai function-calling — ADR-104). Le champ `message` du retour est le message
    assistant brut, réinjectable tel quel dans l'historique de conversation.
    """
    start = time.perf_counter()
    response = await acompletion(
        model=settings.llm_model,
        messages=messages,
        tools=tools,
        tool_choice="auto" if tools else None,
        max_tokens=max_tokens,
        api_key=settings.mistral_api_key or None,
    )
    message = response.choices[0].message
    tool_calls = [
        {"id": call.id, "name": call.function.name, "arguments": call.function.arguments}
        for call in (message.tool_calls or [])
    ]
    return {
        "model": settings.llm_model,
        "message": message.model_dump(),
        "content": message.content,
        "tool_calls": tool_calls,
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

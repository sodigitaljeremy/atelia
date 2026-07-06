"""Génération de réponse citée (M2-b) — boucle RAG fermée au-dessus du retrieval M2-a.

Défense hors-corpus en DEUX couches :
1. un portier déterministe par seuil de similarité, AVANT tout appel LLM — il coupe les
   questions clairement hors domaine (gratuit, imparable) ;
2. le system prompt strict — pour les questions au vocabulaire proche du domaine dont la
   réponse n'est pas dans les passages (le seuil ne peut pas les distinguer).

Seuil calibré empiriquement le 06/07/2026 sur le corpus INCO (31 chunks, mistral-embed) :
- hors corpus : « TVA sur les conserves » 0.760 (!), « coupe du monde » 0.702, « licencier
  un salarié » 0.698 ;
- dans le corpus : « déclaration nutritionnelle » 0.844, « allergènes » 0.805, « taille de
  police » 0.735.
→ 0.72 rejette le hors-domaine franc sans sacrifier l'in-corpus mesuré ; le cas « TVA »
(proche du domaine) passe le portier et doit être refusé par le prompt.
"""

import logging

from app.core import llm
from app.modules.compliance import repository

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.72
TOP_N = 5

NO_ANSWER = "Je ne trouve pas cette information dans le règlement indexé."

SYSTEM_PROMPT = """Tu es l'assistant conformité de la plateforme AtelIA. Tu réponds à des
questions sur l'étiquetage alimentaire à partir du règlement (UE) n° 1169/2011 (INCO).

RÈGLES ABSOLUES :
- Réponds UNIQUEMENT à partir des passages fournis ci-dessous. N'utilise aucune
  connaissance externe.
- Si la réponse n'est pas dans les passages, dis clairement : « Je ne trouve pas cette
  information dans le règlement indexé. » N'invente jamais.
- Cite systématiquement les articles sur lesquels tu t'appuies (ex. « selon l'Article 21 »,
  « l'Annexe II liste... »). Chaque affirmation doit être rattachable à un passage fourni.
- Réponds en français, de façon concise et opérationnelle (3-8 phrases) : la règle,
  ses conditions, ses références. Pas de paraphrase intégrale des passages."""


def _build_user_message(question: str, chunks: list[dict]) -> str:
    passages = "\n\n".join(f"[{chunk['ref_article']}]\n{chunk['contenu']}" for chunk in chunks)
    return (
        f"PASSAGES DU RÈGLEMENT (seules sources autorisées) :\n\n{passages}\n\n"
        f"QUESTION : {question}"
    )


async def answer(question: str) -> dict:
    """Chaîne RAG complète. Retourne {answer, sources, hors_corpus, error}.

    Les sources affichées sont les passages réellement passés au LLM (retrieval),
    jamais une liste produite par le modèle — même principe d'ancrage que le score M3.
    """
    chunks = await repository.search_chunks(question, limit=TOP_N)
    relevant = [c for c in chunks if c["similarite"] >= SIMILARITY_THRESHOLD]
    if not relevant:
        best = max((c["similarite"] for c in chunks), default=0)
        logger.info(
            "RAG hors-corpus (portier) : meilleur score %.3f < %s", best, SIMILARITY_THRESHOLD
        )
        return {"answer": NO_ANSWER, "sources": [], "hors_corpus": True, "error": None}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(question, relevant)},
    ]
    try:
        reply = await llm.complete_messages(messages, max_tokens=1024)
    except Exception:  # rate limit, réseau… : message propre, jamais de 500
        logger.warning("RAG : appel LLM échoué", exc_info=True)
        return {
            "answer": None,
            "sources": [],
            "hors_corpus": False,
            "error": "La génération a échoué (limite de débit ou indisponibilité du modèle) — "
            "réessayez dans quelques secondes.",
        }
    return {
        "answer": (reply["content"] or "").strip() or NO_ANSWER,
        "sources": relevant,
        "hors_corpus": False,
        "error": None,
    }

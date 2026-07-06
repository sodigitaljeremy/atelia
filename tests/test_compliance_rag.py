"""Tests de la boucle RAG (M2-b) — retrieval ET LLM mockés, AUCUN réseau.

Le test central : hors corpus, l'assistant répond « je ne trouve pas » SANS que
le LLM soit appelé (le mock lève s'il est sollicité).
"""

import asyncio

import pytest

from app.core import llm
from app.modules.compliance import rag, repository

CHUNK_ALLERGENES = {
    "ref_article": "Annexe II",
    "contenu": "Annexe II — SUBSTANCES OU PRODUITS PROVOQUANT DES ALLERGIES\n1. Céréales contenant du gluten…",
    "titre": "Règlement INCO",
    "source_celex": "02011R1169",
    "similarite": 0.80,
}
CHUNK_FAIBLE = {**CHUNK_ALLERGENES, "ref_article": "Article 23", "similarite": 0.55}


def _fake_search(chunks):
    async def fake(query, limit=5):
        return chunks

    return fake


def _fake_llm(content):
    async def fake(messages, tools=None, max_tokens=1024):
        return {"content": content, "tool_calls": [], "message": {}}

    return fake


def test_question_dans_le_corpus_reponse_citee_et_sources(monkeypatch):
    captured = {}

    async def fake_llm(messages, tools=None, max_tokens=1024):
        captured["messages"] = messages
        return {
            "content": "Selon l'Annexe II, quatorze catégories doivent être déclarées.",
            "tool_calls": [],
            "message": {},
        }

    monkeypatch.setattr(repository, "search_chunks", _fake_search([CHUNK_ALLERGENES, CHUNK_FAIBLE]))
    monkeypatch.setattr(llm, "complete_messages", fake_llm)
    result = asyncio.run(rag.answer("quels allergènes déclarer ?"))

    assert result["hors_corpus"] is False and result["error"] is None
    assert "Annexe II" in result["answer"]
    # les sources = les passages RÉELLEMENT passés au LLM (au-dessus du seuil uniquement)
    assert [s["ref_article"] for s in result["sources"]] == ["Annexe II"]
    # le passage sous le seuil (0.55) n'est PAS parti au LLM
    assert "Article 23" not in captured["messages"][1]["content"]
    assert "Céréales contenant du gluten" in captured["messages"][1]["content"]
    # le grounding est bien exigé par le system prompt
    assert "UNIQUEMENT" in captured["messages"][0]["content"]


def test_hors_corpus_refus_sans_appel_llm(monkeypatch):
    async def llm_interdit(messages, tools=None, max_tokens=1024):
        pytest.fail("le LLM ne doit JAMAIS être appelé quand aucun passage ne passe le seuil")

    monkeypatch.setattr(repository, "search_chunks", _fake_search([CHUNK_FAIBLE]))
    monkeypatch.setattr(llm, "complete_messages", llm_interdit)
    result = asyncio.run(rag.answer("qui a gagné la coupe du monde ?"))

    assert result["hors_corpus"] is True
    assert result["answer"] == rag.NO_ANSWER
    assert result["sources"] == []


def test_seuil_frontiere(monkeypatch):
    au_seuil = {**CHUNK_ALLERGENES, "similarite": rag.SIMILARITY_THRESHOLD}
    monkeypatch.setattr(repository, "search_chunks", _fake_search([au_seuil]))
    monkeypatch.setattr(llm, "complete_messages", _fake_llm("Réponse."))
    result = asyncio.run(rag.answer("question"))
    assert result["hors_corpus"] is False  # >= seuil : on répond


def test_erreur_llm_message_propre(monkeypatch):
    async def failing(messages, tools=None, max_tokens=1024):
        raise RuntimeError("Rate limit exceeded")

    monkeypatch.setattr(repository, "search_chunks", _fake_search([CHUNK_ALLERGENES]))
    monkeypatch.setattr(llm, "complete_messages", failing)
    result = asyncio.run(rag.answer("quels allergènes ?"))
    assert "réessayez" in result["error"]
    assert result["answer"] is None


def test_reponse_vide_du_llm_devient_je_ne_sais_pas(monkeypatch):
    monkeypatch.setattr(repository, "search_chunks", _fake_search([CHUNK_ALLERGENES]))
    monkeypatch.setattr(llm, "complete_messages", _fake_llm(""))
    result = asyncio.run(rag.answer("question"))
    assert result["answer"] == rag.NO_ANSWER

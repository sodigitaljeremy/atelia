"""Tests de la boucle agentique — LLM et API mockés, AUCUN réseau.

On monkeypatche llm.complete_messages (scénarios scriptés) et agent.search_companies :
on teste la mécanique de la boucle (tool_call → exécution → tool message → synthèse),
le garde-fou anti-boucle, la propagation d'erreur d'outil et le repli de parsing.
"""

import asyncio
import json

from app.core import llm
from app.modules.suppliers import agent
from app.modules.suppliers.client import SearchError

FICHE_EDF = {
    "nom": "ELECTRICITE DE FRANCE (EDF)",
    "siren": "552081317",
    "etat": "Active",
    "active": True,
    "naf": "35.11Z",
    "effectif": "10 000 salariés et plus",
    "creation": "1955-01-01",
    "siege": "PARIS",
    "dirigeants": [],
}

# Barème M3-b1 ajusté : actif ancien cohérent = 50 + 30 + 20 = 100 ; taille HORS critères
FINAL_JSON = json.dumps(
    {
        "synthese": "Entreprise active et ancienne, données officielles cohérentes.",
        "score": 100,
        "taille": "10 000 salariés et plus",
        "criteres": [
            {"critere": "État administratif", "points": 50, "justification": "Active"},
            {
                "critere": "Ancienneté",
                "points": 30,
                "justification": "créée en 1955, plus de 10 ans",
            },
            {
                "critere": "Cohérence des données",
                "points": 20,
                "justification": "SIREN présent (+10) et NAF présent (+10)",
            },
        ],
    },
    ensure_ascii=False,
)

# Règle éliminatoire : cessée → 0 partout, score 0
FINAL_JSON_CESSEE = json.dumps(
    {
        "synthese": "L'entreprise est cessée : statut éliminatoire, le score est de 0 "
        "quelles que soient l'ancienneté et la cohérence des données.",
        "score": 0,
        "taille": "non renseigné",
        "criteres": [
            {
                "critere": "État administratif",
                "points": 0,
                "justification": "Cessée — éliminatoire",
            },
            {
                "critere": "Ancienneté",
                "points": 0,
                "justification": "annulée par la règle éliminatoire",
            },
            {
                "critere": "Cohérence des données",
                "points": 0,
                "justification": "annulée par la règle éliminatoire",
            },
        ],
    },
    ensure_ascii=False,
)


def _tool_call_reply(call_id="call_abc123", query="EDF"):
    arguments = json.dumps({"query": query})
    return {
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "rechercher_entreprise", "arguments": arguments},
                }
            ],
        },
        "content": None,
        "tool_calls": [{"id": call_id, "name": "rechercher_entreprise", "arguments": arguments}],
    }


def _final_reply(content=FINAL_JSON):
    return {
        "message": {"role": "assistant", "content": content},
        "content": content,
        "tool_calls": [],
    }


def _scripted_llm(replies, seen_messages):
    """complete_messages mocké : rejoue les réponses dans l'ordre, capture les messages."""
    replies = list(replies)

    async def fake(messages, tools=None, max_tokens=1024):
        seen_messages.append([dict(m) for m in messages])
        return replies.pop(0)

    return fake


def test_boucle_nominale_tool_call_puis_synthese(monkeypatch):
    seen = []
    monkeypatch.setattr(
        llm, "complete_messages", _scripted_llm([_tool_call_reply(), _final_reply()], seen)
    )

    async def fake_search(query, **kwargs):
        assert query == "EDF"
        return [FICHE_EDF]

    monkeypatch.setattr(agent, "search_companies", fake_search)
    analysis = asyncio.run(agent.analyze("EDF"))

    assert analysis["error"] is None
    # actif ancien cohérent = 100 (50 état + 30 ancienneté + 20 cohérence), 3 critères
    assert analysis["result"]["score"] == 100
    assert len(analysis["result"]["criteres"]) == 3
    assert [c["critere"] for c in analysis["result"]["criteres"]] == [
        "État administratif",
        "Ancienneté",
        "Cohérence des données",
    ]
    # la taille est une info de contexte séparée, jamais un critère noté
    assert analysis["result"]["taille"] == "10 000 salariés et plus"
    assert all("aille" not in c["critere"] for c in analysis["result"]["criteres"])
    kinds = [step["kind"] for step in analysis["timeline"]]
    assert kinds == ["tool_call", "tool_result", "final"]
    # preuve du vrai tool-call : l'id émis par le modèle est tracé et propagé
    assert "call_abc123" in analysis["timeline"][0]["text"]
    tool_messages = [m for m in seen[1] if m.get("role") == "tool"]
    assert tool_messages[0]["tool_call_id"] == "call_abc123"
    assert "552081317" in tool_messages[0]["content"]


def test_garde_fou_anti_boucle_infinie(monkeypatch):
    # le modèle demande l'outil à chaque tour, sans jamais conclure
    replies = [_tool_call_reply(call_id=f"call_{i}") for i in range(agent.MAX_TURNS + 2)]
    monkeypatch.setattr(llm, "complete_messages", _scripted_llm(replies, []))

    async def fake_search(query, **kwargs):
        return [FICHE_EDF]

    monkeypatch.setattr(agent, "search_companies", fake_search)
    analysis = asyncio.run(agent.analyze("EDF"))

    assert analysis["error"] is not None and str(agent.MAX_TURNS) in analysis["error"]
    assert analysis["timeline"][-1]["kind"] == "stopped"
    # exactement MAX_TURNS appels LLM, pas un de plus
    assert sum(1 for s in analysis["timeline"] if s["kind"] == "tool_call") == agent.MAX_TURNS


def test_erreur_outil_transmise_au_modele_sans_crash(monkeypatch):
    seen = []
    monkeypatch.setattr(
        llm, "complete_messages", _scripted_llm([_tool_call_reply(), _final_reply()], seen)
    )

    async def failing_search(query, **kwargs):
        raise SearchError("L'API publique est injoignable pour le moment — réessayez plus tard.")

    monkeypatch.setattr(agent, "search_companies", failing_search)
    analysis = asyncio.run(agent.analyze("EDF"))

    assert analysis["error"] is None  # pas de crash : l'erreur est une donnée pour le modèle
    tool_messages = [m for m in seen[1] if m.get("role") == "tool"]
    assert "injoignable" in tool_messages[0]["content"]
    assert any("injoignable" in step["text"] for step in analysis["timeline"])


def _bodacc_call_reply(call_id="call_bodacc1", siren="552081317"):
    arguments = json.dumps({"siren": siren})
    return {
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "rechercher_procedures_bodacc", "arguments": arguments},
                }
            ],
        },
        "content": None,
        "tool_calls": [
            {"id": call_id, "name": "rechercher_procedures_bodacc", "arguments": arguments}
        ],
    }


def test_orchestration_deux_outils_enchaines(monkeypatch):
    """Le modèle enchaîne recherche → BODACC → synthèse : 3 tours, 2 tool_calls distincts."""
    seen = []
    monkeypatch.setattr(
        llm,
        "complete_messages",
        _scripted_llm([_tool_call_reply(), _bodacc_call_reply(), _final_reply()], seen),
    )

    async def fake_search(query, **kwargs):
        return [FICHE_EDF]

    procedures = [
        {
            "nature": "Jugement de conversion en liquidation judiciaire",
            "date_jugement": "2021-04-14",
            "date_parution": "2021-04-25",
            "tribunal": "TC Lille",
        }
    ]

    async def fake_bodacc(siren, **kwargs):
        assert siren == "552081317"  # le SIREN vient du 1er outil, réutilisé par le modèle
        return procedures

    monkeypatch.setattr(agent, "search_companies", fake_search)
    monkeypatch.setattr(agent, "search_procedures", fake_bodacc)
    analysis = asyncio.run(agent.analyze("EDF"))

    tool_calls = [s for s in analysis["timeline"] if s["kind"] == "tool_call"]
    assert len(tool_calls) == 2
    assert "rechercher_entreprise" in tool_calls[0]["text"]
    assert "rechercher_procedures_bodacc" in tool_calls[1]["text"]
    # la capture serveur alimente le bloc d'alerte depuis la donnée brute de l'API
    assert analysis["bodacc"]["consulted"] is True
    assert analysis["bodacc"]["procedures"] == procedures
    # les deux ToolMessages sont bien repartis au modèle avec leurs ids
    tool_messages = [m for m in seen[2] if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["call_abc123", "call_bodacc1"]


def test_bodacc_vide_capture_neutre(monkeypatch):
    monkeypatch.setattr(
        llm,
        "complete_messages",
        _scripted_llm([_bodacc_call_reply(), _final_reply()], []),
    )

    async def fake_bodacc(siren, **kwargs):
        return []

    monkeypatch.setattr(agent, "search_procedures", fake_bodacc)
    analysis = asyncio.run(agent.analyze("552081317"))

    assert analysis["bodacc"] == {"consulted": True, "procedures": [], "error": None}
    assert any("absence non probante" in s["text"] for s in analysis["timeline"])


def test_bodacc_non_consulte(monkeypatch):
    monkeypatch.setattr(llm, "complete_messages", _scripted_llm([_final_reply()], []))
    analysis = asyncio.run(agent.analyze("EDF"))
    assert analysis["bodacc"] is None


def test_erreur_llm_rend_un_message_propre_jamais_un_crash(monkeypatch):
    async def failing_llm(messages, tools=None, max_tokens=1024):
        raise RuntimeError("Rate limit exceeded")

    monkeypatch.setattr(llm, "complete_messages", failing_llm)
    analysis = asyncio.run(agent.analyze("EDF"))
    assert "réessayez" in analysis["error"]
    assert analysis["timeline"][-1]["kind"] == "stopped"


def test_la_nuance_bodacc_est_dans_le_prompt():
    prompt = agent.SYSTEM_PROMPT
    assert "absence non probante" in prompt
    assert "INTERDICTION de conclure" in prompt
    assert "n'entre PAS dans le score" in prompt
    assert "rechercher_procedures_bodacc" in prompt


def test_cessee_est_eliminatoire_score_zero(monkeypatch):
    monkeypatch.setattr(
        llm,
        "complete_messages",
        _scripted_llm(
            [_tool_call_reply(query="virgin stores"), _final_reply(content=FINAL_JSON_CESSEE)], []
        ),
    )

    async def fake_search(query, **kwargs):
        return [{**FICHE_EDF, "nom": "VIRGIN STORES", "etat": "Cessée", "active": False}]

    monkeypatch.setattr(agent, "search_companies", fake_search)
    analysis = asyncio.run(agent.analyze("virgin stores"))

    assert analysis["result"]["score"] == 0
    assert all(c["points"] == 0 for c in analysis["result"]["criteres"])
    assert "éliminatoire" in analysis["result"]["synthese"]


def test_le_bareme_du_prompt_est_le_nouveau():
    # garde-fou anti-régression : les règles imposées figurent bien dans le system prompt
    prompt = agent.SYSTEM_PROMPT
    assert "ÉLIMINATOIRE" in prompt and "score global est 0" in prompt
    assert "Active = 50" in prompt
    assert "plus de 10 ans = 30" in prompt and "3 à 10 ans = 20" in prompt
    assert "SIREN présent = 10" in prompt and "code NAF présent = 10" in prompt
    assert "n'est PAS un critère" in prompt  # taille hors barème


def test_repli_si_reponse_finale_non_json(monkeypatch):
    monkeypatch.setattr(
        llm,
        "complete_messages",
        _scripted_llm([_final_reply(content="Réponse en texte libre, sans JSON.")], []),
    )
    analysis = asyncio.run(agent.analyze("EDF"))
    assert analysis["result"] is None
    assert analysis["raw_answer"].startswith("Réponse en texte libre")
    assert analysis["error"] is None


def test_parse_final_tolere_le_texte_autour():
    content = 'Voici mon analyse :\n{"synthese": "ok", "score": 55, "criteres": []}\nVoilà.'
    parsed = agent._parse_final(content)
    assert parsed["score"] == 55


def test_parse_final_tolere_les_cles_accentuees_et_les_fences():
    # cas réellement observé avec Mistral : clés accentuées + bloc ```json
    content = (
        '```json\n{"synthèse": "ok", "score": 100, "taille": "x",\n'
        ' "critères": [{"critère": "État administratif", "points": 50, "justification": "j"}]}\n```'
    )
    parsed = agent._parse_final(content)
    assert parsed["synthese"] == "ok"
    assert parsed["criteres"][0]["critere"] == "État administratif"

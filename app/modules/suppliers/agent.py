"""Agent d'analyse fournisseur — vrai function-calling via la couche LLM du socle.

Boucle agentique : le MODÈLE décide d'appeler l'outil (tool_choice="auto", jamais
pré-appelé par le code), on exécute la vraie recherche M3-a, on lui renvoie le
résultat (même tool_call_id), il synthétise. Chaque tour est tracé dans une
timeline affichée à l'utilisateur.
"""

import json

from app.core import llm
from app.modules.suppliers.client import SearchError, search_companies

MAX_TURNS = 4  # garde-fou anti-boucle infinie

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rechercher_entreprise",
            "description": (
                "Recherche une entreprise française dans les registres officiels "
                "(RNE + Sirene, data publique de l'État). Retourne pour chaque résultat : "
                "dénomination, SIREN, état administratif (Active/Cessée), code NAF, "
                "tranche d'effectif, date de création, adresse du siège, dirigeants."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Nom de l'entreprise ou SIREN (9 chiffres, recherche directe)",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

SYSTEM_PROMPT = """Tu es l'analyste fournisseurs de la plateforme AtelIA. Tu évalues la fiabilité
administrative d'une entreprise française en t'appuyant EXCLUSIVEMENT sur l'outil
rechercher_entreprise (registres officiels RNE + Sirene).

RÈGLES D'ANCRAGE — ABSOLUES :
- Tu raisonnes UNIQUEMENT sur les données réellement renvoyées par l'outil.
- INTERDICTION d'inventer ou d'estimer : chiffre d'affaires, santé financière, solvabilité,
  rentabilité, notation, litiges. L'API ne fournit PAS ces informations.
- Toute information absente des données de l'outil : écris « non disponible ».
- Si l'outil renvoie une erreur ou aucun résultat, dis-le simplement, sans supposer.

GRILLE DE SCORE (0-100) — IMPOSÉE, tu ne la modifies pas :
- État administratif : Active = 40 points ; Cessée = 0 point.
- Ancienneté (date de création) : plus de 20 ans = 25 ; 5 à 20 ans = 15 ; moins de 5 ans = 5 ;
  non disponible = 0.
- Taille (tranche d'effectif) : 50 salariés ou plus = 20 ; moins de 50 = 10 ; non renseigné = 0.
- Cohérence des données (SIREN ET code NAF présents) = 15 ; sinon 0.
Le score est la somme exacte de ces contributions.

RÉPONSE FINALE — STRICTEMENT ce JSON, sans texte autour ni markdown :
{"synthese": "3-5 phrases factuelles fondées sur les données de l'outil",
 "score": <somme des points>,
 "criteres": [{"critere": "État administratif", "points": <n>, "justification": "..."},
              {"critere": "Ancienneté", "points": <n>, "justification": "..."},
              {"critere": "Taille", "points": <n>, "justification": "..."},
              {"critere": "Cohérence des données", "points": <n>, "justification": "..."}]}
S'il y a plusieurs résultats, analyse le plus pertinent par rapport à la demande et dis-le
dans la synthèse."""


def _summarize_tool_result(companies: list[dict]) -> str:
    if not companies:
        return "aucun résultat"
    parts = [f"{c['nom']} ({c['etat']}, SIREN {c['siren']})" for c in companies[:3]]
    extra = f" +{len(companies) - 3} autre(s)" if len(companies) > 3 else ""
    return f"{len(companies)} fiche(s) : " + " · ".join(parts) + extra


def _parse_final(content: str) -> dict | None:
    """Extrait le JSON final ({synthese, score, criteres}) — None si illisible."""
    text = (content or "").strip()
    start_index, end_index = text.find("{"), text.rfind("}")
    if start_index == -1 or end_index <= start_index:
        return None
    try:
        parsed = json.loads(text[start_index : end_index + 1])
    except ValueError:
        return None
    if not isinstance(parsed, dict) or "synthese" not in parsed:
        return None
    return parsed


async def _run_tool(name: str, arguments: str) -> str:
    """Exécute l'outil demandé par le modèle — réutilise la recherche M3-a, sans duplication."""
    if name != "rechercher_entreprise":
        return json.dumps({"erreur": f"outil inconnu : {name}"}, ensure_ascii=False)
    try:
        query = json.loads(arguments or "{}").get("query", "")
    except ValueError:
        query = ""
    if not query:
        return json.dumps({"erreur": "paramètre query manquant"}, ensure_ascii=False)
    try:
        return json.dumps(await search_companies(query), ensure_ascii=False)
    except SearchError as exc:
        return json.dumps({"erreur": str(exc)}, ensure_ascii=False)


async def analyze(query: str) -> dict:
    """Boucle agentique complète. Retourne {timeline, result, raw_answer, error}."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Évalue la fiabilité de ce fournisseur : {query}"},
    ]
    timeline = []
    for turn in range(1, MAX_TURNS + 1):
        reply = await llm.complete_messages(messages, tools=TOOLS)
        if reply["tool_calls"]:
            messages.append(reply["message"])
            for call in reply["tool_calls"]:
                try:
                    shown_args = json.loads(call["arguments"] or "{}").get("query", "?")
                except ValueError:
                    shown_args = "?"
                timeline.append(
                    {
                        "turn": turn,
                        "kind": "tool_call",
                        "text": f"Le modèle a émis un tool_call (id {call['id']}) : "
                        f"rechercher_entreprise(« {shown_args} »)",
                    }
                )
                result = await _run_tool(call["name"], call["arguments"])
                try:
                    parsed_result = json.loads(result)
                    summary = (
                        parsed_result["erreur"]
                        if isinstance(parsed_result, dict) and "erreur" in parsed_result
                        else _summarize_tool_result(parsed_result)
                    )
                except ValueError:
                    summary = "résultat illisible"
                timeline.append(
                    {"turn": turn, "kind": "tool_result", "text": f"Données reçues : {summary}"}
                )
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            continue

        timeline.append(
            {"turn": turn, "kind": "final", "text": "Le modèle produit sa synthèse finale."}
        )
        return {
            "timeline": timeline,
            "result": _parse_final(reply["content"]),
            "raw_answer": reply["content"],
            "error": None,
        }

    timeline.append(
        {
            "turn": MAX_TURNS,
            "kind": "stopped",
            "text": f"Garde-fou : arrêt après {MAX_TURNS} tours sans réponse finale.",
        }
    )
    return {
        "timeline": timeline,
        "result": None,
        "raw_answer": None,
        "error": f"L'agent n'a pas conclu en {MAX_TURNS} tours — analyse interrompue proprement.",
    }

"""Agent d'analyse fournisseur — vrai function-calling via la couche LLM du socle.

Boucle agentique : le MODÈLE décide d'appeler l'outil (tool_choice="auto", jamais
pré-appelé par le code), on exécute la vraie recherche M3-a, on lui renvoie le
résultat (même tool_call_id), il synthétise. Chaque tour est tracé dans une
timeline affichée à l'utilisateur.
"""

import json
from datetime import date, datetime

from app.core import llm
from app.modules.suppliers.bodacc import search_procedures
from app.modules.suppliers.client import SearchError, search_companies

MAX_TURNS = 5  # garde-fou anti-boucle infinie (2 outils → un tour de plus qu'en M3-b1)

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
    },
    {
        "type": "function",
        "function": {
            "name": "rechercher_procedures_bodacc",
            "description": (
                "Recherche les annonces de PROCÉDURES COLLECTIVES (sauvegarde, redressement, "
                "liquidation judiciaire) publiées au BODACC pour un SIREN donné. "
                "Source : DILA, annonces légales officielles, data publique. "
                "Attention : l'absence d'annonce ne prouve pas la bonne santé de l'entreprise."
            ),
            "parameters": {
                "type": "object",
                "properties": {"siren": {"type": "string", "description": "SIREN à 9 chiffres"}},
                "required": ["siren"],
            },
        },
    },
]

SYSTEM_PROMPT = """Tu es l'analyste fournisseurs de la plateforme AtelIA. Tu évalues la fiabilité
administrative d'une entreprise française en t'appuyant EXCLUSIVEMENT sur tes deux outils :
1. rechercher_entreprise — identité et état administratif (registres RNE + Sirene) ;
2. rechercher_procedures_bodacc — procédures collectives publiées au BODACC (DILA).

DÉMARCHE : identifie d'abord l'entreprise et son SIREN avec rechercher_entreprise, PUIS
consulte systématiquement le BODACC avec ce SIREN avant de produire ta synthèse.

RÈGLE BODACC — NUANCE OBLIGATOIRE :
- Procédure trouvée = signal de risque : signale-le clairement dans la synthèse (nature, date).
- Aucune procédure trouvée = information NEUTRE : écris exactement « aucune procédure
  collective trouvée au BODACC (absence non probante) ». INTERDICTION de conclure que
  l'entreprise est « saine », « solvable » ou « sans risque » sur la base de cette absence.
- Le BODACC n'entre PAS dans le score : le barème ci-dessous reste inchangé.

RÈGLES D'ANCRAGE — ABSOLUES :
- Tu raisonnes UNIQUEMENT sur les données réellement renvoyées par l'outil.
- INTERDICTION d'inventer ou d'estimer : chiffre d'affaires, santé financière, solvabilité,
  rentabilité, notation, litiges. L'API ne fournit PAS ces informations.
- Toute information absente des données de l'outil : écris « non disponible ».
- Si l'outil renvoie une erreur ou aucun résultat, dis-le simplement, sans supposer.

SCORE DE FIABILITÉ — CALCULÉ PAR LE SYSTÈME, JAMAIS PAR TOI :
Chaque fiche renvoyée par rechercher_entreprise contient un champ « score_bareme »
(score 0-100 et détail des critères), calculé par le système selon un barème fixe
(état actif 50 / ancienneté 30 / cohérence des données 20 ; entreprise cessée = 0,
éliminatoire). Tu peux citer ce score tel quel dans ta synthèse. INTERDICTION ABSOLUE
de le recalculer, de le modifier, d'en inventer un autre ou d'y retrancher des points —
notamment : les procédures BODACC ne modifient JAMAIS ce score, ce sont des signaux à
part que tu signales dans la synthèse.

RÉPONSE FINALE — STRICTEMENT ce JSON, sans texte autour ni markdown :
{"synthese": "3-5 phrases factuelles fondées sur les données des outils (état, ancienneté,
 cohérence, résultat BODACC avec sa nuance, score système éventuellement cité tel quel)",
 "siren_analyse": "le SIREN de la fiche que tu as analysée"}
Les clés JSON sont exactement "synthese" et "siren_analyse" — SANS accent. S'il y a
plusieurs résultats, analyse le plus pertinent par rapport à la demande et dis-le dans
la synthèse."""


def grade(fiche: dict, today: date | None = None) -> dict:
    """Barème déterministe — SEULE source de vérité du score (le LLM ne calcule jamais).

    Le score global est la somme des points des lignes du tableau construites ici :
    par construction, le gros chiffre affiché et le tableau ne peuvent pas diverger.
    Le BODACC n'est volontairement PAS un paramètre : il ne peut rien retrancher.
    """
    today = today or date.today()
    if not fiche.get("active"):
        elimine = "Annulée par la règle éliminatoire (entreprise cessée)."
        criteres = [
            {
                "critere": "État administratif",
                "points": 0,
                "justification": "Cessée — éliminatoire : tous les critères sont ramenés à 0.",
            },
            {"critere": "Ancienneté", "points": 0, "justification": elimine},
            {"critere": "Cohérence des données", "points": 0, "justification": elimine},
        ]
    else:
        criteres = [
            {
                "critere": "État administratif",
                "points": 50,
                "justification": "Entreprise active dans les registres officiels.",
            }
        ]
        age_points, age_just = 0, "Date de création non disponible."
        creation = fiche.get("creation")
        if creation and creation != "—":
            try:
                created = datetime.strptime(creation, "%Y-%m-%d").date()
            except ValueError:
                created = None
            if created is not None:
                years = (today - created).days / 365.25
                if years > 10:
                    age_points, age_just = 30, f"Créée le {created:%d/%m/%Y} — plus de 10 ans."
                elif years >= 3:
                    age_points, age_just = 20, f"Créée le {created:%d/%m/%Y} — entre 3 et 10 ans."
                else:
                    age_points, age_just = 10, f"Créée le {created:%d/%m/%Y} — moins de 3 ans."
        criteres.append({"critere": "Ancienneté", "points": age_points, "justification": age_just})

        siren_ok = bool(fiche.get("siren"))
        naf_ok = bool(fiche.get("naf")) and fiche.get("naf") != "—"
        criteres.append(
            {
                "critere": "Cohérence des données",
                "points": (10 if siren_ok else 0) + (10 if naf_ok else 0),
                "justification": f"SIREN {'présent (+10)' if siren_ok else 'absent (+0)'} ; "
                f"code NAF {'présent (+10)' if naf_ok else 'absent (+0)'}.",
            }
        )
    # Le total EST la somme des lignes du tableau — pas de second calcul parallèle.
    return {"score": sum(c["points"] for c in criteres), "criteres": criteres}


def _select_fiche(
    companies: list[dict], siren_analyse: str | None, bodacc_siren: str | None
) -> dict | None:
    """Fiche à noter : celle désignée par le modèle, sinon celle passée au BODACC, sinon la 1re."""
    for wanted in (siren_analyse, bodacc_siren):
        if wanted:
            for fiche in companies:
                if fiche.get("siren") == wanted:
                    return fiche
    return companies[0] if companies else None


def _summarize_tool_result(companies: list[dict]) -> str:
    if not companies:
        return "aucun résultat"
    parts = [f"{c['nom']} ({c['etat']}, SIREN {c['siren']})" for c in companies[:3]]
    extra = f" +{len(companies) - 3} autre(s)" if len(companies) > 3 else ""
    return f"{len(companies)} fiche(s) : " + " · ".join(parts) + extra


# Le prompt impose des clés sans accent, mais les modèles en remettent parfois : on tolère.
_KEY_ALIASES = {"synthèse": "synthese", "critères": "criteres", "critère": "critere"}


def _normalize_keys(value):
    if isinstance(value, dict):
        return {_KEY_ALIASES.get(k, k): _normalize_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_keys(item) for item in value]
    return value


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
    if not isinstance(parsed, dict):
        return None
    parsed = _normalize_keys(parsed)
    if "synthese" not in parsed:
        return None
    return parsed


def _summarize_procedures(procedures: list[dict]) -> str:
    if not procedures:
        return "aucune procédure collective (absence non probante)"
    parts = [f"{p['nature']} ({p['date_jugement']})" for p in procedures[:3]]
    extra = f" +{len(procedures) - 3} autre(s)" if len(procedures) > 3 else ""
    return f"{len(procedures)} procédure(s) : " + " · ".join(parts) + extra


async def _run_tool(name: str, arguments: str) -> tuple[str, str, dict]:
    """Exécute l'outil demandé par le modèle. Réutilise les clients M3-a/BODACC existants.

    Retourne (contenu JSON pour le modèle, résumé pour la timeline, captures).
    Les captures ({"companies", "bodacc", "bodacc_siren"}) alimentent le score et le bloc
    d'alerte de l'UI depuis la donnée BRUTE des API — jamais depuis le texte du LLM (ancrage).
    """
    try:
        args = json.loads(arguments or "{}")
    except ValueError:
        args = {}

    if name == "rechercher_entreprise":
        query = args.get("query", "")
        if not query:
            return (
                json.dumps({"erreur": "paramètre query manquant"}, ensure_ascii=False),
                ("paramètre query manquant"),
                {},
            )
        try:
            companies = await search_companies(query)
            # score_bareme calculé EN CODE et fourni au modèle : il le reçoit, ne le calcule pas
            enriched = [{**fiche, "score_bareme": grade(fiche)} for fiche in companies]
            return (
                json.dumps(enriched, ensure_ascii=False),
                _summarize_tool_result(companies),
                {"companies": companies},
            )
        except SearchError as exc:
            return json.dumps({"erreur": str(exc)}, ensure_ascii=False), str(exc), {}

    if name == "rechercher_procedures_bodacc":
        siren = args.get("siren", "")
        try:
            procedures = await search_procedures(siren)
            payload = {
                "procedures_collectives": procedures,
                "note": "l'absence de procédure ne prouve pas la bonne santé (non probante)",
            }
            capture = {"consulted": True, "procedures": procedures, "error": None}
            return (
                json.dumps(payload, ensure_ascii=False),
                _summarize_procedures(procedures),
                {"bodacc": capture, "bodacc_siren": siren},
            )
        except SearchError as exc:
            capture = {"consulted": True, "procedures": None, "error": str(exc)}
            return (
                json.dumps({"erreur": str(exc)}, ensure_ascii=False),
                str(exc),
                {"bodacc": capture, "bodacc_siren": siren},
            )

    return (
        json.dumps({"erreur": f"outil inconnu : {name}"}, ensure_ascii=False),
        (f"outil inconnu : {name}"),
        {},
    )


async def analyze(query: str) -> dict:
    """Boucle agentique complète. Retourne {timeline, result, raw_answer, error}."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Évalue la fiabilité de ce fournisseur : {query}"},
    ]
    timeline = []
    bodacc_capture = None  # rempli depuis la donnée brute de l'API si l'agent consulte le BODACC
    captured_companies: list[dict] = []  # fiches brutes reçues — base du score déterministe
    bodacc_siren = None
    for turn in range(1, MAX_TURNS + 1):
        try:
            reply = await llm.complete_messages(messages, tools=TOOLS)
        except Exception as exc:  # rate limit, quota, réseau… : message propre, jamais de 500
            timeline.append(
                {"turn": turn, "kind": "stopped", "text": f"Appel au modèle échoué : {exc}"[:180]}
            )
            return {
                "timeline": timeline,
                "result": None,
                "raw_answer": None,
                "bodacc": bodacc_capture,
                "error": "L'appel au modèle a échoué (limite de débit ou indisponibilité) — "
                "réessayez dans quelques secondes.",
            }
        if reply["tool_calls"]:
            messages.append(reply["message"])
            for call in reply["tool_calls"]:
                try:
                    args = json.loads(call["arguments"] or "{}")
                    shown_args = args.get("query") or args.get("siren") or "?"
                except ValueError:
                    shown_args = "?"
                timeline.append(
                    {
                        "turn": turn,
                        "kind": "tool_call",
                        "text": f"Le modèle a émis un tool_call (id {call['id']}) : "
                        f"{call['name']}(« {shown_args} »)",
                    }
                )
                result, summary, captures = await _run_tool(call["name"], call["arguments"])
                if "companies" in captures:
                    captured_companies.extend(captures["companies"])
                if "bodacc" in captures:
                    bodacc_capture = captures["bodacc"]
                    bodacc_siren = captures.get("bodacc_siren")
                timeline.append(
                    {"turn": turn, "kind": "tool_result", "text": f"Données reçues : {summary}"}
                )
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            continue

        timeline.append(
            {"turn": turn, "kind": "final", "text": "Le modèle produit sa synthèse finale."}
        )
        parsed = _parse_final(reply["content"])
        result = None
        if parsed is not None:
            # Score et tableau viennent de grade() sur la fiche BRUTE capturée — le LLM
            # ne fournit que la prose. Chiffre et tableau ne peuvent pas diverger.
            fiche = _select_fiche(captured_companies, parsed.get("siren_analyse"), bodacc_siren)
            notation = grade(fiche) if fiche else {"score": None, "criteres": []}
            result = {
                "synthese": parsed.get("synthese"),
                "score": notation["score"],
                "criteres": notation["criteres"],
                "taille": fiche.get("effectif") if fiche else None,
            }
        return {
            "timeline": timeline,
            "result": result,
            "raw_answer": reply["content"],
            "bodacc": bodacc_capture,
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
        "bodacc": bodacc_capture,
        "error": f"L'agent n'a pas conclu en {MAX_TURNS} tours — analyse interrompue proprement.",
    }

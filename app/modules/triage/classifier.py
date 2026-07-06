"""Classification zero-shot des messages entrants — LLM dans un cadre contraint.

Trois verrous, du plus souple au plus dur :
1. le prompt impose des listes fermées et un JSON strict (zero-shot : les catégories
   sont décrites, jamais illustrées d'exemples étiquetés) ;
2. le code PARSE et VALIDE via Pydantic (Literal = liste fermée par le typage) ;
   JSON invalide ou catégorie hors liste → UN retry motivé, puis erreur propre ;
3. GARDE-FOU SÉCURITÉ déterministe par-dessus le LLM : sur les signaux de sécurité
   alimentaire, la priorité est FORCÉE à « critique » et la catégorie à « Sécurité »,
   quel que soit l'avis du modèle. Parti pris documenté : RAPPEL > précision — une
   fausse alerte coûte une vérification humaine, un manqué coûte une crise sanitaire.
   On ne confie jamais le critique au seul jugement d'un LLM (même principe que le
   score déterministe de M3).

Données synthétiques assumées : aucune vraie réclamation (confidentialité).
"""

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

from app.core import llm

logger = logging.getLogger(__name__)

CATEGORIES = ("Qualité", "Logistique", "Commercial", "Administratif", "Sécurité")
PRIORITES = ("critique", "haute", "moyenne", "basse")

SECURITY_SERVICE = "Qualité / Sécurité alimentaire"

# Signaux de sécurité alimentaire (regex, insensibles à la casse) — liste volontairement
# large (rappel > précision) : « malade » seul déclenche, tant pis pour l'hyperbole.
SECURITY_PATTERNS = [
    (r"allergi|allergène", "allergène / allergie"),
    (
        r"(ne (mentionne|indique|déclare) pas|non (mentionn|indiqu|déclar)|pas (indiqu|mentionn|déclar)).{0,60}(arachide|noisette|gluten|lait|œuf|oeuf|soja|sésame|sesame|crustacé|céleri|moutarde|lupin|sulfite|trace)",
        "ingrédient allergisant non déclaré",
    ),
    (
        r"(trace|traces) de (noisette|arachide|gluten|lait|œuf|oeuf|soja|sésame|sesame|fruits à coque).{0,60}(non|pas|oubli|manqu|absent)",
        "traces allergènes non étiquetées",
    ),
    (r"corps étranger", "corps étranger"),
    (
        r"(morceau|éclat|bout|fragment|débris)x?s? de (verre|métal|metal|plastique|bois)",
        "corps étranger (verre/métal/plastique)",
    ),
    (
        r"trouvé.{0,40}(verre|métal|metal|plastique|vis|insecte|cheveu)",
        "objet trouvé dans le produit",
    ),
    (r"intoxicat|vomi|diarrhée|nausée", "symptômes d'intoxication"),
    (r"\bmalade", "personne malade"),
    (r"hôpital|urgences\b", "prise en charge médicale"),
    (r"listeria|salmonell|botulis|e\.? ?coli|staphylocoque", "pathogène nommé"),
    (
        r"(couvercle|bocal|boîte) (bombé|gonflé|bombée|gonflée)|odeur (suspecte|anormale|putride)",
        "signe d'altération (bombage, odeur)",
    ),
    (r"rappel (produit|de lot|des lots)", "demande de rappel produit"),
    (r"étouff", "risque d'étouffement"),
]


def security_guard(message: str) -> list[str]:
    """Détection déterministe des signaux de sécurité alimentaire — AUCUN LLM.

    Retourne les libellés des signaux détectés (vide = pas de déclenchement).
    """
    signals = []
    for pattern, label in SECURITY_PATTERNS:
        if re.search(pattern, message, flags=re.IGNORECASE) and label not in signals:
            signals.append(label)
    return signals


class Classification(BaseModel):
    """Sortie contrainte : les Literal ferment les listes au niveau du typage."""

    categorie: Literal["Qualité", "Logistique", "Commercial", "Administratif", "Sécurité"]
    priorite: Literal["critique", "haute", "moyenne", "basse"]
    resume: str
    service_destinataire: str
    entites: dict[str, str] = {}

    @field_validator("entites", mode="before")
    @classmethod
    def _stringify_values(cls, value):
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items() if v is not None}
        return {}


SYSTEM_PROMPT = """Tu tries le courrier entrant d'une conserverie artisanale (emails, formulaires,
réclamations). Pour chaque message, tu produis UNE classification.

CATÉGORIES (liste FERMÉE, aucune autre valeur possible) :
- "Qualité" : goût, texture, aspect, conformité produit, emballage défectueux sans danger.
- "Logistique" : livraisons, retards, quantités manquantes, transport, stocks.
- "Commercial" : demandes de référencement, tarifs, nouveaux clients, partenariats.
- "Administratif" : factures, paiements, documents, données fournisseur/client.
- "Sécurité" : danger pour le consommateur (allergène non déclaré, corps étranger,
  intoxication, produit altéré). En cas de doute entre Sécurité et Qualité → Sécurité.

PRIORITÉS (liste FERMÉE) : "critique" (danger consommateur, urgence sanitaire),
"haute" (client bloqué, impact immédiat), "moyenne" (à traiter cette semaine),
"basse" (informatif, sans urgence).

SERVICE DESTINATAIRE (choisis le plus adapté) : "Service Qualité",
"Qualité / Sécurité alimentaire", "Service Logistique", "Service Commercial",
"Comptabilité / Administration".

RÉPONSE — STRICTEMENT ce JSON, sans texte autour ni markdown, clés sans accent :
{"categorie": "...", "priorite": "...", "resume": "une phrase factuelle",
 "service_destinataire": "...",
 "entites": {"produit": "...", "num_commande": "...", "num_lot": "...", "client": "..."}}
Dans "entites", n'inclus QUE les clés réellement présentes dans le message."""


def _parse(content: str) -> tuple[Classification | None, str]:
    """Extrait et valide le JSON du modèle. Retourne (classification, motif d'échec)."""
    text = (content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None, "aucun JSON trouvé dans la réponse"
    try:
        raw = json.loads(text[start : end + 1])
    except ValueError as exc:
        return None, f"JSON illisible ({exc})"
    try:
        return Classification.model_validate(raw), ""
    except ValidationError as exc:
        reasons = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()[:3]
        )
        return None, f"schéma invalide ({reasons})"


async def classify(message: str) -> dict:
    """Chaîne complète : garde-fou (toujours) + LLM contraint (retry unique si invalide).

    Le garde-fou est calculé sur le message BRUT, indépendamment du LLM : même si la
    génération échoue, les signaux de sécurité détectés sont remontés à l'UI.
    """
    signals = security_guard(message)
    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"MESSAGE À CLASSER :\n{message}"},
    ]
    classification, error = None, None
    for _attempt in (1, 2):  # un retry motivé, pas plus
        try:
            reply = await llm.complete_messages(conversation, max_tokens=600)
        except Exception:  # rate limit, réseau… : message propre, jamais de 500
            logger.warning("Triage : appel LLM échoué", exc_info=True)
            error = (
                "La classification a échoué (limite de débit ou indisponibilité du modèle) — "
                "réessayez dans quelques secondes."
            )
            break
        classification, problem = _parse(reply["content"])
        if classification is not None:
            break
        logger.info("Triage : sortie LLM invalide (%s) — retry", problem)
        conversation.append({"role": "assistant", "content": reply["content"]})
        conversation.append(
            {
                "role": "user",
                "content": f"Ta réponse était invalide ({problem}). "
                "Renvoie UNIQUEMENT le JSON demandé, sans aucun texte autour.",
            }
        )
        error = "Le modèle n'a pas produit de classification exploitable — réessayez."

    if classification is not None:
        error = None
        if signals:
            # LE garde-fou : le jugement du LLM est OUTREPASSÉ sur le critique
            classification = classification.model_copy(
                update={
                    "categorie": "Sécurité",
                    "priorite": "critique",
                    "service_destinataire": SECURITY_SERVICE,
                }
            )
    return {
        "classification": classification,
        "garde_fou": bool(signals),
        "signaux": signals,
        "error": error,
    }

"""Client de l'API Recherche d'entreprises (recherche-entreprises.api.gouv.fr).

API ouverte de l'État, sans clé — données officielles RNE + Sirene (ADR-104 : API
publiques uniquement, pas de scraping). Un terme de 9 chiffres est traité par l'API
comme un SIREN, sinon recherche textuelle. Limite officielle : 7 req/s — l'usage ici
est humain (une requête par action UI, pas de recherche à la frappe), très en dessous :
pas de limiteur côté client, choix assumé.
"""

import httpx

from app.core.config import settings

TIMEOUT_S = 5.0

# Nomenclature INSEE des tranches d'effectif salarié
EFFECTIF_LABELS = {
    "00": "0 salarié",
    "01": "1 ou 2 salariés",
    "02": "3 à 5 salariés",
    "03": "6 à 9 salariés",
    "11": "10 à 19 salariés",
    "12": "20 à 49 salariés",
    "21": "50 à 99 salariés",
    "22": "100 à 199 salariés",
    "31": "200 à 249 salariés",
    "32": "250 à 499 salariés",
    "41": "500 à 999 salariés",
    "42": "1 000 à 1 999 salariés",
    "51": "2 000 à 4 999 salariés",
    "52": "5 000 à 9 999 salariés",
    "53": "10 000 salariés et plus",
}

ETAT_LABELS = {"A": "Active", "C": "Cessée"}


class SearchError(Exception):
    """Erreur d'appel à l'API — le message est affichable tel quel à l'utilisateur."""


def _format_dirigeant(dirigeant: dict) -> str:
    qualite = dirigeant.get("qualite") or ""
    if dirigeant.get("denomination"):  # personne morale
        nom = dirigeant["denomination"]
    else:
        nom = " ".join(filter(None, [dirigeant.get("prenoms"), dirigeant.get("nom")]))
    return f"{nom} — {qualite}" if qualite else nom


def parse_results(payload: dict) -> list[dict]:
    """Normalise la réponse API en fiches affichables — fonction pure, testée sans réseau.

    On n'expose que ce que l'API ouverte fournit réellement (pas de données financières).
    """
    companies = []
    for result in payload.get("results", []):
        siege = result.get("siege") or {}
        adresse = siege.get("adresse") or ", ".join(
            filter(None, [siege.get("code_postal"), siege.get("libelle_commune")])
        )
        etat_code = result.get("etat_administratif")
        companies.append(
            {
                "nom": result.get("nom_complet") or result.get("nom_raison_sociale") or "—",
                "siren": result.get("siren"),
                "etat": ETAT_LABELS.get(etat_code, etat_code or "inconnu"),
                "active": etat_code == "A",
                "naf": result.get("activite_principale") or "—",
                "effectif": EFFECTIF_LABELS.get(
                    result.get("tranche_effectif_salarie"), "non renseigné"
                ),
                "creation": result.get("date_creation") or "—",
                "siege": adresse or "—",
                "dirigeants": [_format_dirigeant(d) for d in (result.get("dirigeants") or [])[:5]],
            }
        )
    return companies


async def search_companies(
    query: str, per_page: int = 5, transport: httpx.AsyncBaseTransport | None = None
) -> list[dict]:
    """Interroge l'API et renvoie les fiches normalisées. Lève SearchError, jamais de crash.

    `transport` est injectable pour les tests (httpx.MockTransport) — aucun test ne tape le réseau.
    """
    params = {"q": query, "page": 1, "per_page": per_page}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            response = await client.get(settings.suppliers_api_url, params=params)
    except httpx.TimeoutException as exc:
        raise SearchError("L'API publique n'a pas répondu à temps (5 s) — réessayez.") from exc
    except httpx.HTTPError as exc:
        raise SearchError(
            "L'API publique est injoignable pour le moment — réessayez plus tard."
        ) from exc

    if response.status_code == 429:
        raise SearchError("Limite de débit de l'API atteinte — patientez quelques secondes.")
    if response.status_code >= 500:
        raise SearchError("L'API publique est momentanément indisponible (erreur serveur).")
    if response.status_code >= 400:
        raise SearchError(
            f"Requête refusée par l'API (code {response.status_code}) — vérifiez le terme recherché."
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchError("Réponse illisible de l'API publique — réessayez.") from exc
    return parse_results(payload)
